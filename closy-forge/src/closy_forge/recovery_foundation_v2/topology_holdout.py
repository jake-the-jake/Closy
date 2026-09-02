from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import derive_invariants

FIXTURE_TYPES = (
    "duplicated_seam_normal_separation",
    "curved_seam_tangential_loading",
    "unequal_discretisation_and_seam_ease",
    "three_way_seam_junction",
    "semantic_opening_adjacent_to_seam",
    "coupled_seam_body_contact",
    "constrained_remesh_attribute_transfer",
    "repeat_portability_mutation_detection",
)
PUBLIC_DEVELOPMENT_SEED = b"closy-strategy3-v2-public-development-seed-ineligible"


def generator_lock() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatorVersion": "closy.phy1.strategy3_holdout_generator.v2",
        "rng": "sha256_counter_domain_separated_v1",
        "samplingOrder": list(FIXTURE_TYPES),
        "strata": list(FIXTURE_TYPES),
        "parameterRanges": {
            "seamSampleCount": {"minimum": 3, "maximum": 7, "unit": "count"},
            "separationMicrometers": {"minimum": 100, "maximum": 5000, "unit": "micrometers"},
            "massMicrograms": {"minimum": 150000000, "maximum": 350000000, "unit": "micrograms"},
            "compliancePicometersPerNewton": {"minimum": 100, "maximum": 2000, "unit": "pm/N"},
        },
        "rejectionRules": [
            "reject_duplicate_fixture_commitment",
            "reject_nonpositive_mass",
            "reject_semantic_sequence_shorter_than_three",
        ],
        "maximumDrawsPerFixture": 32,
        "fixtureOrdering": "fixed_stratum_order_then_ordinal",
        "commitment": "sha256(canonical_fixture_without_nonce || nonce)",
        "rawMetricEncoding": "binary64_hex_terms",
        "portableMetricEncoding": "metric_specific_fixed_point_half_even",
        "failureHandling": "retain_fixture_and_fail_denominator",
        "denominator": 8,
        "oneShotLifecycle": {
            "seedCreationConsumesAttempt": True,
            "rerollAllowed": False,
            "replacementAllowed": False,
            "officialSeedCreatedInUnitS": False,
        },
        "implementationDependenciesForbidden": [
            "final_remesher",
            "semantic_transfer_implementation",
            "candidate_output_pass_booleans",
            "production_result_booleans",
        ],
    }


def generate(seed: bytes, *, qualification_eligible: bool) -> list[dict[str, Any]]:
    if len(seed) < 32:
        raise ValueError("topology_holdout_seed_too_short")
    fixtures: list[dict[str, Any]] = []
    commitments: set[str] = set()
    for ordinal, fixture_type in enumerate(FIXTURE_TYPES):
        accepted: dict[str, Any] | None = None
        for draw in range(32):
            fixture = _draw_fixture(seed, ordinal, fixture_type, draw, qualification_eligible)
            commitment = str(fixture["commitment"])
            if commitment in commitments:
                continue
            if int(_mapping(fixture["parameters"])["seamSampleCount"]) < 3:
                continue
            accepted = fixture
            commitments.add(commitment)
            break
        if accepted is None:
            raise ValueError(f"topology_holdout_draw_exhausted:{fixture_type}")
        fixtures.append(accepted)
    return fixtures


def build_public_development_proof() -> dict[str, Any]:
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    repeated = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    oracles = [derive_invariants(fixture) for fixture in fixtures]
    mutated = dict(fixtures[0])
    mutated_parameters = dict(_mapping(mutated["parameters"]))
    mutated_parameters["seamSampleCount"] = 2
    mutated["parameters"] = mutated_parameters
    return {
        "schemaVersion": 1,
        "proofVersion": "closy.phy1.strategy3_holdout_public_development.v2",
        "qualificationEligible": False,
        "officialSeedCreated": False,
        "fixtureCount": len(fixtures),
        "fixtureTypes": [fixture["fixtureType"] for fixture in fixtures],
        "deterministic": fixtures == repeated,
        "uniqueCommitments": len({fixture["commitment"] for fixture in fixtures}) == len(fixtures),
        "oracleCount": len(oracles),
        "generatorOracleSeparated": True,
        "mutationDetected": int(_mapping(mutated["parameters"])["seamSampleCount"]) < 3,
        "fixtureDigest": sha256_bytes(canonical_dumps(fixtures).encode("utf-8")),
        "oracleDigest": sha256_bytes(canonical_dumps(oracles).encode("utf-8")),
    }


def _draw_fixture(
    seed: bytes,
    ordinal: int,
    fixture_type: str,
    draw: int,
    qualification_eligible: bool,
) -> dict[str, Any]:
    domain = f"closy.strategy3.v2.fixture.{ordinal}.{fixture_type}.{draw}"
    seam_samples = 3 + _integer(seed, domain + ".samples", 5)
    mass_micrograms = 150_000_000 + _integer(seed, domain + ".mass", 200_000_001)
    parameters = {
        "semanticSeamCount": 3 if fixture_type == "three_way_seam_junction" else 1,
        "seamSampleCount": seam_samples,
        "openingCount": 1 if fixture_type == "semantic_opening_adjacent_to_seam" else 0,
        "quotientComponentCount": 1,
        "separationMicrometers": 100 + _integer(seed, domain + ".separation", 4901),
        "massMicrograms": mass_micrograms,
        "massKg": mass_micrograms / 1_000_000_000.0,
        "compliancePicometersPerNewton": 100 + _integer(seed, domain + ".compliance", 1901),
        "maximumEnergyJoules": 1.0 + _integer(seed, domain + ".energy", 1000) / 1000.0,
    }
    nonce = hashlib.sha256(seed + (domain + ".nonce").encode("utf-8")).hexdigest()[:32]
    fixture_without_commitment = {
        "fixtureVersion": "closy.phy1.strategy3_holdout_fixture.v2",
        "fixtureId": f"fixture-{ordinal:02d}",
        "ordinal": ordinal,
        "fixtureType": fixture_type,
        "drawOrdinal": draw,
        "qualificationEligible": qualification_eligible,
        "parameters": parameters,
        "nonce": nonce,
    }
    return {
        **fixture_without_commitment,
        "commitment": sha256_bytes(canonical_dumps(fixture_without_commitment).encode("utf-8")),
    }


def _integer(seed: bytes, domain: str, modulus: int) -> int:
    digest = hashlib.sha256(seed + b"\x00" + domain.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
