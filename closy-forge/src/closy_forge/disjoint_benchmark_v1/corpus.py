from __future__ import annotations

import hashlib
import hmac
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .protocol import FIXED_PARAMETERS, OBSERVABLE_PARAMETERS, PARAMETER_RANGES, normalized_distance

BASE_COLOURS: tuple[tuple[int, int, int], ...] = (
    (35, 73, 126),
    (178, 65, 74),
    (48, 112, 91),
    (213, 157, 67),
    (92, 82, 125),
    (202, 198, 186),
)
LOGO_SHAPES: tuple[str, ...] = ("none", "circle", "diamond", "bar")
NECK_SHAPES: tuple[str, ...] = ("crew", "scoop", "wide")


@dataclass(frozen=True)
class RealizedIdentity:
    opaque_id: str
    ordinal: int
    stratum: str
    parameters: dict[str, float]
    appearance: dict[str, Any]
    capture: dict[str, Any]
    nonce: str
    target_commitment: str
    draw_digest: str

    def public_source_record(self) -> dict[str, Any]:
        return {
            "opaqueId": self.opaque_id,
            "ordinal": self.ordinal,
            "stratum": self.stratum,
            "capture": self.capture,
            "targetCommitment": self.target_commitment,
            "drawDigest": self.draw_digest,
        }

    def target_record(self) -> dict[str, Any]:
        return {
            "opaqueId": self.opaque_id,
            "parameters": self.parameters,
            "appearance": self.appearance,
            "capture": self.capture,
            "nonce": self.nonce,
            "targetCommitment": self.target_commitment,
            "drawDigest": self.draw_digest,
        }


def realize_identities(
    *,
    seed_hex: str,
    count: int,
    role: str,
    minimum_prior_distance: float,
    references: Iterable[Mapping[str, Any]],
    maximum_attempts: int,
) -> tuple[list[RealizedIdentity], list[dict[str, Any]]]:
    seed = int(hashlib.sha256(seed_hex.encode("ascii")).hexdigest(), 16)
    rng = random.Random(seed)
    reference_parameters = [dict(item) for item in references]
    accepted: list[RealizedIdentity] = []
    transcript: list[dict[str, Any]] = []
    for attempt in range(maximum_attempts):
        draw = _draw(rng, attempt)
        draw_digest = sha256_bytes(canonical_dumps(draw).encode("utf-8"))
        distances = [normalized_distance(draw["parameters"], item) for item in reference_parameters]
        prior_distance = min(distances, default=1.0)
        duplicate = any(item.draw_digest == draw_digest for item in accepted)
        reasons: list[str] = []
        if prior_distance < minimum_prior_distance:
            reasons.append("below_minimum_normalized_reference_distance")
        if duplicate:
            reasons.append("duplicate_draw_digest")
        if not _structural_draw_valid(draw["parameters"]):
            reasons.append("canonical_structural_preflight_failed")
        if (
            accepted
            and min(normalized_distance(draw["parameters"], item.parameters) for item in accepted)
            < 0.075
        ):
            reasons.append("below_minimum_within_role_distance")
        expected_stratum = ("logo_absent", "logo_present", "controlled_capture", "shape_extreme")[
            len(accepted) % 4
        ]
        observed_stratum = _stratum(draw, len(accepted))
        if observed_stratum != expected_stratum:
            reasons.append(f"ordinal_stratum_mismatch:{expected_stratum}:{observed_stratum}")
        accepted_draw = not reasons
        transcript_record: dict[str, Any] = {
            "attempt": attempt,
            "seedExpansion": hmac.new(
                seed_hex.encode("ascii"), f"{role}:{attempt}".encode(), hashlib.sha256
            ).hexdigest(),
            "drawDigest": draw_digest,
            "accepted": accepted_draw,
            "reasons": reasons,
        }
        if accepted_draw:
            ordinal = len(accepted)
            opaque_id = (
                "garment_"
                + hmac.new(
                    seed_hex.encode("ascii"), f"opaque:{role}:{attempt}".encode(), hashlib.sha256
                ).hexdigest()[:20]
            )
            nonce = hmac.new(
                seed_hex.encode("ascii"), f"nonce:{role}:{attempt}".encode(), hashlib.sha512
            ).hexdigest()
            target_payload = {
                "opaqueId": opaque_id,
                "parameters": draw["parameters"],
                "appearance": draw["appearance"],
                "capture": draw["capture"],
                "drawDigest": draw_digest,
            }
            commitment = sha256_bytes(
                nonce.encode("ascii") + canonical_dumps(target_payload).encode("utf-8")
            )
            identity = RealizedIdentity(
                opaque_id=opaque_id,
                ordinal=ordinal,
                stratum=_stratum(draw, ordinal),
                parameters=draw["parameters"],
                appearance=draw["appearance"],
                capture=draw["capture"],
                nonce=nonce,
                target_commitment=commitment,
                draw_digest=draw_digest,
            )
            accepted.append(identity)
            transcript_record.update(
                {
                    "ordinal": ordinal,
                    "opaqueId": opaque_id,
                    "stratum": identity.stratum,
                    "minimumReferenceDistance": round(prior_distance, 9),
                    "targetCommitment": commitment,
                }
            )
            reference_parameters.append(identity.parameters)
            if len(accepted) == count:
                transcript.append(transcript_record)
                break
        transcript.append(transcript_record)
    if len(accepted) != count:
        raise ValueError(f"d0_disjoint_identity_inventory_incomplete:{len(accepted)}:{count}")
    return accepted, transcript


def verify_target_commitment(record: Mapping[str, Any]) -> bool:
    target_payload = {
        "opaqueId": record["opaqueId"],
        "parameters": record["parameters"],
        "appearance": record["appearance"],
        "capture": record["capture"],
        "drawDigest": record["drawDigest"],
    }
    observed = sha256_bytes(
        str(record["nonce"]).encode("ascii") + canonical_dumps(target_payload).encode("utf-8")
    )
    return hmac.compare_digest(observed, str(record["targetCommitment"]))


def default_prior() -> dict[str, float]:
    return {
        **{name: float(getattr(TShirtParameters(), name)) for name in OBSERVABLE_PARAMETERS},
        **FIXED_PARAMETERS,
    }


def _draw(rng: random.Random, attempt: int) -> dict[str, Any]:
    parameters = {
        name: round(rng.uniform(bounds[0], bounds[1]), 9)
        for name, bounds in PARAMETER_RANGES.items()
    }
    parameters.update(FIXED_PARAMETERS)
    parameters["shoulder_slope"] = round(parameters["shoulder_slope"], 9)
    TShirtParameters(**parameters).validate()
    logo_shape = LOGO_SHAPES[(attempt + rng.randrange(len(LOGO_SHAPES))) % len(LOGO_SHAPES)]
    appearance = {
        "baseColorSrgb": list(BASE_COLOURS[rng.randrange(len(BASE_COLOURS))]),
        "logoShape": logo_shape,
        "logoCenterNormalized": [
            round(rng.uniform(0.38, 0.62), 6),
            round(rng.uniform(0.36, 0.66), 6),
        ],
        "logoScaleNormalized": round(rng.uniform(0.065, 0.15), 6),
        "logoColorSrgb": [238, 231, 214],
        "neckShape": NECK_SHAPES[rng.randrange(len(NECK_SHAPES))],
    }
    capture = {
        "front": _camera(rng, "front"),
        "rear": _camera(rng, "rear"),
        "evaluatorThreeQuarter": _camera(rng, "evaluator_three_quarter"),
        "occlusionFraction": round(rng.choice((0.0, 0.0, 0.025, 0.05, 0.075)), 6),
        "cropFraction": round(rng.choice((0.0, 0.0, 0.015, 0.025)), 6),
    }
    return {"parameters": parameters, "appearance": appearance, "capture": capture}


def _camera(rng: random.Random, role: str) -> dict[str, Any]:
    nominal_azimuth = {"front": 0.0, "rear": 180.0, "evaluator_three_quarter": 38.0}[role]
    return {
        "projection": "orthographic",
        "azimuthDegrees": round(nominal_azimuth + rng.uniform(-2.0, 2.0), 6),
        "elevationDegrees": round(4.0 + rng.uniform(-1.0, 1.0), 6),
        "orthographicScale": round(1.12 + rng.uniform(-0.035, 0.035), 6),
        "principalPointNormalized": [
            round(0.5 + rng.uniform(-0.008, 0.008), 6),
            round(0.5 + rng.uniform(-0.008, 0.008), 6),
        ],
        "imageSize": [128, 160],
        "candidateBoundsAutoFraming": False,
        "runtimeBoundsFramed": False,
    }


def _stratum(draw: Mapping[str, Any], ordinal: int) -> str:
    appearance = draw["appearance"]
    capture = draw["capture"]
    if appearance["logoShape"] == "none":
        return "logo_absent"
    if float(capture["occlusionFraction"]) > 0.0 or float(capture["cropFraction"]) > 0.0:
        return "controlled_capture"
    return "shape_extreme" if ordinal % 4 == 3 else "logo_present"


def _structural_draw_valid(parameters: Mapping[str, Any]) -> bool:
    # Imported lazily so corpus commitments remain independent of evaluator aggregation.
    from .compiler import compile_structural_candidate

    try:
        compiled = compile_structural_candidate(parameters)
    except ValueError:
        return False
    return bool(compiled.report["finite"] and compiled.report["bindingStatus"] == "pass")
