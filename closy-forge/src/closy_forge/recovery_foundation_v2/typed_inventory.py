from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

INVENTORY_SOURCES = (
    ("unit_f_g", "fixtures/d0_disjoint_tshirt_benchmark_v1/protocol_lock.json"),
    ("v1_public_revealed", "fixtures/d0_disjoint_tshirt_benchmark_v1/development_lock.json"),
    (
        "phase9_train_validation_test",
        "docs/evidence/phase9_raster_synthetic_d0/corpus_manifest.json",
    ),
    (
        "retrieval_template_golden",
        "docs/evidence/d0_evidence_integrity_v4/raster_semantics_v4.json",
    ),
    ("later_synthetic_studies", "fixtures/d0_strict_c3_confirmation_v5/sentinel_manifest.json"),
    ("v2_public_material", "fixtures/d0_disjoint_tshirt_confirmation_v2/protocol_lock.json"),
)
DOMAINS = {
    "program": {
        "contentKind": "canonical_tshirt_program",
        "canonicalisation": "closy.canonical_json.v1",
        "units": "meters_radians_srgb_unit_interval",
        "coordinateConvention": "closy_right_handed_y_up_meters_v1",
        "hashDomain": "semantic_content",
    },
    "rest_mesh": {
        "contentKind": "rest_simulation_mesh",
        "canonicalisation": "closy.typed_rest_mesh.v1",
        "units": "meters",
        "coordinateConvention": "closy_right_handed_y_up_meters_v1",
        "hashDomain": "semantic_content",
    },
    "simulation_mesh": {
        "contentKind": "simulated_deformed_mesh",
        "canonicalisation": "closy.typed_simulation_mesh.v1",
        "units": "meters",
        "coordinateConvention": "closy_right_handed_y_up_meters_v1",
        "hashDomain": "semantic_content",
    },
    "appearance_logo": {
        "contentKind": "observable_base_colour_logo_identity",
        "canonicalisation": "closy.observable_appearance.v1",
        "units": "uint8_srgb_alpha_and_normalized_logo_coordinates",
        "coordinateConvention": "uv_origin_declared_per_program",
        "hashDomain": "semantic_content",
    },
    "pbr": {
        "contentKind": "bounded_pbr_preset",
        "canonicalisation": "closy.pbr_preset.v1",
        "units": "srgb_and_unit_interval",
        "coordinateConvention": "not_applicable",
        "hashDomain": "semantic_content",
    },
    "raster": {
        "contentKind": "decoded_rgba_capture",
        "canonicalisation": "png_file_bytes_v1",
        "units": "uint8_srgb_alpha",
        "coordinateConvention": "image_top_left_x_right_y_down",
        "hashDomain": "byte_stream",
    },
    "capture": {
        "contentKind": "capture_instance",
        "canonicalisation": "closy.capture_contract.v1",
        "units": "meters_radians_pixels",
        "coordinateConvention": "declared_per_capture",
        "hashDomain": "semantic_content",
    },
}


def build_recoverable_inventory(root: Path) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for source_class, relative in INVENTORY_SOURCES:
        path = root / relative
        if path.is_file():
            sources.append(
                {
                    "sourceClass": source_class,
                    "sourcePath": relative,
                    "availability": "recoverable",
                    "contentKind": "evidence_inventory_source",
                    "canonicalisation": "raw_file_bytes_v1",
                    "units": "not_applicable",
                    "coordinateConvention": "not_applicable",
                    "hashDomain": "byte_stream",
                    "sourceCommit": "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
                    "digestAlgorithm": "sha256",
                    "digest": sha256_file(path),
                    "recordCount": _count_identity_records(read_json(path)),
                }
            )
        else:
            sources.append(
                {
                    "sourceClass": source_class,
                    "sourcePath": relative,
                    "availability": "unavailable",
                    "contentKind": "evidence_inventory_source",
                    "canonicalisation": "raw_file_bytes_v1",
                    "units": "not_applicable",
                    "coordinateConvention": "not_applicable",
                    "hashDomain": "byte_stream",
                    "sourceCommit": "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
                    "digestAlgorithm": "sha256",
                    "digest": None,
                    "recordCount": 0,
                }
            )
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "inventoryVersion": "closy.d0_v3.typed_prior_inventory.v1",
        "domains": DOMAINS,
        "sources": sources,
        "unrecoverableV2OpaqueCohort": {
            "availability": "unrecoverable",
            "acceptedIdentityCountInferredFromControlFlow": 16,
            "artifactAttested": False,
            "seedDigestAvailable": False,
            "identityHashesAvailable": False,
            "commitmentBytesAvailable": False,
            "disjointnessClaimPermitted": False,
        },
        "requiredV3Statement": "disjointFromUnrecoverableV2OpaqueCohort = unverified",
        "inventoryDigest": "",
    }
    document["inventoryDigest"] = _document_digest(document, "inventoryDigest")
    return document


def validate_inventory(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    domains = _mapping(document.get("domains"))
    if set(domains) != set(DOMAINS):
        issues.append("typed_inventory_domain_inventory_invalid")
    for name, definition in domains.items():
        row = _mapping(definition)
        for field in (
            "contentKind",
            "canonicalisation",
            "units",
            "coordinateConvention",
            "hashDomain",
        ):
            if row.get(field) in (None, ""):
                issues.append(f"typed_inventory_domain_field_missing:{name}:{field}")
    sources = _records(document.get("sources"))
    expected_classes = {item[0] for item in INVENTORY_SOURCES}
    actual_classes = [str(row.get("sourceClass", "")) for row in sources]
    if set(actual_classes) != expected_classes:
        issues.append("typed_inventory_source_coverage_invalid")
    if len(actual_classes) != len(set(actual_classes)):
        issues.append("typed_inventory_source_duplicate")
    for row in sources:
        for field in (
            "contentKind",
            "canonicalisation",
            "units",
            "coordinateConvention",
            "hashDomain",
            "sourcePath",
            "sourceCommit",
            "digestAlgorithm",
        ):
            if row.get(field) in (None, ""):
                issues.append(
                    f"typed_inventory_source_field_missing:{row.get('sourceClass')}:{field}"
                )
        if row.get("availability") == "recoverable" and row.get("digest") in (None, ""):
            issues.append(f"typed_inventory_source_digest_missing:{row.get('sourceClass')}")
    opaque = _mapping(document.get("unrecoverableV2OpaqueCohort"))
    if (
        opaque.get("artifactAttested") is not False
        or opaque.get("disjointnessClaimPermitted") is not False
    ):
        issues.append("typed_inventory_opaque_v2_overclaim")
    if document.get("requiredV3Statement") != (
        "disjointFromUnrecoverableV2OpaqueCohort = unverified"
    ):
        issues.append("typed_inventory_opaque_v2_statement_invalid")
    if _document_digest(document, "inventoryDigest") != document.get("inventoryDigest"):
        issues.append("typed_inventory_digest_invalid")
    return sorted(set(issues))


def evaluate_disjointness(
    prior_records: Sequence[Mapping[str, Any]],
    candidate_records: Sequence[Mapping[str, Any]],
    *,
    minimum_parameter_distance: float,
) -> dict[str, Any]:
    prior_garments = {_garment_identity(row) for row in prior_records}
    candidate_garments = [_garment_identity(row) for row in candidate_records]
    capture_ids = [_capture_identity(row) for row in candidate_records]
    duplicate_garments = sorted(
        identity for identity, count in Counter(candidate_garments).items() if count > 1
    )
    duplicate_captures = sorted(
        identity for identity, count in Counter(capture_ids).items() if count > 1
    )
    overlap = sorted(set(candidate_garments) & prior_garments)
    distances = [
        min(
            (_parameter_distance(candidate, prior) for prior in prior_records),
            default=1.0,
        )
        for candidate in candidate_records
    ]
    distance_pass = all(distance >= minimum_parameter_distance for distance in distances)
    return {
        "garmentIdentityPredicate": {
            "duplicateWithinCohort": duplicate_garments,
            "recoverablePriorOverlap": overlap,
            "minimumDistances": distances,
            "threshold": minimum_parameter_distance,
            "pass": not duplicate_garments and not overlap and distance_pass,
        },
        "captureInstancePredicate": {
            "duplicateWithinCohort": duplicate_captures,
            "pass": not duplicate_captures,
        },
        "disjointFromUnrecoverableV2OpaqueCohort": "unverified",
        "overallRecoverableInventoryPass": (
            not duplicate_garments and not overlap and distance_pass and not duplicate_captures
        ),
    }


def _garment_identity(row: Mapping[str, Any]) -> str:
    identity = _mapping(row.get("garmentIdentity"))
    required = (
        "patternParameters",
        "program",
        "panels",
        "seams",
        "openings",
        "restGeometry",
        "simulationGeometry",
        "appearanceLogo",
        "pbrPreset",
    )
    if any(identity.get(field) in (None, "") for field in required):
        raise ValueError("typed_inventory_garment_identity_incomplete")
    payload = {field: identity[field] for field in required}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _capture_identity(row: Mapping[str, Any]) -> str:
    capture = _mapping(row.get("captureIdentity"))
    required = ("camera", "crop", "occlusion", "lighting", "raster")
    if any(capture.get(field) in (None, "") for field in required):
        raise ValueError("typed_inventory_capture_identity_incomplete")
    payload = {field: capture[field] for field in required}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _parameter_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    left_parameters = _mapping(left.get("parameters"))
    right_parameters = _mapping(right.get("parameters"))
    shared = sorted(set(left_parameters) & set(right_parameters))
    if not shared:
        return 1.0
    return max(abs(float(left_parameters[key]) - float(right_parameters[key])) for key in shared)


def _count_identity_records(value: object) -> int:
    if isinstance(value, Mapping):
        total = 0
        for key, child in value.items():
            if key in {
                "developmentIdentities",
                "identities",
                "records",
                "rows",
            } and isinstance(child, list):
                total += len(child)
            else:
                total += _count_identity_records(child)
        return total
    if isinstance(value, list):
        return sum(_count_identity_records(item) for item in value)
    return 0


def _document_digest(document: Mapping[str, Any], field: str) -> str:
    payload = dict(document)
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(item) for item in value] if isinstance(value, list) else []
