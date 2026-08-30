from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from closy_forge.layer_collision.fixtures import (
    build_layer_collision_capability_manifest,
    run_layer_collision_suite,
)
from closy_forge.package_io.canonical_json import canonical_dumps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = build_layer_collision_capability_manifest()
    suite = run_layer_collision_suite()
    evidence = {
        "schemaVersion": 1,
        "evidenceVersion": "closy.layer_collision_evidence.d0.v1",
        "scope": "source_only_LayerCollision-D0_CPU_project_authored_shells",
        "capabilityManifest": manifest,
        "suite": suite,
        "status": "pass" if _suite_passed(suite) else "fail",
        "integrationTruth": {
            "integratedPhase13Acceptance": False,
            "phase11DynamicExecuted": False,
            "z2Executed": False,
            "phy1Passed": False,
        },
        "knownLimitations": [
            "radial-shell CPU reference is not production cloth or visual-quality evidence",
            "no integrated dynamic/runtime/Phase13 lineage",
            "no GPU, mobile, battery, thermal, private-user, licensed-body, "
            "or human-review evidence",
        ],
    }
    _write(root / "docs/layer_collision_d0_capability_v1.json", manifest)
    _write(root / "docs/evidence/layer_collision_d0_v1.json", evidence)
    summary = suite["summary"]
    print(
        f"accepted={summary['acceptedPassCount']}/{summary['acceptedCaseCount']} "
        f"rejections={summary['rejectionPassCount']}/{summary['rejectionCaseCount']} "
        f"status={evidence['status']}"
    )
    return 0 if evidence["status"] == "pass" else 1


def _suite_passed(suite: dict[str, Any]) -> bool:
    summary = suite["summary"]
    return bool(
        suite["inventoryExact"]
        and summary["acceptedPassCount"] == summary["acceptedCaseCount"]
        and summary["rejectionPassCount"] == summary["rejectionCaseCount"]
        and summary["allSimultaneousSolvesExecuted"]
        and summary["allDifferentMaterialsExecuted"]
    )


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_dumps(value).rstrip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
