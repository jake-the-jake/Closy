# Avatar Runtime Pipeline

Closy Avatar Preview now treats procedural geometry as an emergency fallback, not the desired product visual.

## Runtime Source Order

The avatar source manager resolves one deterministic body source:

1. `realistic_glb`: a runtime URL or future bundled realistic avatar.
2. `stylised_glb`: the bundled stylised mannequin GLB slot.
3. `procedural_fallback`: the safe procedural mannequin when no GLB is available or a GLB fails.

The viewport keeps the procedural fallback available during GLB loading so startup never opens blank.

## Asset Locations

Preferred asset convention:

- `assets/avatar/realistic/default-avatar.glb`
- `assets/avatar/realistic/default-avatar.meta.json`
- `assets/avatar/stylised/default-mannequin.glb`
- `assets/avatar/stylised/default-mannequin.meta.json`

Current bridge:

- `assets/models/avatar/default-stylised-avatar.glb` is still used as the bundled stylised slot until a dedicated file is placed in the new convention.

## GLB Export Requirements

- Units: meters.
- Orientation: Y-up, avatar facing +Z.
- Scale: roughly 1.7-1.85 meters tall; runtime normalization targets about 1.78.
- Origin: near floor center if possible. Runtime also centers X/Z and grounds feet at `y=0`.
- Materials: standard PBR where possible. Use base color, roughness, metalness, normal maps if mobile-safe.
- Meshes: keep body mesh count low. Avoid custom shaders for Expo GL.
- Textures: keep mobile budgets modest. Prefer 1K or lower for early dev.

## Rig Naming

Recommended names:

- `hips` / `pelvis`
- `spine`
- `chest`
- `neck`
- `head`
- `upperArm_L`, `lowerArm_L`, `hand_L`
- `upperArm_R`, `lowerArm_R`, `hand_R`
- `upperLeg_L`, `lowerLeg_L`, `foot_L`
- `upperLeg_R`, `lowerLeg_R`, `foot_R`

The inspector also recognizes common Mixamo, Ready Player Me-ish, VRM-ish, SMPL-ish, Blender, and CesiumMan-style names.

## Garment Foundation

Garments should bind to resolved anchors, not arbitrary viewport offsets:

- head, neck, chest, waist, hips
- shoulder/elbow/wrist left and right
- thigh/knee/ankle/foot left and right

Anchor source priority:

1. Detected bones.
2. Future named empties/nodes.
3. Bounds-derived fallback.
4. Procedural fallback anchors.

Fit proxies are simple capsule/ellipsoid volumes for torso, pelvis, arms, and legs. They are hidden in Clean mode and visible in Fit/Debug modes.

## Future Path

The architecture is ready for:

- SMPL / SMPL-X style parametric body models.
- MediaPipe/OpenPose-style body keypoints.
- Image-to-avatar reconstruction.
- Ready Player Me / MakeHuman / Blender-authored rigs.
- Garment segmentation, learned garment deformation, and later cloth simulation.
- A native renderer or server-side avatar generation path if Expo GL becomes limiting.
