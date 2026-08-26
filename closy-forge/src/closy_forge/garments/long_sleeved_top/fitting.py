from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .parameters import LongSleevedTopParameters

LONG_SLEEVED_FIT_VERSION = "closy.long_sleeved_top.bounded_fit.d0.v1"


def fit_long_sleeved_top(
    prior: LongSleevedTopParameters,
    *,
    observed_half_width_meters: float = 0.337,
    observed_body_length_meters: float = 0.662,
    observed_sleeve_length_meters: float = 0.558,
    observed_cuff_width_meters: float = 0.106,
) -> tuple[LongSleevedTopParameters, dict[str, Any]]:
    prior.validate()
    observations = {
        "halfWidthMeters": observed_half_width_meters,
        "bodyLengthMeters": observed_body_length_meters,
        "sleeveLengthMeters": observed_sleeve_length_meters,
        "cuffWidthMeters": observed_cuff_width_meters,
        "source": "public_synthetic_long_sleeved_capture_fixture",
        "measuredFromPrivateImage": False,
    }
    evaluations: list[dict[str, Any]] = []
    for index, (width_delta, length_delta) in enumerate(
        (width_delta, length_delta)
        for width_delta in (-0.012, -0.006, 0.0, 0.006, 0.012)
        for length_delta in (-0.012, -0.006, 0.0, 0.006, 0.012)
    ):
        candidate = replace(
            prior,
            half_chest_width_meters=prior.half_chest_width_meters + width_delta,
            body_length_meters=prior.body_length_meters + length_delta,
        )
        candidate.validate()
        losses = {
            "halfWidthErrorMeters": _round(
                abs(
                    candidate.half_chest_width_meters
                    + candidate.body_ease_meters
                    - observed_half_width_meters
                )
            ),
            "bodyLengthErrorMeters": _round(
                abs(candidate.body_length_meters - observed_body_length_meters)
            ),
            "sleeveLengthErrorMeters": _round(
                abs(candidate.sleeve_length_meters - observed_sleeve_length_meters)
            ),
            "cuffWidthErrorMeters": _round(
                abs(candidate.cuff_width_meters - observed_cuff_width_meters)
            ),
        }
        losses["weightedObjective"] = _round(
            losses["halfWidthErrorMeters"] * 0.38
            + losses["bodyLengthErrorMeters"] * 0.24
            + losses["sleeveLengthErrorMeters"] * 0.25
            + losses["cuffWidthErrorMeters"] * 0.13
        )
        evaluations.append(
            {
                "candidateId": f"candidate.long_sleeved_top.{index:03d}",
                "parameters": candidate.to_json(),
                "losses": losses,
            }
        )
    evaluations.sort(key=lambda item: (item["losses"]["weightedObjective"], item["candidateId"]))
    winner_doc = evaluations[0]
    winner = LongSleevedTopParameters(**winner_doc["parameters"])
    accepted = float(winner_doc["losses"]["weightedObjective"]) <= 0.005
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": LONG_SLEEVED_FIT_VERSION,
        "fitReportId": "fit.long_sleeved_top.public_d0_v1",
        "garmentClass": "long_sleeved_top",
        "method": "bounded_exhaustive_parameter_candidate_evaluation",
        "status": "pass" if accepted else "fail",
        "accepted": accepted,
        "observations": observations,
        "priorParameters": prior.to_json(),
        "fittedParameters": winner.to_json(),
        "candidateCount": len(evaluations),
        "winnerCandidateId": winner_doc["candidateId"],
        "winnerLosses": winner_doc["losses"],
        "evaluations": evaluations,
        "boundsEnforced": True,
        "learnedFitRun": False,
        "privateUserFitRun": False,
        "integrity": {"fitReportHash": ""},
    }
    report["integrity"]["fitReportHash"] = hash_long_sleeved_fit_report(report)
    return winner, report


def hash_long_sleeved_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
