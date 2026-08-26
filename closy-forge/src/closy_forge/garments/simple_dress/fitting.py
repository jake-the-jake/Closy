from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .parameters import SimpleDressParameters

SIMPLE_DRESS_FIT_VERSION = "closy.simple_dress.bounded_fit.d0.v1"


def fit_simple_dress(
    prior: SimpleDressParameters,
    *,
    observed_half_waist_meters: float = 0.224,
    observed_half_hip_meters: float = 0.281,
    observed_half_chest_meters: float = 0.321,
    observed_skirt_length_meters: float = 0.618,
) -> tuple[SimpleDressParameters, dict[str, Any]]:
    prior.validate()
    observations = {
        "halfWaistMeters": observed_half_waist_meters,
        "halfHipMeters": observed_half_hip_meters,
        "halfChestMeters": observed_half_chest_meters,
        "skirtLengthMeters": observed_skirt_length_meters,
        "source": "public_synthetic_simple_dress_capture_fixture",
        "measuredFromPrivateImage": False,
    }
    evaluations: list[dict[str, Any]] = []
    for index, (waist_delta, length_delta) in enumerate(
        (waist_delta, length_delta)
        for waist_delta in (-0.012, -0.006, 0.0, 0.006, 0.012)
        for length_delta in (-0.012, -0.006, 0.0, 0.006, 0.012)
    ):
        candidate = replace(
            prior,
            half_waist_width_meters=prior.half_waist_width_meters + waist_delta,
            skirt_length_meters=prior.skirt_length_meters + length_delta,
        )
        candidate.validate()
        losses = {
            "halfWaistErrorMeters": _round(
                abs(
                    candidate.half_waist_width_meters
                    + candidate.waist_ease_meters
                    - observed_half_waist_meters
                )
            ),
            "halfHipErrorMeters": _round(
                abs(
                    candidate.half_hip_width_meters
                    + candidate.hip_ease_meters
                    - observed_half_hip_meters
                )
            ),
            "halfChestErrorMeters": _round(
                abs(
                    candidate.half_chest_width_meters
                    + candidate.body_ease_meters
                    - observed_half_chest_meters
                )
            ),
            "skirtLengthErrorMeters": _round(
                abs(candidate.skirt_length_meters - observed_skirt_length_meters)
            ),
        }
        losses["weightedObjective"] = _round(
            losses["halfWaistErrorMeters"] * 0.32
            + losses["halfHipErrorMeters"] * 0.24
            + losses["halfChestErrorMeters"] * 0.24
            + losses["skirtLengthErrorMeters"] * 0.20
        )
        evaluations.append(
            {
                "candidateId": f"candidate.simple_dress.{index:03d}",
                "parameters": candidate.to_json(),
                "losses": losses,
            }
        )
    evaluations.sort(key=lambda item: (item["losses"]["weightedObjective"], item["candidateId"]))
    winner_doc = evaluations[0]
    winner = SimpleDressParameters(**winner_doc["parameters"])
    accepted = float(winner_doc["losses"]["weightedObjective"]) <= 0.005
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": SIMPLE_DRESS_FIT_VERSION,
        "fitReportId": "fit.simple_dress.public_d0_v1",
        "garmentClass": "simple_dress",
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
    report["integrity"]["fitReportHash"] = hash_simple_dress_fit_report(report)
    return winner, report


def hash_simple_dress_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
