from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .common import canonical_digest
from .corpus import SessionSpec

ISOLATION_VERSION = "closy.capture_future_d0_isolation_prerequisites.v1"
FORBIDDEN_CONTESTANT_KEYS = frozenset(
    {
        "targetParameters",
        "generatorSeed",
        "exactCamera",
        "exactCrop",
        "renderer",
        "rendererCameraFamily",
        "evaluatorTarget",
        "identityGroupId",
    }
)
FORBIDDEN_CONTESTANT_MODULES = (
    "capture_engineering_v1.corpus",
    "capture_engineering_v1.evidence",
    "exact_d0",
    "d0_disjoint",
)


def contestant_payload(
    *,
    decoded_rgba: bytes,
    width: int,
    height: int,
    view_role: str,
    metadata: Mapping[str, object],
    allowed_metadata: Sequence[str],
) -> dict[str, Any]:
    allowed = set(allowed_metadata)
    payload: dict[str, Any] = {
        "decodedRgba": decoded_rgba,
        "width": width,
        "height": height,
        "viewRole": view_role,
        "coarseMetadata": {key: metadata[key] for key in sorted(metadata) if key in allowed},
    }
    assert_contestant_payload(payload)
    return payload


def assert_contestant_payload(payload: Mapping[str, object]) -> None:
    keys = set(payload)
    metadata = payload.get("coarseMetadata")
    if isinstance(metadata, Mapping):
        keys.update(map(str, metadata))
    leaked = sorted(keys & FORBIDDEN_CONTESTANT_KEYS)
    if leaked:
        raise ValueError("contestant_payload_leak:" + ",".join(leaked))


def audit_contestant_source(source_paths: Sequence[Path]) -> dict[str, Any]:
    imports: set[str] = set()
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    forbidden = sorted(
        name
        for name in imports
        if any(fragment in name for fragment in FORBIDDEN_CONTESTANT_MODULES)
    )
    return {
        "sourceCount": len(source_paths),
        "imports": sorted(imports),
        "forbiddenImports": forbidden,
        "targetImplementationImportableByContestant": bool(forbidden),
        "status": "pass" if not forbidden else "fail",
    }


def future_d0_prerequisite_report(
    specs: Sequence[SessionSpec], *, contestant_source_paths: Sequence[Path]
) -> dict[str, Any]:
    development = [spec for spec in specs if spec.split == "development"]
    validation = [spec for spec in specs if spec.split == "validation"]
    held_out_facets = {
        "rendererCameraFamily": _disjoint(
            development, validation, lambda spec: spec.renderer_camera_family
        ),
        "avatarShapeFamily": _disjoint(
            development, validation, lambda spec: spec.avatar_shape_family
        ),
        "poseFamily": _disjoint(development, validation, lambda spec: spec.pose_family),
        "appearanceFamily": _disjoint(development, validation, lambda spec: spec.appearance_family),
    }
    source_audit = audit_contestant_source(contestant_source_paths)
    identity_ids = {spec.identity_group_id for spec in specs}
    identity_separation = all(value.startswith("capture-group-v1-") for value in identity_ids)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "isolationVersion": ISOLATION_VERSION,
        "qualificationRun": False,
        "developmentEvidenceOnly": True,
        "pr58IdentityReuse": not identity_separation,
        "identityNamespace": "capture-group-v1-*",
        "identityCount": len(identity_ids),
        "heldOutWholeFamilies": held_out_facets,
        "independentRenderers": {
            "count": 2,
            "implementations": [
                "closy.inspection.cpu_raster.scanline_triangle_zbuffer",
                "closy.capture_engineering.independent_per_pixel_ray_triangle",
            ],
            "sameRasterizerAtDifferentResolution": False,
            "sharedRasterizerCode": False,
            "sharedUpstreamMeshContractsDisclosed": True,
        },
        "variedFactors": [
            "avatar_body",
            "pose",
            "camera",
            "light",
            "background",
            "occlusion",
            "garment_parameters",
            "appearance",
        ],
        "contestantBoundary": source_audit,
        "futureHiddenRecordsOutsideContestantHistory": True,
        "futureQualificationAuthorityConsumed": False,
        "status": (
            "pass"
            if identity_separation
            and all(held_out_facets.values())
            and source_audit["status"] == "pass"
            else "fail"
        ),
        "reportDigest": "",
    }
    report["reportDigest"] = canonical_digest(report, "reportDigest")
    return report


def _disjoint(
    development: Sequence[SessionSpec],
    validation: Sequence[SessionSpec],
    selector: Any,
) -> bool:
    return not ({selector(spec) for spec in development} & {selector(spec) for spec in validation})
