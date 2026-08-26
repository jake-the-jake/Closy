from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .parameters import SimpleSkirtParameters

SIMPLE_SKIRT_FIT_VERSION = "closy.simple_skirt.bounded_fit.d0.v1"


def fit_simple_skirt(
    prior: SimpleSkirtParameters,
    *,
    observed_half_waist_meters: float = 0.224,
    observed_half_hip_meters: float = 0.281,
    observed_length_meters: float = 0.558,
    observed_hem_half_width_meters: float = 0.346,
) -> tuple[SimpleSkirtParameters, dict[str, Any]]:
    prior.validate()
    observations = {
        "halfWaistMeters": observed_half_waist_meters,
        "halfHipMeters": observed_half_hip_meters,
        "lengthMeters": observed_length_meters,
        "hemHalfWidthMeters": observed_hem_half_width_meters,
        "source": "public_synthetic_simple_skirt_capture_fixture",
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
            length_meters=prior.length_meters + length_delta,
        )
        candidate.validate()
        waist = candidate.half_waist_width_meters + candidate.waist_ease_meters
        hip = candidate.half_hip_width_meters + candidate.hip_ease_meters
        losses = {
            "halfWaistErrorMeters": _round(abs(waist - observed_half_waist_meters)),
            "halfHipErrorMeters": _round(abs(hip - observed_half_hip_meters)),
            "lengthErrorMeters": _round(abs(candidate.length_meters - observed_length_meters)),
            "hemHalfWidthErrorMeters": _round(
                abs(hip + candidate.flare_meters - observed_hem_half_width_meters)
            ),
        }
        losses["weightedObjective"] = _round(
            losses["halfWaistErrorMeters"] * 0.34
            + losses["halfHipErrorMeters"] * 0.30
            + losses["lengthErrorMeters"] * 0.22
            + losses["hemHalfWidthErrorMeters"] * 0.14
        )
        evaluations.append(
            {
                "candidateId": f"candidate.simple_skirt.{index:03d}",
                "parameters": candidate.to_json(),
                "losses": losses,
            }
        )
    evaluations.sort(key=lambda item: (item["losses"]["weightedObjective"], item["candidateId"]))
    winner_doc = evaluations[0]
    winner = SimpleSkirtParameters(**winner_doc["parameters"])
    accepted = float(winner_doc["losses"]["weightedObjective"]) <= 0.005
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": SIMPLE_SKIRT_FIT_VERSION,
        "fitReportId": "fit.simple_skirt.public_d0_v1",
        "garmentClass": "simple_skirt",
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
    report["integrity"]["fitReportHash"] = hash_simple_skirt_fit_report(report)
    return winner, report


def hash_simple_skirt_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
