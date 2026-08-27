from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

FAMILY_GROUPS = {
    "upper": ("tshirt", "sleeveless", "long-sleeved"),
    "lower": ("simple-skirt", "simple-trousers", "simple-dress"),
    "structured": ("button-shirt", "jacket-outerwear", "layered-asymmetric"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one stable Forge family rebuild shard.")
    parser.add_argument("--group", choices=sorted(FAMILY_GROUPS), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    started = time.perf_counter()
    for family in FAMILY_GROUPS[args.group]:
        command = f"build-{family}"
        left = root / f"{family}_a.closygarment"
        right = root / f"{family}_b.closygarment"
        family_started = time.perf_counter()
        _run("demo", command, "--output", str(left), "--force")
        _run("demo", command, "--output", str(right), "--force")
        _run("packages", "diff", str(left), str(right), "--json")
        _run("validate", str(left))
        _run("report", str(left))
        manifest = json.loads((left / "manifest.json").read_text(encoding="utf-8"))
        validation = json.loads(
            (left / "reports" / "package_validation.json").read_text(encoding="utf-8")
        )
        settle_path = left / "simulation" / "settle_diagnostics.json"
        settle = json.loads(settle_path.read_text(encoding="utf-8")) if settle_path.exists() else {}
        inter_layer_collision = None
        layered_quality_path = left / "reports" / "layered_asymmetric_quality.json"
        if layered_quality_path.exists():
            layered_quality = json.loads(layered_quality_path.read_text(encoding="utf-8"))
            inter_layer_collision = layered_quality.get("layering", {}).get(
                "interLayerCollisionEnabled"
            )
        results.append(
            {
                "canonicalDigest": manifest["packageDigest"],
                "elapsedSeconds": round(time.perf_counter() - family_started, 6),
                "family": family,
                "validationStatus": validation.get("status"),
                "validationErrors": int(validation.get("counts", {}).get("error", 0)),
                "validationFatals": int(validation.get("counts", {}).get("fatal", 0)),
                "physicalQualityAccepted": bool(settle.get("physicalQualityAccepted", False)),
                "interLayerCollisionEnabled": inter_layer_collision,
            }
        )
    summary = {
        "elapsedSeconds": round(time.perf_counter() - started, 6),
        "families": results,
        "group": args.group,
        "python": ".".join(str(value) for value in sys.version_info[:3]),
        "schemaVersion": 1,
    }
    (root / f"family-shard-{args.group}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def _run(*arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "closy_forge", *arguments],
        check=True,
        timeout=1_800,
    )


if __name__ == "__main__":
    raise SystemExit(main())
