from pathlib import Path

from closy_forge.capture_engineering_v1.common import read_mapping
from closy_forge.capture_engineering_v1.evidence import verify_generated_evidence

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "capture_camera_material_engineering_v1"
)


def test_persisted_capture_evidence_is_complete_and_truthfully_partial() -> None:
    assert verify_generated_evidence(EVIDENCE) == []
    summary = read_mapping(EVIDENCE / "summary.json")
    capture = read_mapping(EVIDENCE / "capture_decode_qc_camera.json")
    fitting = read_mapping(EVIDENCE / "fitting_and_family_breadth.json")
    uv = read_mapping(EVIDENCE / "uv_appearance.json")
    isolation = read_mapping(EVIDENCE / "future_d0_v5_prerequisites.json")
    assert summary["literalResult"] == "development_acceptance_partial"
    assert capture["attemptedSessionCount"] == 80
    assert capture["actualEncodedVideoClipCount"] == 12
    assert capture["minimumSourceFramesPerVideo"] == 24
    assert fitting["attemptedValidationIdentityCount"] == 20
    assert fitting["statusCounts"] == {"invalid_package": 12, "valid": 8}
    assert all(row["compilerTopologySolverExecuted"] for row in fitting["rows"])
    assert fitting["learnedPlusFitBeatsDeterministicPixelFit"] is True
    assert fitting["developmentCriteriaPassed"] is False
    assert uv["statusCounts"] == {"pass": 20}
    assert isolation["qualificationRun"] is False
    assert isolation["status"] == "pass"
    assert all(value is False for value in summary["promotions"].values())
