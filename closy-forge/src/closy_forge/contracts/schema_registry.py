from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def schema_registry() -> dict[str, dict[str, Any]]:
    base_object = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["schemaVersion"],
        "properties": {"schemaVersion": {"const": SCHEMA_VERSION}},
    }
    schemas = {
        "common.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/common.schema.json",
            "title": "Closy common coordinate and artifact fields",
        },
        "garment-manifest.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/garment-manifest.schema.json",
            "title": "Closy garment package manifest",
            "additionalProperties": False,
            "required": [
                "schemaVersion",
                "packageKind",
                "garmentId",
                "garmentClass",
                "coordinateConvention",
                "inventory",
                "canonicalPackageDigest",
                "capabilities",
            ],
            "properties": {
                "schemaVersion": {"const": SCHEMA_VERSION},
                "packageKind": {"const": "closy.garment"},
                "garmentId": {"type": "string"},
                "displayName": {"type": "string"},
                "garmentClass": {"const": "tshirt"},
                "units": {"const": "metres"},
                "coordinateConvention": {"type": "object"},
                "status": {"type": "string"},
                "avatar": {"type": "object"},
                "canonicalPaths": {"type": "object"},
                "hashes": {"type": "object"},
                "inventory": {"type": "array"},
                "canonicalDigestDefinition": {"type": "object"},
                "canonicalPackageDigest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "algorithmVersions": {"type": "object"},
                "seed": {"type": "integer"},
                "buildProfile": {"type": "object"},
                "capabilities": {"type": "object"},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "zeroOne": {"type": "object"},
                "extensions": {"type": "object"},
            },
        },
        "provenance.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/provenance.schema.json",
            "title": "Closy deterministic provenance graph",
        },
        "avatar-contract.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/avatar-contract.schema.json",
            "title": "Closy avatar contract",
        },
        "avatar-body-regions.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/avatar-body-regions.schema.json",
            "title": "Closy avatar landmarks, body regions, and collision primitives",
        },
        "semantic-graph.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/semantic-graph.schema.json",
            "title": "Closy garment semantic graph",
        },
        "pattern.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/pattern.schema.json",
            "title": "Closy garment pattern panels, curves, seams, and openings",
        },
        "simulation-mesh-manifest.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/simulation-mesh-manifest.schema.json",
            "title": "Closy garment simulation mesh manifest",
        },
        "constraints.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/constraints.schema.json",
            "title": "Closy garment seam constraints",
        },
        "material-physics.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/material-physics.schema.json",
            "title": "Closy authored material physics preset",
        },
        "render-mesh-manifest.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/render-mesh-manifest.schema.json",
            "title": "Closy garment render mesh manifest",
        },
        "render-materials.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/render-materials.schema.json",
            "title": "Closy garment render materials",
        },
        "binding-manifest.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/binding-manifest.schema.json",
            "title": "Closy sim-to-render binding manifest",
        },
        "validation-report.schema.json": {
            **base_object,
            "$id": "https://closy.local/schemas/v1/validation-report.schema.json",
            "title": "Closy package validation issues and report",
        },
    }
    return schemas
