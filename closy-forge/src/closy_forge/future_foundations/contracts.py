from __future__ import annotations

import zlib
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes


def build_future_foundations() -> dict[str, Any]:
    fallback = b"closy-public-conventional-fallback-glb-fixture"
    compressed = zlib.compress(fallback, level=9)
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "foundationVersion": "closy.future_foundations.d0.v1",
        "phase10": _zeroone_static(fallback),
        "phase11": _deformation(),
        "phase12": _mobile(fallback, compressed),
        "phase13": _avatar_layering(),
        "phase14": _native_model(),
        "integrity": {"foundationHash": ""},
    }
    document["integrity"]["foundationHash"] = _hash(document)
    issues = validate_future_foundations(document)
    if issues:
        raise ValueError(";".join(issues))
    return document


def validate_future_foundations(document: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    phase10 = document.get("phase10", {})
    phase11 = document.get("phase11", {})
    phase12 = document.get("phase12", {})
    phase13 = document.get("phase13", {})
    phase14 = document.get("phase14", {})
    if (
        phase10.get("actualZeroOneStaticCookExecutedThisInvocation") is not False
        or phase10.get("actualZeroOneStaticArtifactLoaded") is not False
        or phase10.get("cacheValidated") is not False
        or phase10.get("referenceExecutableExecuted") is not True
        or phase10.get("input", {}).get("fallbackHash")
        != phase10.get("output", {}).get("preservedFallbackHash")
        or phase10.get("negotiation", {}).get("acceptedVersion") != "1.0"
    ):
        issues.append("zeroone_static_contract_invalid")
    clusters = phase11.get("influenceClusters", [])
    if (
        len(clusters) != 3
        or any(
            abs(sum(float(weight) for weight in item["weights"].values()) - 1.0) > 1e-9
            for item in clusters
        )
        or phase11.get("dynamicLodHarness", {}).get("actualZeroOneDynamicDeformationExecuted")
        is not False
        or phase11.get("frameUpdateContract", {}).get("normalAndTangentUpdateRequired") is not True
    ):
        issues.append("zeroone_deformation_foundation_invalid")
    if (
        phase12.get("roundTripHash") != phase12.get("sourceHash")
        or phase12.get("streaming", {}).get("resumeByteOffset") != 16
        or phase12.get("evidenceTier", {}).get("deviceRun") is not False
    ):
        issues.append("mobile_runtime_foundation_invalid")
    layers = phase13.get("outfit", {}).get("layers", [])
    if (
        [item.get("collisionOrder") for item in layers] != [10, 20]
        or phase13.get("measurements", {}).get("containsPrivateData") is not False
        or phase13.get("quality", {}).get("boundedTwoGarmentFixture") is not True
    ):
        issues.append("avatar_layering_foundation_invalid")
    if (
        phase14.get("training", {}).get("actualTrainingRun") is not False
        or phase14.get("modelCard", {}).get("weightsAvailable") is not False
        or phase14.get("evaluation", {}).get("benchmarkSuperiorityClaimed") is not False
        or len(phase14.get("rollback", {}).get("failureFixtures", [])) != 3
    ):
        issues.append("native_model_foundation_overclaim")
    if document.get("integrity", {}).get("foundationHash") != _hash(document):
        issues.append("future_foundations_hash_mismatch")
    return issues


def _zeroone_static(fallback: bytes) -> dict[str, Any]:
    fallback_hash = sha256_bytes(fallback)
    return {
        "schemaVersion": 1,
        "contractVersion": "closy.zeroone.offline_static.d0.v1",
        "input": {
            "kind": "closy.garment.public_fixture",
            "fallbackHash": fallback_hash,
            "networkAllowed": False,
        },
        "negotiation": {
            "clientVersions": ["1.0"],
            "referenceExecutableVersions": ["1.0"],
            "acceptedVersion": "1.0",
            "unsupportedVersionFailsClosed": True,
        },
        "output": {
            "status": "reference_passthrough_completed",
            "preservedFallbackHash": fallback_hash,
            "generatedZeroOneBytes": False,
            "reportSchemaVersion": 1,
        },
        "referenceExecutableExecuted": True,
        "referenceExecutableLabel": "deterministic_fake_not_zeroone",
        "actualZeroOneStaticCookExecutedThisInvocation": False,
        "actualZeroOneStaticArtifactLoaded": False,
        "cacheValidated": False,
        "fallbackPreserved": True,
    }


def _deformation() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "contractVersion": "closy.zeroone.deformation_foundation.d0.v1",
        "influenceClusters": [
            {"id": "cluster.chest", "weights": {"spine": 0.35, "chest": 0.65}},
            {"id": "cluster.waist", "weights": {"spine": 0.25, "hips": 0.75}},
            {"id": "cluster.sleeve_left", "weights": {"upperArmL": 0.7, "lowerArmL": 0.3}},
        ],
        "deformedBounds": {
            "units": "metres",
            "minimum": [-0.42, 0.62, -0.18],
            "maximum": [0.42, 1.58, 0.18],
        },
        "frameUpdateContract": {
            "normalAndTangentUpdateRequired": True,
            "tangentHandednessPreserved": True,
            "degenerateFrameFailsClosed": True,
        },
        "fixtures": {
            "crackThresholdMeters": 0.01,
            "measuredCrackMeters": 0.004,
            "cullingBoundsContainDeformedMesh": True,
            "publicMotionFixtureCount": 4,
        },
        "dynamicLodHarness": {
            "lods": [0, 1, 2],
            "topologyStableWithinLod": True,
            "actualZeroOneDynamicDeformationExecuted": False,
        },
    }


def _mobile(source: bytes, compressed: bytes) -> dict[str, Any]:
    decoded = zlib.decompress(compressed)
    return {
        "schemaVersion": 1,
        "contractVersion": "closy.mobile_runtime_foundation.d0.v1",
        "compression": "zlib_reference_not_production_mesh_compression",
        "sourceBytes": len(source),
        "compressedBytes": len(compressed),
        "sourceHash": sha256_bytes(source),
        "roundTripHash": sha256_bytes(decoded),
        "profiles": [
            {"id": "mobile-low", "maxTextureSize": 1024, "fallbackRequired": True},
            {"id": "mobile-standard", "maxTextureSize": 2048, "fallbackRequired": True},
        ],
        "negotiation": {"requested": "mobile-standard", "selected": "mobile-standard"},
        "streaming": {
            "chunkBytes": 8,
            "receivedChunks": 2,
            "resumeByteOffset": 16,
            "idempotentResume": True,
            "fallbackRetainedUntilDecode": True,
        },
        "evidenceTier": {
            "deterministicDecodeTest": True,
            "deviceRun": False,
            "batteryMeasured": False,
            "thermalMeasured": False,
            "frameTimeMeasured": False,
        },
    }


def _avatar_layering() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "contractVersion": "closy.personalised_avatar_layering.d0.v1",
        "measurements": {
            "units": "metres",
            "height": {"value": 1.72, "confidence": 0.92, "source": "synthetic_fixture"},
            "chestCircumference": {
                "value": 0.91,
                "confidence": 0.82,
                "source": "synthetic_fixture",
            },
            "waistCircumference": {
                "value": 0.74,
                "confidence": 0.84,
                "source": "synthetic_fixture",
            },
            "containsPrivateData": False,
        },
        "correction": {"field": "waistCircumference", "deltaMeters": 0.01, "bounded": True},
        "easeControls": {"topEaseMeters": 0.035, "outerwearEaseMeters": 0.065},
        "outfit": {
            "layers": [
                {"garmentId": "garment.synthetic.base_top", "collisionOrder": 10},
                {"garmentId": "garment.synthetic.outer_jacket", "collisionOrder": 20},
            ],
            "minimumLayerClearanceMeters": 0.012,
        },
        "quality": {
            "boundedTwoGarmentFixture": True,
            "orderingValid": True,
            "unresolvedLayerContacts": 0,
            "privateUserFitRun": False,
            "licensedBodyModelRun": False,
        },
    }


def _native_model() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "contractVersion": "closy.native_model_foundation.d0.v1",
        "dataset": {
            "version": "synthetic.garments.d0.v1",
            "licence": "project-authored-synthetic-only",
            "splits": {"train": 8, "validation": 8, "test": 8},
            "privateData": False,
        },
        "modelCard": {
            "modelId": "closy.pattern_model.untrained_contract_v1",
            "intendedDomain": "human_avatar_garments_only",
            "weightsAvailable": False,
            "licenceReviewed": True,
        },
        "training": {
            "command": ["python", "-m", "closy_train", "--config", "synthetic-d0.json"],
            "reproducibilityFields": ["seed", "datasetVersion", "codeCommit", "environmentLock"],
            "actualTrainingRun": False,
        },
        "evaluation": {
            "baseline": "deterministic_template_retrieval",
            "metrics": ["grammarValidity", "panelCountAccuracy", "openingValidity"],
            "benchmarkSuperiorityClaimed": False,
        },
        "rollback": {
            "policy": "retain_last_valid_deterministic_template",
            "failureFixtures": ["invalid_grammar", "nonfinite_geometry", "out_of_domain_object"],
            "failureModelEvaluationExecuted": True,
        },
    }


def _hash(document: dict[str, Any]) -> str:
    payload = deepcopy(document)
    payload["integrity"]["foundationHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
