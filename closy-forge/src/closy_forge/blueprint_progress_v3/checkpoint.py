"""Editorial PR66 baseline, inspected locally, not an evaluator or live GitHub claim."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

BASELINE_HEAD = "930b3da556c96e9ded52b6ee8df5620d4903c280"
BASELINE_TREE = "1aee06f2d65bd66a08c63e30ad47ceb65c85a590"
BLUEPRINT_PATH = "docs/Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md"


def _phase(
    number: int,
    title: str,
    implementation: str,
    evidence: str,
    unmet: str,
    dependencies: str,
    code: str,
    saved: str,
) -> dict[str, Any]:
    return {
        "roadmapPhase": number,
        "title": title,
        "implementationStatus": "partial",
        "supportedScope": implementation,
        "savedEvidenceOutcome": evidence,
        "unmetGates": unmet,
        "dependencies": dependencies,
        "implementationAnchors": [code],
        "evidenceAnchors": [saved],
        "acceptanceStatus": "not_reassessed" if number == 0 else "partial",
        "inspectionBasis": "PR66 local source and saved reports; no evaluator rerun",
    }


_PHASES = [
    _phase(
        0,
        "Contract and deterministic harness",
        "Package reader/writer, hashes, validation, CLI and deterministic T-shirt build exist.",
        "Legacy 101 ledger called this complete within a fixed synthetic fixture scope.",
        "No new exact-head phase acceptance run in this reporting sidecar.",
        "Preserve fixture-specific scope and source provenance.",
        "src/closy_forge/pipeline/build_tshirt_demo.py",
        "docs/blueprint_coverage.json",
    ),
    _phase(
        1,
        "Deterministic T-shirt construction",
        "Pattern panels, seam constraints, triangulation, settling and GLB inspection path.",
        "PR66 includes successful static/conventional T-shirt outputs; not broad physical proof.",
        "Physical convergence and independent drape acceptance remain separate from valid export.",
        "Valid canonical topology, seams and body-clearance evidence.",
        "src/closy_forge/pipeline/build_tshirt_demo.py",
        "docs/evidence/static_zeroone_runtime_v2/result.json",
    ),
    _phase(
        2,
        "Capture and visual understanding",
        "Pixel masks, JPEG/PNG/MJPEG decode, camera estimation and structured correction paths.",
        "PR63: 30 synthetic sessions decoded, 28 fitted/intrinsically valid, 2 QC rejects.",
        "Zero route-eligible sessions; first failure CAPV2-05. Not private-photo readiness.",
        "Better image inference; authorized data, privacy and P1 before real users.",
        "src/closy_forge/capture_reconstruction_v2/contestant.py",
        "docs/evidence/capture_reconstruction_v2/canonical_result_envelope.json",
    ),
    _phase(
        3,
        "T-shirt fitting from images",
        "Bounded pixel-observation fitting compiles and settles three supported families.",
        "PR63's 28 intrinsic packages fail physical quality; 0 route-eligible sessions.",
        "Image-driven fit/camera/physical acceptance failed, not absent implementation.",
        "Phases 1/2 and trustworthy image-to-drape comparison.",
        "src/closy_forge/capture_reconstruction_v2/fitter.py",
        "docs/evidence/capture_reconstruction_v2/canonical_result_envelope.json",
    ),
    _phase(
        4,
        "Texture identity recovery",
        "Fitted-camera projection, source/generated provenance and causal appearance controls.",
        "PR63: 123/150 appearance controls passed in synthetic scope; route quality failed.",
        "Human visual, hidden-region, real-logo and general PBR acceptance unestablished.",
        "Reliable geometry/cameras, licensed observed pixels and independent visual review.",
        "src/closy_forge/capture_reconstruction_v2/appearance.py",
        "docs/evidence/capture_reconstruction_v2/canonical_result_envelope.json",
    ),
    _phase(
        5,
        "Visual-geometry providers",
        "Null/manual provider path; nine authored dense shells cleaned, bound and packaged.",
        "PR65 manual-provider scoped C3 failed; external learned provider remains not_run.",
        "Manual project-owned shells are not open-model or real-provider acceptance.",
        "Approved model weights/runtime/licences and provider fidelity evaluation.",
        "src/closy_forge/manual_provider_c3_v1/package.py",
        "docs/evidence/manual_provider_c3_v1/result.json",
    ),
    _phase(
        6,
        "Robust sim-to-render binding",
        "Lower-resolution cage, serialized barycentric binding, frames and dense/fallback motion.",
        "PR65: 9 shells x 11 states = 99 rows; 16/17 gates; rest max 0.0122075879 m.",
        "MPC3-09 failed 0.008 m limit; V1 lattice sampling and zero-offset repair still needed.",
        "General geometry-based binding and independent rest reconstruction; no global C3 claim.",
        "src/closy_forge/manual_provider_c3_v1/binding.py",
        "docs/evidence/manual_provider_c3_v1/result.json",
    ),
    _phase(
        7,
        "Material physics inference",
        "Material-coupled CPU XPBD-centred solver, inference and garment-motion evaluation exist.",
        "PR64: 24 tuples, 576 garment motions; SMV2-01 failed, mean error 0.415668.",
        "Recovery/calibration failed; no measured real fabric. PR62 remains ineligible.",
        "Measured fabric coupons, improved inference and independent physical validation.",
        "src/closy_forge/solver_material_v2/evaluation.py",
        "docs/evidence/solver_material_v2/canonical_result_envelope.json",
    ),
    _phase(
        8,
        "Additional garment families",
        "Nine family builders with distinct templates/semantics; not merely enum entries.",
        "PR66: six static successes; long sleeves, button shirt and jacket fail geometry.",
        "Full Phase 8 needs templates, semantics, capture tests AND simulation for each family.",
        "Parent-owned successor geometry matrix; family capture estimation and physical coverage.",
        "src/closy_forge/pipeline/build_long_sleeved_demo.py",
        "docs/evidence/static_zeroone_runtime_v2/result.json",
    ),
    _phase(
        9,
        "Learned structured patterns",
        "Synthetic training, learned classification/regression, grammar/decoder and corrections.",
        "Saved legacy coverage describes bounded E1/E2 execution, not universal pattern recovery.",
        "No new model evaluation; variable-topology, unseen-data and correction UI gaps remain.",
        "Stable compile/fit gates, authorized diverse data and honest held-out comparisons.",
        "src/closy_forge/pattern_inference/model_v2.py",
        "docs/blueprint_coverage.json",
    ),
    _phase(
        10,
        "ZeroOne offline/static integration",
        "Read-only processor interface, derivative validation and conventional fallback.",
        "PR66: 6/9 static pass; Z4/Z5/Z6/Z8 each 6 pass + 3 blocked; Z3/Z7 6 not_run + 3 blocked.",
        "All-family static readiness failed; count equality alone is not exact surface coverage.",
        "Valid input geometry, available read-only build, triangle/provenance/bounds audits.",
        "src/closy_forge/zeroone/static_stage_audit_v2.py",
        "docs/evidence/static_zeroone_runtime_v2/result.json",
    ),
    _phase(
        11,
        "ZeroOne deformation integration",
        "Dynamic request/integration and mechanical-reference paths exist, distinct from static.",
        "Saved reconciliation blocks Phase 11 on refreshed paired scoped Z1 prerequisites.",
        "Global dynamic gate Z2 not established; section 9.5 stage Z2 is a different concept.",
        "Admissible solver motion, cloth-driven derivatives, bounds/cracks/LOD performance.",
        "src/closy_forge/zeroone/dynamic_integration.py",
        "docs/evidence/phase11_prerequisite_reconciliation_v2.json",
    ),
    _phase(
        12,
        "Mobile/runtime optimisation",
        "Compressed packages, bounded load/decode, rebuilds, analytic poses and resume controls.",
        "PR66: 24/36 valid runtime rows; 12 invalid geometry; 8/9 recovery controls pass.",
        "Cross-package rejected for size, not expected hash; physical device tests not_run.",
        "Geometry checks, trusted manifest identity, distinct corruption controls and devices.",
        "src/closy_forge/runtime_delivery/package_v2.py",
        "docs/evidence/static_zeroone_runtime_v2/result.json",
    ),
    _phase(
        13,
        "Personalised avatar and outfit layering",
        "Synthetic measurement fitting/ease and analytic layer-projection development paths.",
        "Existing fit/layer reports are synthetic; radial solver is not arbitrary package contact.",
        "General package-surface collision and licensed photo-body fit not established.",
        "Outfit meshes, mismatched tessellations, binding, licensed body assets and consent.",
        "src/closy_forge/layer_collision/solver.py",
        "docs/evidence/phase13_synthetic_avatar_fit_v1.json",
    ),
    _phase(
        14,
        "Closy-native trained models",
        "Bounded trained linear material ranker/logistic warning model and fixture dataset.",
        "Saved model evidence is source-only project-authored CPU/advisory scope.",
        "Not a garment foundation model or calibrated physical-material predictor.",
        "Mature authorized data/evaluation, compute, licences and independent provider baselines.",
        "src/closy_forge/bounded_models/model.py",
        "docs/evidence/phase14_bounded_models_v1.json",
    ),
]
_PHASES[0]["implementationStatus"] = "implemented_scoped"


def phase_overview() -> dict[str, Any]:
    return {
        "overviewVersion": "closy.blueprint_phase_overview.pr66.v3",
        "baselinePr": 66,
        "baselineHead": BASELINE_HEAD,
        "baselineTree": BASELINE_TREE,
        "observedDate": "2026-09-05",
        "liveGitHubRechecked": False,
        "newUnitOutcomes": "not incorporated; parent implementation owns subsequent evidence",
        "codeAndCI": "PR66 checkpoint reports 32/32 Forge successes; not rerun by this sidecar",
        "developmentQuality": (
            "capture, material, manual binding and all-family static/runtime failed"
        ),
        "scientificQualification": (
            "No new qualification. Y2 preseed_scientific_protocol_invalid; "
            "Strategy 3 consumed; topology budget 0; canonical candidate budget 1 unchanged."
        ),
        "productReadiness": (
            "No Research Prototype, Alpha/Beta, physical mobile or production grant"
        ),
        "phases": deepcopy(_PHASES),
    }


def render_phase_table() -> str:
    lines = [
        "| Phase | Inspected implementation / scope | Saved evidence | Unmet / dependencies |",
        "|---|---|---|---|",
    ]
    for row in _PHASES:
        code = row["implementationAnchors"][0]
        evidence = row["evidenceAnchors"][0]
        lines.append(
            f"| {row['roadmapPhase']}: {row['title']} | "
            f"[{row['supportedScope']}]({code}) | "
            f"[{row['savedEvidenceOutcome']}]({evidence}) | "
            f"{row['unmetGates']} {row['dependencies']} |"
        )
    return "\n".join(lines) + "\n"
