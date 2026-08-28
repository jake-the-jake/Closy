from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .parameters import SimpleTrousersParameters

SIMPLE_TROUSERS_FIT_VERSION = "closy.simple_trousers.bounded_fit.d0.v1"


def fit_simple_trousers(
    prior: SimpleTrousersParameters,
    *,
    observed_half_waist_meters: float = 0.214,
    observed_half_hip_meters: float = 0.271,
    observed_outseam_meters: float = 0.978,
    observed_cuff_width_meters: float = 0.147,
) -> tuple[SimpleTrousersParameters, dict[str, Any]]:
    prior.validate()
    observations = {
        "halfWaistMeters": observed_half_waist_meters,
        "halfHipMeters": observed_half_hip_meters,
        "outseamMeters": observed_outseam_meters,
        "cuffWidthMeters": observed_cuff_width_meters,
        "source": "project_authored_hidden_target_capture_measurements",
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
            outseam_length_meters=prior.outseam_length_meters + length_delta,
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
            "outseamErrorMeters": _round(
                abs(candidate.outseam_length_meters - observed_outseam_meters)
            ),
            "cuffWidthErrorMeters": _round(
                abs(candidate.leg_cuff_width_meters - observed_cuff_width_meters)
            ),
        }
        losses["weightedObjective"] = _round(
            losses["halfWaistErrorMeters"] * 0.34
            + losses["halfHipErrorMeters"] * 0.28
            + losses["outseamErrorMeters"] * 0.24
            + losses["cuffWidthErrorMeters"] * 0.14
        )
        evaluations.append(
            {
                "candidateId": f"candidate.simple_trousers.{index:03d}",
                "parameters": candidate.to_json(),
                "losses": losses,
            }
        )
    evaluations.sort(key=lambda item: (item["losses"]["weightedObjective"], item["candidateId"]))
    winner_doc = evaluations[0]
    winner = SimpleTrousersParameters(**winner_doc["parameters"])
    accepted = float(winner_doc["losses"]["weightedObjective"]) <= 0.005
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": SIMPLE_TROUSERS_FIT_VERSION,
        "fitReportId": "fit.simple_trousers.public_d0_v1",
        "garmentClass": "simple_trousers",
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
        "evidenceSeparation": {
            "candidatePatternUsedToGenerateTarget": False,
            "hiddenTargetParametersAvailableToFitter": False,
            "hiddenTargetProgramIdentityAvailableToFitter": False,
            "permittedInputs": sorted(observations),
            "prohibitedInputs": [
                "target_family_label",
                "target_template_id",
                "target_panel_count",
                "target_opening_count",
                "exact_target_parameters",
            ],
        },
        "integrity": {"fitReportHash": ""},
    }
    report["integrity"]["fitReportHash"] = hash_simple_trousers_fit_report(report)
    return winner, report


def hash_simple_trousers_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
