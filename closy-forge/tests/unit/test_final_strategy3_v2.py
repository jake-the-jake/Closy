from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from closy_forge.final_strategy3_v2.ccd import public_ccd_evidence
from closy_forge.final_strategy3_v2.evaluator import evaluate_fixture, validate_report
from closy_forge.final_strategy3_v2.remesh import (
    build_generic_garment,
    quotient_component_count,
    remesh_garment,
    validate_transfer,
)
from closy_forge.final_strategy3_v2.semantic_transfer import (
    build_correspondence,
    validate_correspondence,
)
from closy_forge.recovery_foundation_v2.topology_holdout import (
    PUBLIC_DEVELOPMENT_SEED,
    generate,
)
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import (
    derive_invariants,
    validate_candidate_report,
)


def test_public_holdout_shaped_fixtures_pass_independent_oracle_and_strategy_validator() -> None:
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    reports = [evaluate_fixture(fixture) for fixture in fixtures]
    for fixture, report in zip(fixtures, reports, strict=True):
        oracle = derive_invariants(fixture)
        assert validate_candidate_report(fixture, oracle, report) == []
        assert validate_report(report) == []
        assert report["productionPathEvidence"]["productionAssemblyExecuted"] is True
        assert report["sourceTopologyHash"] != report["targetTopologyHash"]


@pytest.mark.parametrize("refinement_levels", [1, 2, 3])
def test_refinement_preserves_mass_attributes_seam_authority_and_rebuilt_indices(
    refinement_levels: int,
) -> None:
    source = build_generic_garment(
        seam_count=1,
        sample_count=7,
        opening_count=4,
        target_mass_kg=0.243,
    )
    target, rebuilt = remesh_garment(source, refinement_levels=refinement_levels)
    assert validate_transfer(source, target, rebuilt) == []
    assert len(rebuilt.seam_constraint_ids) == 7
    assert len(target.opening_cycles) == 4
    assert quotient_component_count(target) == 1
    assert (
        abs(sum(vertex.mass_kg for panel in target.panels for vertex in panel.vertices) - 0.243)
        <= 1e-12
    )
    assert all(binding.target_topology_hash == target.topology_hash for binding in rebuilt.bindings)


def test_correspondence_supports_orientation_and_unequal_side_sampling() -> None:
    source = build_generic_garment(
        seam_count=1,
        sample_count=6,
        opening_count=0,
        target_mass_kg=0.2,
    )
    target, _ = remesh_garment(source, refinement_levels=2)
    seam = target.seams[0]
    samples = build_correspondence(seam, target.panels)
    assert validate_correspondence(seam, samples) == []
    assert [row.normalized_arclength_b for row in samples] == sorted(
        (row.normalized_arclength_b for row in samples), reverse=True
    )
    assert any(
        row.side_a.interpolation_weight != row.side_b.interpolation_weight for row in samples
    )

    same_orientation = replace(seam, sides=(seam.sides[0], deepcopy(seam.sides[0])))
    same_samples = build_correspondence(same_orientation, target.panels)
    assert validate_correspondence(same_orientation, same_samples) == []
    assert [row.normalized_arclength_b for row in same_samples] == sorted(
        row.normalized_arclength_b for row in same_samples
    )


def test_opening_and_junction_semantics_are_representation_specific() -> None:
    garment = build_generic_garment(
        seam_count=3,
        sample_count=4,
        opening_count=4,
        target_mass_kg=0.2,
    )
    assert len(garment.panels) == 2
    assert quotient_component_count(garment) == 1
    assert len(garment.opening_cycles) == 4
    assert {seam.junction_id for seam in garment.seams} == {"junction.shoulder"}
    assert all(len(set(cycle)) == len(cycle) for cycle in garment.opening_cycles)


def test_ccd_detects_interior_tunnelling_that_endpoint_mutations_miss() -> None:
    evidence = public_ccd_evidence()
    assert evidence["vertexFace"]["detected"] is True
    assert evidence["vertexFace"]["endpointOnlyMutationMissed"] is True
    assert evidence["edgeEdge"]["detected"] is True
    assert evidence["edgeEdge"]["endpointOnlyMutationMissed"] is True
    assert (
        evidence["postCorrection"]["seamResidualMeters"]
        <= evidence["postCorrection"]["maximumAllowedMeters"]
    )


def test_oracle_and_strategy_reject_real_report_mutations() -> None:
    fixture = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)[0]
    report = evaluate_fixture(fixture)
    oracle = derive_invariants(fixture)
    mutated = deepcopy(report)
    mutated["semanticSeamSequences"]["seam.0"].reverse()
    assert "topology_report_semantic_sequence_invalid" in validate_candidate_report(
        fixture, oracle, mutated
    )
    mutated = deepcopy(report)
    mutated["productionPathEvidence"]["productionAssemblyExecuted"] = False
    assert "strategy3_production_assembly_not_executed" in validate_report(mutated)
    mutated = deepcopy(report)
    mutated["finiteComplianceLaw"]["sampleCountAfter"] += 1
    assert "strategy3_seam_sample_authority_changed" in validate_report(mutated)
