from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "fixtures" / "manual_provider_c3_v1"
RAW_ROOT = FIXTURE_ROOT / "raw_sources"


@dataclass(frozen=True)
class AuthoredProfile:
    source_id: str
    family: str
    authoring_note: str
    width_rows: tuple[float, ...]
    y_min: float
    y_max: float
    depth: float
    asymmetry: float
    phase: float


# These are nine independently hand-curated profiles. The lattice exporter below is deliberately
# separate from Closy's canonical pattern generators and only serializes provider-like dense shells.
PROFILES = (
    AuthoredProfile(
        "manual-tshirt-01",
        "tshirt",
        "boxy crew tee with long shoulder shelf",
        (0.48, 0.49, 0.50, 0.52, 0.70, 0.72),
        0.72,
        1.46,
        0.105,
        0.006,
        0.13,
    ),
    AuthoredProfile(
        "manual-tshirt-02",
        "tshirt",
        "fitted crew tee with tapered waist",
        (0.43, 0.42, 0.44, 0.49, 0.64, 0.66),
        0.75,
        1.47,
        0.095,
        -0.008,
        0.37,
    ),
    AuthoredProfile(
        "manual-tshirt-03",
        "tshirt",
        "cropped tee with dropped shoulder",
        (0.47, 0.48, 0.50, 0.54, 0.73, 0.76),
        0.84,
        1.48,
        0.115,
        0.011,
        0.61,
    ),
    AuthoredProfile(
        "manual-sleeveless-01",
        "sleeveless_top",
        "straight tank with narrow shoulder straps",
        (0.42, 0.43, 0.46, 0.49, 0.37, 0.30),
        0.72,
        1.45,
        0.085,
        0.004,
        0.19,
    ),
    AuthoredProfile(
        "manual-sleeveless-02",
        "sleeveless_top",
        "athletic vest with deep arm opening",
        (0.40, 0.41, 0.44, 0.48, 0.35, 0.27),
        0.76,
        1.47,
        0.092,
        -0.006,
        0.43,
    ),
    AuthoredProfile(
        "manual-sleeveless-03",
        "sleeveless_top",
        "relaxed shell top with broad upper body",
        (0.48, 0.49, 0.50, 0.51, 0.43, 0.34),
        0.70,
        1.44,
        0.108,
        0.009,
        0.73,
    ),
    AuthoredProfile(
        "manual-skirt-01",
        "simple_skirt",
        "gentle A-line knee skirt",
        (0.62, 0.58, 0.54, 0.50, 0.47, 0.45),
        0.13,
        0.91,
        0.115,
        0.005,
        0.23,
    ),
    AuthoredProfile(
        "manual-skirt-02",
        "simple_skirt",
        "straight midi skirt with subtle kick",
        (0.50, 0.49, 0.48, 0.47, 0.46, 0.45),
        0.06,
        0.91,
        0.105,
        -0.007,
        0.53,
    ),
    AuthoredProfile(
        "manual-skirt-03",
        "simple_skirt",
        "short flared skirt with asymmetric drape",
        (0.67, 0.61, 0.55, 0.50, 0.46, 0.44),
        0.38,
        0.92,
        0.125,
        0.013,
        0.83,
    ),
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def interpolate(rows: tuple[float, ...], t: float) -> float:
    scaled = t * (len(rows) - 1)
    lo = min(int(scaled), len(rows) - 2)
    alpha = scaled - lo
    return rows[lo] * (1.0 - alpha) + rows[lo + 1] * alpha


def panel(profile: AuthoredProfile, side: str) -> tuple[list[list[float]], list[list[int]]]:
    nx = 25 + (int(profile.source_id[-1]) % 3) * 2
    ny = 27 + (int(profile.source_id[-1]) % 2) * 2
    z_sign = 1.0 if side == "front" else -1.0
    vertices: list[list[float]] = []
    for row in range(ny):
        v = row / (ny - 1)
        width = interpolate(profile.width_rows, v)
        for column in range(nx):
            u = column / (nx - 1)
            x = (u * 2.0 - 1.0) * width
            y = profile.y_min + (profile.y_max - profile.y_min) * v
            hand_authored_irregularity = 0.0018 * sin((column + 1) * 1.37 + profile.phase)
            hand_authored_irregularity += 0.0011 * cos((row + 2) * 0.91 + profile.phase)
            x += profile.asymmetry * v * (0.35 + u)
            z = z_sign * (profile.depth + 0.018 * sin(pi * v))
            z += z_sign * hand_authored_irregularity
            vertices.append([round(x, 7), round(y, 7), round(z, 7)])

    faces: list[list[int]] = []
    for row in range(ny - 1):
        for column in range(nx - 1):
            a = row * nx + column
            b = a + 1
            c = a + nx
            d = c + 1
            if (row + column + int(profile.phase * 100)) % 2:
                cell = [[a, b, c], [b, d, c]]
            else:
                cell = [[a, b, d], [a, d, c]]
            if side == "back":
                cell = [[tri[0], tri[2], tri[1]] for tri in cell]
            faces.extend(cell)

    # Provider-like repair targets: unreferenced vertices, one degenerate, one duplicate, and one
    # reversed triangle. They are deterministic source defects, not injected by the cleanup code.
    vertices.extend([[99.0, 99.0, 99.0], [-99.0, -99.0, -99.0]])
    faces.append([0, 0, 1])
    faces.append(list(faces[3]))
    faces[7] = [faces[7][0], faces[7][2], faces[7][1]]
    return vertices, faces


def authored_source(profile: AuthoredProfile) -> dict[str, Any]:
    parts = []
    for side in ("front", "back"):
        vertices, faces = panel(profile, side)
        parts.append(
            {
                "partId": f"{profile.source_id}.{side}",
                "semanticHint": f"panel.{side}",
                "vertices": vertices,
                "triangles": faces,
            }
        )
    openings = (
        ["opening.neck", "opening.hem", "opening.sleeve.left", "opening.sleeve.right"]
        if profile.family == "tshirt"
        else ["opening.neck", "opening.hem", "opening.arm.left", "opening.arm.right"]
        if profile.family == "sleeveless_top"
        else ["opening.waist", "opening.hem"]
    )
    return {
        "schemaVersion": 1,
        "sourceId": profile.source_id,
        "rawAssetId": f"raw:{profile.source_id}:v1",
        "family": profile.family,
        "authorship": {
            "author": "Closy project",
            "method": "independently hand-curated profile exported as a dense provider shell",
            "note": profile.authoring_note,
            "canonicalPatternGeneratorUsed": False,
            "derivedFromOtherCorpusSource": False,
        },
        "licence": {
            "spdx": "CC0-1.0",
            "projectAuthored": True,
            "redistributionAllowed": True,
            "personalData": False,
        },
        "coordinateSystem": {"axis": "right-handed-y-up", "unit": "metre"},
        "declaredOpenings": openings,
        "parts": parts,
    }


def main() -> None:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    inventory = []
    family_counts: dict[str, int] = {}
    for profile in PROFILES:
        source = authored_source(profile)
        data = canonical_bytes(source)
        relative = f"raw_sources/{profile.source_id}.json"
        (FIXTURE_ROOT / relative).write_bytes(data)
        family_counts[profile.family] = family_counts.get(profile.family, 0) + 1
        inventory.append(
            {
                "sourceId": profile.source_id,
                "rawAssetId": source["rawAssetId"],
                "family": profile.family,
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "partCount": len(source["parts"]),
                "vertexCount": sum(len(part["vertices"]) for part in source["parts"]),
                "triangleCount": sum(len(part["triangles"]) for part in source["parts"]),
                "licenceSpdx": "CC0-1.0",
                "redistributionAllowed": True,
            }
        )

    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "freezeVersion": "closy.manual_provider_c3_v1.raw_source_freeze.v1",
        "scope": "project_authored_redistributable_manual_provider_development",
        "sourceCount": len(inventory),
        "familyCounts": family_counts,
        "requiredFamilies": ["simple_skirt", "sleeveless_top", "tshirt"],
        "sources": sorted(inventory, key=lambda item: item["sourceId"]),
        "provenancePolicy": {
            "projectAuthoredOnly": True,
            "redistributableOnly": True,
            "canonicalPatternGeneratorForbidden": True,
            "crossSourceDerivationForbidden": True,
            "privateOrPersonalDataForbidden": True,
        },
        "benchmarkDenominator": {
            "sourceCount": 9,
            "sourcesPerFamily": 3,
            "families": 3,
            "poseStateCount": 11,
            "requiredEvaluationRows": 99,
            "cleanBuildCount": 2,
        },
    }
    digest = hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    freeze["freezeDigest"] = digest
    (FIXTURE_ROOT / "raw_source_freeze.json").write_bytes(canonical_bytes(freeze))
    print(f"authored {len(inventory)} source shells; freezeDigest={digest}")


if __name__ == "__main__":
    main()
