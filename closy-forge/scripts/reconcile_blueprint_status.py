from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.blueprint.status import build_status_model, render_status_summary

EVIDENCE_ANCHOR = "628738e5e8bc2da89be2ae1c349d9a2a220d8839"
VERSION = "closy.blueprint_coverage.integrity_reconciliation.v1"
GENERATED_BY = "Canonical C3 reconciliation from exact implementation head " + EVIDENCE_ANCHOR

NEXT_ACTIONS = {
    "BP-05-04-ZEROONE-OPTIONAL": (
        "Run and validate the task-owned headless ZeroOne static processor, retaining all output "
        "as optional hash-linked derivatives."
    ),
    "BP-47-INSPECTION-ARTIFACTS": (
        "Add validation-time rerendering and independent hidden synthetic targets before broader "
        "fidelity acceptance."
    ),
    "BP-48-PERSISTED-FRAMES-TANGENTS": (
        "Validate independently reconstructed dense and fallback frames over real stitched-shell "
        "deformation states."
    ),
    "BP-49-RASTER-INGESTION-PRIVACY": (
        "Retain fixture-only capture authority while completing bounded JPEG decode and deletion "
        "safety; private-user Gate P1 remains not run."
    ),
    "BP-50-PIXEL-PARSING-CORRECTIONS": (
        "Evaluate parsing and correction contracts on identity-disjoint hidden targets; automated "
        "fixtures remain simulated corrections."
    ),
    "BP-51-MULTIVIEW-CAPTURE-FUSION": (
        "Add independent public/provider capture evidence without exposing target program identity."
    ),
    "BP-52-IMAGE-CONDITIONED-FITTING": (
        "Evaluate the trained synthetic D0 grammar model on identity-disjoint hidden targets and "
        "retain deterministic fitting fallback."
    ),
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": (
        "Validate appearance against independently authored target rasters and authorised source "
        "tiers without treating generated fill as source evidence."
    ),
    "BP-08-A-INGESTION": (
        "Complete bounded JPEG pixel decode and preserve fixture/private evidence separation."
    ),
    "BP-08-C-SEGMENTATION": (
        "Evaluate masks on identity-disjoint hidden targets and later authorised capture tiers."
    ),
    "BP-08-E-MULTIVIEW-FUSION": (
        "Evaluate fusion on identity-disjoint hidden synthetic targets and later authorised "
        "captures."
    ),
    "BP-08-H-PATTERN-INFERENCE": (
        "Train and evaluate a grammar-constrained model on identity-disjoint project-authored data."
    ),
    "BP-08-I-GEOMETRY-PROVIDERS": (
        "Run the owned ZeroOne headless static processor on corrected canonical packages; keep "
        "provider derivatives non-authoritative."
    ),
    "BP-08-K-CLOTH-SIMULATION": (
        "Close the scoped XPBD collision gate without filtering contacts, then gather broader "
        "provider, motion, and hardware evidence."
    ),
    "BP-08-L-FIT-REFINEMENT": (
        "Evaluate learned and deterministic fit routes on identity-disjoint hidden synthetic "
        "targets."
    ),
    "BP-08-M-MESH-ANALYSIS": (
        "Apply concave-safe topology validation to every family and validate real ZeroOne "
        "derivatives."
    ),
    "BP-08-P-TEXTURE-PBR": (
        "Add independent source-tier fidelity and mobile runtime evidence without overclaiming "
        "generated fixture appearance."
    ),
    "BP-08-Q-MATERIAL-INFERENCE": (
        "Complete per-family applicability and calibrated physical evidence beyond authored D0 "
        "presets."
    ),
    "BP-08-U-QUALITY-PROVENANCE": (
        "Regenerate evidence from corrected topology, XPBD, independent fidelity, and real "
        "ZeroOne runs."
    ),
    "BP-09-GEOMOTREE": (
        "Implement and validate the task-owned ZeroOne static garment processor against pinned "
        "Closy packages."
    ),
    "BP-12-MODEL-STRATEGY": (
        "Evaluate the project-owned trained synthetic grammar model and real ZeroOne static "
        "processor; "
        "retain licence and evidence-tier boundaries."
    ),
    "BP-14-EVALUATION": (
        "Use authoritative independent C3, fidelity, learned-model, and ZeroOne reports rather "
        "than stale prose."
    ),
    "BP-17-PHASE-02": (
        "Keep Phase 2 partial while adding independent and authorised capture tiers beyond D0 "
        "fixtures."
    ),
    "BP-17-PHASE-03": (
        "Evaluate fitting on identity-disjoint hidden targets and authorised capture tiers."
    ),
    "BP-17-PHASE-04": (
        "Validate texture/PBR fidelity against independent targets and authorised source tiers."
    ),
    "BP-17-PHASE-06": (
        "Resolve stitched-shell body clearance/source correspondence and bring recomputed "
        "self-collision residual depth within the declared D0 budget."
    ),
    "BP-17-PHASE-08": (
        "Retain package-contract-complete D0 fixture verticals while adding continuous collision, "
        "provider, private, hardware, and human-review evidence."
    ),
    "BP-17-PHASE-10": (
        "Invoke and validate the pinned task-owned ZeroOne static executable; contract fixtures "
        "alone "
        "do not count as runtime execution."
    ),
    "BP-17-PHASE-11": (
        "Begin actual dynamic deformation only after scoped C3 and real ZeroOne static gates pass."
    ),
    "BP-18-GATE-C3": (
        "Resolve stitched-shell body clearance/source correspondence and zero or budget the "
        "remaining recomputed collision penetrations without widening thresholds."
    ),
    "BP-20-RESEARCH-PROTOTYPE": (
        "Integrate corrected topology, scoped C3, trained synthetic D0 inference, and real ZeroOne "
        "static "
        "execution while retaining unsupported tiers."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate canonical blueprint status artifacts.")
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    docs = args.docs.resolve()
    coverage_path = docs / "blueprint_coverage.json"
    stack_path = docs / "pr_stack_manifest.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["version"] = VERSION
    coverage["generatedBy"] = GENERATED_BY
    for row in coverage["rows"]:
        row_id = str(row["id"])
        if row_id in NEXT_ACTIONS:
            row["nextAction"] = NEXT_ACTIONS[row_id]
        if row_id.startswith("BP-09-Z"):
            row["nextAction"] = (
                "Implement and validate the scoped task-owned ZeroOne garment path; do not infer "
                "global gate completion from repository access."
            )
    coverage_path.write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    stack = json.loads(stack_path.read_text(encoding="utf-8"))
    model = build_status_model(coverage, stack, evidence_anchor_sha=EVIDENCE_ANCHOR)
    (docs / "current_blueprint_status.json").write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (docs / "BLUEPRINT_STATUS_SUMMARY.md").write_text(
        render_status_summary(model), encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
