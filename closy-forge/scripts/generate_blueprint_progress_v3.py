"""Read saved sources only. Emit to stdout; never update historical/current pointers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from closy_forge.blueprint_progress_v3 import build_requirement_inventory
from closy_forge.blueprint_progress_v3.checkpoint import (
    BLUEPRINT_PATH,
    phase_overview,
    render_phase_table,
)
from closy_forge.blueprint_progress_v3.crosswalk import build_migration_crosswalk


def generate_report(forge_root: Path) -> dict[str, Any]:
    text = (forge_root / BLUEPRINT_PATH).read_text(encoding="utf-8")
    payload = text.encode("utf-8")
    oid = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
    inventory = build_requirement_inventory(text, source_blob_oid=oid)
    paths = (
        "docs/evidence/static_zeroone_runtime_v2/blueprint_inventory.json",
        "docs/blueprint_coverage.json",
    )
    historical = [json.loads((forge_root / path).read_text(encoding="utf-8")) for path in paths]
    migration = build_migration_crosswalk(
        inventory,
        historical_239=historical[0],
        historical_101=historical[1],
    )
    return {
        "reportVersion": "closy.blueprint_progress_report.v3",
        "inventory": inventory,
        "migration": migration,
        "phaseOverview": phase_overview(),
        "inputPolicy": "UTF-8 source with LF normalization; OID identifies that exact content",
        "historicalInputPaths": list(paths),
        "historicalInputSha256": {
            path: hashlib.sha256((forge_root / path).read_bytes()).hexdigest() for path in paths
        },
        "sourceMatchesHistorical239": oid == historical[0].get("sourceGitBlobOid"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--format", choices=("json", "summary", "markdown"), default="summary")
    args = parser.parse_args()
    report = generate_report(args.forge_root)
    if args.format == "markdown":
        print("# Blueprint Progress V3\n\nPR66 baseline; no new unit outcomes incorporated.\n")
        print(render_phase_table())
    elif args.format == "summary":
        inventory = report["inventory"]
        print(
            json.dumps(
                {
                    "parserVersion": inventory["parserVersion"],
                    "sourceGitBlobOid": inventory["sourceGitBlobOid"],
                    "sourceMatchesHistorical239": report["sourceMatchesHistorical239"],
                    "sourceBlockCounts": inventory["sourceBlockCounts"],
                    "statusCounts": inventory["statusCounts"],
                    "migrationCounts": report["migration"]["counts"],
                    "phaseSummaries": inventory["phaseSummaries"],
                    "caveat": report["migration"]["statusPolicy"],
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
