from __future__ import annotations

import argparse
import platform
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.simulation_topology_v2.evidence import (
    PHY1_TOPOLOGY_V2_EVIDENCE_DIRECTORY,
    PHY1_TOPOLOGY_V2_PROFILE_PATH,
    attach_performance_measurement,
    build_component_audit,
    build_final_d0_research_matrix,
    build_phy1_topology_v2_profile,
    build_topology_manifest,
    build_v2_invalidation_ledger,
    validate_publication,
)
from closy_forge.simulation_topology_v2.phy1_experiment import (
    build_phy1_topology_v2_inputs,
    run_phy1_topology_v2_experiment,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-sha")
    parser.add_argument("--measured-wall-seconds", type=float)
    parser.add_argument("--peak-memory-bytes", type=int)
    parser.add_argument("--cpu-label", default="not_recorded")
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    evidence_directory = root / PHY1_TOPOLOGY_V2_EVIDENCE_DIRECTORY
    paths = {
        "profile": root / PHY1_TOPOLOGY_V2_PROFILE_PATH,
        "report": evidence_directory / "phy1_experiment.json",
        "topology": evidence_directory / "topology_manifest.json",
        "seam": evidence_directory / "seam_junction_audit.json",
        "binding": evidence_directory / "binding_audit.json",
        "ledger": evidence_directory / "invalidation_ledger.json",
        "matrix": evidence_directory / "final_d0_research_prototype_matrix.json",
    }
    if args.validate_committed:
        documents = {name: _object(path) for name, path in paths.items()}
    else:
        if args.source_sha is None or len(args.source_sha) != 40:
            parser.error("--source-sha must be an exact 40-character source anchor")
        if args.measured_wall_seconds is None:
            parser.error(
                "--measured-wall-seconds is required for deterministic performance evidence"
            )
        inputs = build_phy1_topology_v2_inputs()
        report = run_phy1_topology_v2_experiment(source_anchor_sha=args.source_sha)
        report = attach_performance_measurement(
            report,
            measured_wall_seconds=args.measured_wall_seconds,
            peak_memory_bytes=args.peak_memory_bytes,
            environment={
                "cpu": args.cpu_label,
                "os": platform.platform(),
                "python": platform.python_version(),
                "threadCount": 1,
            },
        )
        documents = {
            "profile": build_phy1_topology_v2_profile(root, report, inputs),
            "report": report,
            "topology": build_topology_manifest(report, inputs),
            "seam": build_component_audit(report, inputs.seam_audit, component="seam_junctions"),
            "binding": build_component_audit(
                report, inputs.binding_audit, component="render_binding"
            ),
            "ledger": build_v2_invalidation_ledger(root, report),
            "matrix": build_final_d0_research_matrix(root, report),
        }
        evidence_directory.mkdir(parents=True, exist_ok=True)
        write_canonical_json(
            evidence_directory / ".closy-forge-owned.json",
            {
                "kind": "published",
                "markerVersion": "closy.forge_owned_output.v1",
                "owner": "closy-forge",
                "purpose": "phy1_topology_v2_evidence",
                "schemaVersion": 1,
            },
        )
        for name, path in paths.items():
            write_canonical_json(path, documents[name])
    issues = validate_publication(
        root,
        profile=documents["profile"],
        report=documents["report"],
        ledger=documents["ledger"],
        matrix=documents["matrix"],
    )
    if issues:
        raise ValueError(";".join(issues))
    aggregate = documents["report"]["replay"]["aggregate"]
    print(
        f"status={documents['report']['acceptance']['status']} "
        f"states={aggregate['statePassCount']}/{aggregate['stateCount']} "
        f"temporal={aggregate['qualifiedTemporalCounts']} "
        f"research={documents['matrix']['researchPrototypeStatus']}"
    )
    return 0


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
