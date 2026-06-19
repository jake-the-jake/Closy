import { THREE } from "../three";

export type AvatarRenderProbeSnapshot = {
  drawSubmitted: boolean;
  drawConfirmationCount: number;
  firstDrawTimestamp: number | null;
  lastDrawTimestamp: number | null;
  firstDrawFrame: number | null;
  lastDrawFrame: number | null;
  rendererCallCountAtConfirmation: number | null;
  rendererTriangleCountAtConfirmation: number | null;
};

export type AvatarProjectionSnapshot = {
  projectedBoundsVisible: boolean;
  cameraFrustumValid: boolean;
  ndcMin: [number, number, number] | null;
  ndcMax: [number, number, number] | null;
  cameraDistance: number | null;
  cameraNear: number | null;
  cameraFar: number | null;
  reason: string;
};

type ProbeState = AvatarRenderProbeSnapshot & {
  frame: number;
};

function isMeshLike(o: THREE.Object3D): o is THREE.Mesh | THREE.SkinnedMesh {
  const flags = o as { isMesh?: boolean; isSkinnedMesh?: boolean };
  return flags.isMesh === true || flags.isSkinnedMesh === true;
}

export function findFirstRenderableMesh(root: THREE.Object3D): THREE.Mesh | THREE.SkinnedMesh | null {
  let first: THREE.Mesh | THREE.SkinnedMesh | null = null;
  root.traverse((o) => {
    if (first || !isMeshLike(o)) return;
    first = o;
  });
  return first;
}

export function createAvatarRenderProbe({
  root,
  sourceKey,
  sceneUuid,
}: {
  root: THREE.Object3D;
  sourceKey: string;
  sceneUuid: string;
}) {
  const mesh = findFirstRenderableMesh(root);
  const originalBefore = mesh?.onBeforeRender;
  const originalAfter = mesh?.onAfterRender;
  const state: ProbeState = {
    frame: 0,
    drawSubmitted: false,
    drawConfirmationCount: 0,
    firstDrawTimestamp: null,
    lastDrawTimestamp: null,
    firstDrawFrame: null,
    lastDrawFrame: null,
    rendererCallCountAtConfirmation: null,
    rendererTriangleCountAtConfirmation: null,
  };

  if (mesh) {
    mesh.onBeforeRender = function onAvatarProbeBeforeRender(...args) {
      state.drawSubmitted = true;
      originalBefore?.apply(this, args);
    };
    mesh.onAfterRender = function onAvatarProbeAfterRender(renderer, scene, camera, geometry, material, group) {
      const now = Date.now();
      state.drawSubmitted = true;
      state.drawConfirmationCount += 1;
      state.firstDrawTimestamp ??= now;
      state.lastDrawTimestamp = now;
      state.firstDrawFrame ??= state.frame;
      state.lastDrawFrame = state.frame;
      state.rendererCallCountAtConfirmation =
        typeof renderer.info?.render?.calls === "number" ? renderer.info.render.calls : null;
      state.rendererTriangleCountAtConfirmation =
        typeof renderer.info?.render?.triangles === "number" ? renderer.info.render.triangles : null;
      originalAfter?.call(this, renderer, scene, camera, geometry, material, group);
    };
  }

  return {
    sourceKey,
    sceneUuid,
    meshName: mesh?.name || null,
    tickFrame() {
      state.frame += 1;
    },
    snapshot(): AvatarRenderProbeSnapshot {
      return {
        drawSubmitted: state.drawSubmitted,
        drawConfirmationCount: state.drawConfirmationCount,
        firstDrawTimestamp: state.firstDrawTimestamp,
        lastDrawTimestamp: state.lastDrawTimestamp,
        firstDrawFrame: state.firstDrawFrame,
        lastDrawFrame: state.lastDrawFrame,
        rendererCallCountAtConfirmation: state.rendererCallCountAtConfirmation,
        rendererTriangleCountAtConfirmation: state.rendererTriangleCountAtConfirmation,
      };
    },
    dispose() {
      if (!mesh) return;
      mesh.onBeforeRender = originalBefore ?? (() => undefined);
      mesh.onAfterRender = originalAfter ?? (() => undefined);
    },
  };
}

function tuple(v: THREE.Vector3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function finiteTuple(values: [number, number, number]): boolean {
  return values.every((n) => Number.isFinite(n));
}

export function projectObjectBounds(
  root: THREE.Object3D,
  camera: THREE.Camera,
): AvatarProjectionSnapshot {
  root.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  if ("updateProjectionMatrix" in camera && typeof camera.updateProjectionMatrix === "function") {
    camera.updateProjectionMatrix();
  }

  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  if (
    !Number.isFinite(size.x) ||
    !Number.isFinite(size.y) ||
    !Number.isFinite(size.z) ||
    size.lengthSq() <= 1e-12
  ) {
    return {
      projectedBoundsVisible: false,
      cameraFrustumValid: false,
      ndcMin: null,
      ndcMax: null,
      cameraDistance: null,
      cameraNear: null,
      cameraFar: null,
      reason: "bounds_invalid",
    };
  }

  const points = [
    new THREE.Vector3(box.min.x, box.min.y, box.min.z),
    new THREE.Vector3(box.min.x, box.min.y, box.max.z),
    new THREE.Vector3(box.min.x, box.max.y, box.min.z),
    new THREE.Vector3(box.min.x, box.max.y, box.max.z),
    new THREE.Vector3(box.max.x, box.min.y, box.min.z),
    new THREE.Vector3(box.max.x, box.min.y, box.max.z),
    new THREE.Vector3(box.max.x, box.max.y, box.min.z),
    new THREE.Vector3(box.max.x, box.max.y, box.max.z),
    center.clone(),
  ];
  const ndcMin = new THREE.Vector3(Infinity, Infinity, Infinity);
  const ndcMax = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  for (const point of points) {
    const projected = point.clone().project(camera);
    if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y) || !Number.isFinite(projected.z)) {
      return {
        projectedBoundsVisible: false,
        cameraFrustumValid: false,
        ndcMin: null,
        ndcMax: null,
        cameraDistance: null,
        cameraNear: null,
        cameraFar: null,
        reason: "projection_nonfinite",
      };
    }
    ndcMin.min(projected);
    ndcMax.max(projected);
  }

  const cameraPosition = new THREE.Vector3();
  camera.getWorldPosition(cameraPosition);
  const cameraDistance = cameraPosition.distanceTo(center);
  const cameraNear = (camera as THREE.PerspectiveCamera | THREE.OrthographicCamera).near ?? null;
  const cameraFar = (camera as THREE.PerspectiveCamera | THREE.OrthographicCamera).far ?? null;
  const ndcMinTuple = tuple(ndcMin);
  const ndcMaxTuple = tuple(ndcMax);
  const cameraFrustumValid =
    finiteTuple(ndcMinTuple) &&
    finiteTuple(ndcMaxTuple) &&
    Number.isFinite(cameraDistance) &&
    cameraDistance > 1e-6 &&
    (cameraNear == null || cameraDistance >= cameraNear * 0.25) &&
    (cameraFar == null || cameraDistance <= cameraFar * 1.25);
  const intersectsViewport =
    ndcMax.x >= -1 &&
    ndcMin.x <= 1 &&
    ndcMax.y >= -1 &&
    ndcMin.y <= 1 &&
    ndcMax.z >= -1 &&
    ndcMin.z <= 1;

  return {
    projectedBoundsVisible: cameraFrustumValid && intersectsViewport,
    cameraFrustumValid,
    ndcMin: ndcMinTuple,
    ndcMax: ndcMaxTuple,
    cameraDistance,
    cameraNear,
    cameraFar,
    reason: cameraFrustumValid && intersectsViewport ? "projected_visible" : "projected_outside_view",
  };
}
