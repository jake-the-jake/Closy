from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .parameters import LayeredAsymmetricParameters

LAYERED_ASYMMETRIC_FIT_VERSION = "closy.layered_asymmetric.bounded_fit.d0.v1"


def fit_layered_asymmetric(
    prior: LayeredAsymmetricParameters,
    *,
    observed_half_width_meters: float = 0.327,
    observed_body_length_meters: float = 0.642,
    observed_armhole_depth_meters: float = 0.226,
) -> tuple[LayeredAsymmetricParameters, dict[str, Any]]:
    """Evaluate a bounded deterministic candidate set against authored source evidence."""

    prior.validate()
    observations = {
        "halfWidthMeters": observed_half_width_meters,
        "bodyLengthMeters": observed_body_length_meters,
        "armholeDepthMeters": observed_armhole_depth_meters,
        "source": "public_synthetic_layered_asymmetric_capture_fixture",
        "measuredFromPrivateImage": False,
    }
    evaluations: list[dict[str, Any]] = []
    candidates: list[LayeredAsymmetricParameters] = []
    for width_delta in (-0.012, -0.006, 0.0, 0.006, 0.012):
        for length_delta in (-0.012, -0.006, 0.0, 0.006, 0.012):
            candidate = replace(
                prior,
                half_chest_width_meters=prior.half_chest_width_meters + width_delta,
                body_length_meters=prior.body_length_meters + length_delta,
            )
            candidate.validate()
            candidates.append(candidate)
    for index, candidate in enumerate(candidates):
        fitted_half_width = candidate.half_chest_width_meters + candidate.body_ease_meters
        width_error = abs(fitted_half_width - observed_half_width_meters)
        length_error = abs(candidate.body_length_meters - observed_body_length_meters)
        armhole_error = abs(candidate.armhole_depth_meters - observed_armhole_depth_meters)
        objective = width_error * 0.48 + length_error * 0.34 + armhole_error * 0.18
        evaluations.append(
            {
                "candidateId": f"candidate.layered_asymmetric.{index:03d}",
                "parameters": candidate.to_json(),
                "losses": {
                    "halfWidthErrorMeters": _round(width_error),
                    "bodyLengthErrorMeters": _round(length_error),
                    "armholeDepthErrorMeters": _round(armhole_error),
                    "weightedObjective": _round(objective),
                },
            }
        )
    evaluations.sort(
        key=lambda item: (
            item["losses"]["weightedObjective"],
            item["candidateId"],
        )
    )
    winner_doc = evaluations[0]
    winner = LayeredAsymmetricParameters(**winner_doc["parameters"])
    accepted = float(winner_doc["losses"]["weightedObjective"]) <= 0.005
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": LAYERED_ASYMMETRIC_FIT_VERSION,
        "fitReportId": "fit.layered_asymmetric.public_d0_v1",
        "garmentClass": "layered_asymmetric",
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
    report["integrity"]["fitReportHash"] = hash_layered_asymmetric_fit_report(report)
    return winner, report


def hash_layered_asymmetric_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
