from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "phase9_raster_synthetic_d0"


def test_committed_phase9_raster_evidence_is_bounded_and_fail_closed() -> None:
    summary = _read("execution_summary.json")
    corpus = _read("corpus_manifest.json")
    split = _read("split.json")
    evaluation = _read("evaluation.json")
    downstream = _read("downstream_execution.json")

    assert summary["closySha"] == "fdcdfb22c02c796b97ee6406bbd76025a645822f"
    assert summary["scope"] == "project_authored_synthetic_raster_unassisted_host_cpu_d0"
    assert summary["corpusHash"] == (
        "d0b31b71b733952c9c8513b25293e8cc07018638d8a7ab65ffc9068b17cd5847"
    )
    assert summary["globalPhase9"] == "partial"
    assert summary["humanCorrectionStatus"] == "not_run"
    assert summary["privateUserEvidence"] is False
    assert summary["realPhotoEvidence"] is False

    assert corpus["programCount"] == 96
    assert corpus["captureCount"] == 384
    assert corpus["viewCount"] == 1536
    assert corpus["rawRasterBytesCommitted"] is False
    assert corpus["privateSeedProvenanceCommitted"] is False
    assert len(split["samples"]["train"]) == 256
    assert len(split["samples"]["validation"]) == 64
    assert len(split["samples"]["test"]) == 64
    assert split["identityComputedBeforeAugmentation"] is True

    primary = evaluation["primary"]
    assert primary["familyTemplate"]["top1Accuracy"] == 0.828125
    assert primary["familyTemplate"]["top3Accuracy"] == 1.0
    assert primary["comparison"]["baselineTop1Accuracy"] == 0.90625
    assert primary["comparison"]["learnedSuperioritySupported"] is False
    assert primary["ood"]["rejectionAccuracy"] == 0.0
    assert evaluation["controls"]["labelPermutation"]["top1Accuracy"] == 0.0
    assert evaluation["controls"]["pixelsDestroyed"]["top1Accuracy"] == 0.125
    assert evaluation["controls"]["metadataOnly"]["top1Accuracy"] == 0.125
    assert evaluation["leakageAudits"]["deliberateLeakageFixtureRejected"] is True
    assert evaluation["leakageAudits"]["duplicatePixelHashes"] == 0
    assert evaluation["claims"]["globalPhase9Complete"] is False

    assert downstream["familyCount"] == 8
    assert downstream["E1"]["status"] == "partial"
    assert downstream["E1"]["allPackagesValidated"] is True
    assert downstream["E1"]["allRerendered"] is True
    assert downstream["E2"] == {
        "reason": "fixed_template_retrieval_and_adaptation_only",
        "status": "not_run",
    }
    assert sum(bool(record["learnedFitRun"]) for record in downstream["records"]) == 4
    assert all(record["package"]["validation"] == "passed" for record in downstream["records"])
    jacket = next(
        record for record in downstream["records"] if record["targetFamily"] == "jacket_outerwear"
    )
    assert jacket["fallbackUsed"] is True
    assert jacket["learnedCandidateBuild"] == {
        "exceptionType": "RuntimeError",
        "reason": "learned_candidate_failed_family_builder_contract",
        "status": "rejected",
    }


def _read(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
