from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path, PureWindowsPath

import pytest

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_file
from closy_forge.recovery_foundation_v2.c3_audit import (
    build_historical_v5_scope,
    generic_c3_mutation_report,
)
from closy_forge.recovery_foundation_v2.container_boundary import (
    IMAGE_REFERENCE,
    build_container_capability,
    build_docker_run_command,
    cap_diagnostic,
    collect_outputs,
    validate_command,
    validate_environment,
    windows_mount_render,
)
from closy_forge.recovery_foundation_v2.contracts import (
    build_budget_event_ledger,
    build_external_attestation,
    build_starting_manifest,
    canonical_digest,
    derive_budgets,
    validate_budget_event_ledger,
    validate_external_attestation,
    validate_result_record,
    validate_starting_manifest,
)
from closy_forge.recovery_foundation_v2.evaluator_v3 import (
    evaluate,
    generic_rows,
    mutation_report,
    protocol,
    validate_protocol,
)
from closy_forge.recovery_foundation_v2.pixel_routes import (
    PRIMARY_ROUTE,
    ROUTES,
    build_pixel_causal_controls,
    decode_pixel_observations,
    fit_public_development_model,
    render_public_tshirt_png,
    run_route,
    validate_fitted_model,
)
from closy_forge.recovery_foundation_v2.portable_numeric import (
    boundary_fixtures,
    canonical_geometry_coordinate,
    derive_from_raw,
    encode_metric,
    validate_metric,
)
from closy_forge.recovery_foundation_v2.production_assembly import (
    execute_public_fixture,
    portable_production_report,
)
from closy_forge.recovery_foundation_v2.topology_holdout import (
    PUBLIC_DEVELOPMENT_SEED,
    build_public_development_proof,
    generate,
    generator_lock,
)
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import (
    derive_invariants,
    validate_candidate_report,
)
from closy_forge.recovery_foundation_v2.typed_inventory import (
    build_recoverable_inventory,
    evaluate_disjointness,
    validate_inventory,
)

ROOT = Path(__file__).resolve().parents[2]


def _load_unit_s_builder() -> object:
    import importlib.util

    path = ROOT / "scripts/build_evidence_authority_recovery_v2.py"
    spec = importlib.util.spec_from_file_location("build_evidence_authority_recovery_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unit_s_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_external_unit_s_authority_attestation_is_fail_closed() -> None:
    module = _load_unit_s_builder()
    path = ROOT / "fixtures/evidence_authority_recovery_v2/unit_s_external_attestation.json"
    attestation = json.loads(path.read_text(encoding="utf-8"))
    assert module.validate_unit_s_authority_attestation(attestation) == []
    invalid = deepcopy(attestation)
    invalid["replicationsPassed"] = 2
    assert "unit_s_authority_replicationsPassed_invalid" in (
        module.validate_unit_s_authority_attestation(invalid)
    )


def _garment_record(ordinal: int, *, capture: int | None = None) -> dict[str, object]:
    return {
        "garmentIdentity": {
            "patternParameters": {"length": 0.5 + ordinal * 0.01},
            "program": f"program-{ordinal}",
            "panels": f"panels-{ordinal}",
            "seams": f"seams-{ordinal}",
            "openings": f"openings-{ordinal}",
            "restGeometry": f"rest-{ordinal}",
            "simulationGeometry": f"simulation-{ordinal}",
            "appearanceLogo": f"appearance-{ordinal}",
            "pbrPreset": "bounded-cotton-v1",
        },
        "captureIdentity": {
            "camera": f"camera-{capture if capture is not None else ordinal}",
            "crop": "none",
            "occlusion": "none",
            "lighting": "fixed",
            "raster": f"raster-{capture if capture is not None else ordinal}",
        },
        "parameters": {"length": 0.5 + ordinal * 0.01},
    }


def test_starting_manifest_and_external_attestation_are_exact_and_fail_closed() -> None:
    manifest = build_starting_manifest()
    attestation = build_external_attestation()
    assert validate_starting_manifest(manifest) == []
    assert validate_external_attestation(attestation) == []
    assert manifest["activeTail"][-1]["headSha"] == ("8dd7a547debf038e9e27c48cf8e42009ae69ac3a")
    bad = deepcopy(manifest)
    bad["publicationAnchors"]["46"]["scientificResultSha"] = bad["publicationAnchors"]["46"][
        "publicationHeadSha"
    ]
    bad["canonicalDigest"] = canonical_digest(bad)
    assert "publication_result_conflated:46" in validate_starting_manifest(bad)
    stale = deepcopy(attestation)
    stale["workflow"]["headSha"] = "0" * 40
    stale["canonicalDigest"] = canonical_digest(stale)
    assert "external_attestation_workflow_head_invalid" in validate_external_attestation(stale)


def test_physical_budget_ledger_is_derived_and_preserves_unit_o_classification() -> None:
    ledger = build_budget_event_ledger()
    assert validate_budget_event_ledger(ledger) == []
    assert ledger["derived"]["remaining"] == {
        "seam_model": 0,
        "topology_strategy": 1,
        "canonical_candidate": 1,
    }
    for row in ledger["events"]:
        assert sha256_file(ROOT / row["sourcePath"]) == row["sourceDigest"]
    duplicated = deepcopy(ledger["events"])
    duplicated[1]["eventId"] = duplicated[0]["eventId"]
    with pytest.raises(ValueError, match="budget_event_id_duplicate_or_missing"):
        derive_budgets(duplicated)
    reordered = list(reversed(deepcopy(ledger["events"])))
    with pytest.raises(ValueError, match="budget_event_order_invalid"):
        derive_budgets(reordered)


def test_result_schema_distinguishes_attempt_result_and_fixed_denominators() -> None:
    result = {
        "result": "pass",
        "attemptState": "completed",
        "denominators": {"fixtures": 8},
        "counts": {"fixtures": 8},
        "rows": [{"identity": "a", "route": "primary"}],
        "requiredRequirementIds": ["S1", "S2"],
        "requirementIds": ["S1", "S2"],
        "repeatReserveDefined": True,
    }
    assert validate_result_record(result) == []
    result["counts"]["fixtures"] = 7
    assert "pass_denominator_incomplete:fixtures" in validate_result_record(result)


def test_container_boundary_is_pinned_scrubbed_and_output_collection_is_fail_closed(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    command = build_docker_run_command(input_dir, output_dir, route_id="generic_canary")
    assert validate_command(command) == []
    assert command[-1] == IMAGE_REFERENCE
    assert build_container_capability()["commandValidationIssues"] == []
    assert validate_environment({"LANG": "C.UTF-8", "ROUTE_ID": "generic_canary"}) == []
    assert validate_environment({"SECRET": "value"}) == ["SECRET"]
    assert windows_mount_render(PureWindowsPath("C:/closy/input")) == "C:\\closy\\input"
    with pytest.raises(ValueError, match="must_be_absolute"):
        windows_mount_render(PureWindowsPath("relative/input"))
    (output_dir / "probe.json").write_text("{}", encoding="utf-8")
    assert collect_outputs(output_dir)[0]["path"] == "probe.json"
    (output_dir / "unexpected.txt").write_text("escape", encoding="utf-8")
    with pytest.raises(ValueError, match="name_or_depth_forbidden"):
        collect_outputs(output_dir)
    assert cap_diagnostic(b"x" * 20, maximum_bytes=8)["truncated"] is True


def test_container_rejects_hardlinks_and_symlinks_where_supported(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    original = output / "probe.json"
    original.write_text("{}", encoding="utf-8")
    os.link(original, output / "prediction.json")
    with pytest.raises(ValueError, match="hardlink_forbidden"):
        collect_outputs(output)


def test_pixel_routes_decode_real_pngs_and_learned_model_is_causally_distinct() -> None:
    model = fit_public_development_model()
    validate_fitted_model(model)
    parameters = {
        "garment_body_length": 0.58,
        "half_chest_width": 0.26,
        "shoulder_width": 0.68,
        "sleeve_length": 0.22,
    }
    front = render_public_tshirt_png(parameters, rear=False, logo=True)
    rear = render_public_tshirt_png(parameters, rear=True, logo=False)
    assert front == render_public_tshirt_png(parameters, rear=False, logo=True)
    assert b"\x78\x01" in front
    observation = decode_pixel_observations(front, rear)
    assert observation["decodedRoles"] == ["front_png", "rear_png"]
    assert run_route(ROUTES[0], front_png=None, rear_png=None)["pixelsConsumed"] is False
    assert (
        run_route(PRIMARY_ROUTE, front_png=front, rear_png=rear, model=model)["pixelsConsumed"]
        is True
    )
    controls = build_pixel_causal_controls(model)
    assert all(
        controls[field] is True
        for field in (
            "missingPixelsRejected",
            "pixelMutationChangesObservation",
            "cropAndOcclusionChangeBytes",
            "negativeModelChangesPrediction",
            "learnedAndMaskRoutesDistinct",
        )
    )
    assert controls["sourceObservedPbrFraction"] == 0.0


def test_pixel_route_source_is_separated_from_target_and_evaluator_implementations() -> None:
    source = (ROOT / "src/closy_forge/recovery_foundation_v2/pixel_routes.py").read_text(
        encoding="utf-8"
    )
    forbidden_imports = (
        "topology_holdout",
        "evaluator_v3",
        "target_generator",
        "private_target",
    )
    assert all(f"import {name}" not in source for name in forbidden_imports)
    assert "from closy_forge.recovery_foundation_v2.evaluator_v3" not in source


def test_typed_inventory_and_non_substitutable_disjointness_layers() -> None:
    inventory = build_recoverable_inventory(ROOT)
    assert validate_inventory(inventory) == []
    assert all(row["availability"] == "recoverable" for row in inventory["sources"])
    prior = [_garment_record(0)]
    fresh = [_garment_record(2)]
    result = evaluate_disjointness(prior, fresh, minimum_parameter_distance=0.01)
    assert result["overallRecoverableInventoryPass"] is True
    repeated_garment = deepcopy(_garment_record(0, capture=9))
    repeated = evaluate_disjointness(prior, [repeated_garment], minimum_parameter_distance=0.01)
    assert repeated["garmentIdentityPredicate"]["pass"] is False
    assert repeated["captureInstancePredicate"]["pass"] is True
    assert repeated["disjointFromUnrecoverableV2OpaqueCohort"] == "unverified"


def test_evaluator_freezes_all_denominators_and_rejects_mutations() -> None:
    document = protocol()
    assert validate_protocol(document) == []
    result = evaluate(document, *generic_rows())
    assert result["denominators"] == {
        "predictions": 64,
        "fullCompiles": 48,
        "primaryCompileRepeats": 16,
        "appearanceScores": 24,
        "primaryAppearanceRepeats": 8,
    }
    assert result["routePromoted"] is True
    assert all(mutation_report().values())


def test_portable_numeric_policy_derives_from_raw_and_fails_ambiguity() -> None:
    metric = encode_metric(
        "seam_gap",
        [0.001, 0.002, 0.003],
        unit="meters",
        integer_scale_per_unit=1_000_000_000,
        threshold=0.01,
        comparator="maximum",
    )
    assert validate_metric(metric) == []
    assert derive_from_raw(metric) == metric
    below, at, above = boundary_fixtures()
    assert below["decision"] == "pass"
    assert at["decision"] == "fail" and at["ambiguityBandEntered"] is True
    assert above["decision"] == "fail"
    assert canonical_geometry_coordinate(0.1234567894)["integerNanometers"] == 123456789
    with pytest.raises(ValueError, match="nonfinite"):
        encode_metric(
            "bad",
            [float("nan")],
            unit="meters",
            integer_scale_per_unit=1_000_000_000,
            threshold=1.0,
            comparator="maximum",
        )


def test_c3_scope_is_decomposed_without_replaying_historical_qualification() -> None:
    report = build_historical_v5_scope(ROOT)
    assert report["poseDenominator"] == 8
    assert report["historicalBytesChanged"] is False
    assert report["qualificationReplayed"] is False
    assert report["rawIndexedSimulationComponents"] == 614
    assert report["rawComponentEqualityIsCoherentShellProof"] is False
    assert report["predicates"]["physicalDeformationCorrectness"] == "not_measured"
    assert all(generic_c3_mutation_report().values())


def test_topology_generator_is_deterministic_independent_and_mutation_sensitive() -> None:
    lock = generator_lock()
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    assert lock["denominator"] == len(fixtures) == 8
    assert fixtures == generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    assert all(fixture["qualificationEligible"] is False for fixture in fixtures)
    assert build_public_development_proof()["mutationDetected"] is True
    oracle = derive_invariants(fixtures[0])
    valid_report = {
        "fixtureId": fixtures[0]["fixtureId"],
        "semanticSeamSequences": oracle["expectedSeamSequences"],
        "intervalCoverage": oracle["expectedIntervalCoverage"],
        "openingCount": oracle["expectedOpeningCount"],
        "transferredAttributeClasses": oracle["requiredAttributeClasses"],
        "productionPathEvidence": {"calls": ["instrumented"]},
    }
    assert validate_candidate_report(fixtures[0], oracle, valid_report) == []
    invalid = deepcopy(valid_report)
    invalid["openingCount"] = 99
    assert "topology_report_opening_count_invalid" in validate_candidate_report(
        fixtures[0], oracle, invalid
    )


def test_topology_oracle_has_no_production_remesher_dependency() -> None:
    oracle_source = (
        ROOT / "src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py"
    ).read_text(encoding="utf-8")
    assert "production_assembly" not in oracle_source
    assert "remesh" not in oracle_source.lower()
    assert "candidate_output_pass" not in oracle_source


def test_public_topology_fixtures_traverse_declared_production_paths() -> None:
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    reports = [execute_public_fixture(fixture) for fixture in fixtures]
    for report in reports:
        if report["productionPathRequired"]:
            assert report["productionPathExecuted"] is True
            assert report["productionCalls"]
        else:
            assert report["productionPathExecuted"] is False


def test_committed_production_telemetry_is_field_classed_and_float_free() -> None:
    fixture = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)[5]
    raw = execute_public_fixture(fixture)
    portable = portable_production_report(raw)

    assert raw["numericLayer"] == "raw_execution_local_binary64"
    assert portable["numericLayer"] == "portable_fixed_point_committed"
    assert portable["rawTelemetry"]["committed"] is False
    assert not _contains_float(portable)
    assert portable["measurements"]["contact"]["maximumPenetrationBeforeMeters"] == {
        "integerValue": 22_000_000,
        "unit": "meters",
        "integerScalePerUnit": 1_000_000_000,
    }


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def test_unit_o_frozen_raw_and_integrity_evidence_bytes_are_unchanged() -> None:
    expected = {
        "docs/evidence/phy1_topology_strategy3_diagnosis_v1/unit_o_outcome.json": (
            "fd9af53158b6e3a8f1951367751ed5ad912351d10f0e21e836f5b3db3e2cbf79"
        ),
        "docs/evidence/phy1_topology_strategy3_diagnosis_v1/integrity_attestation.json": (
            "c8bc078c42e3c827cc537562a100c7279cd48c61320fcfa8ed5c15b2e54813fc"
        ),
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_protocol_and_generator_locks_have_stable_canonical_bytes() -> None:
    first = canonical_dumps({"evaluator": protocol(), "topology": generator_lock()})
    second = canonical_dumps({"evaluator": protocol(), "topology": generator_lock()})
    assert first == second
    assert json.loads(first)["evaluator"]["denominators"]["predictions"] == 64


def test_committed_unit_s_evidence_is_fresh() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_authority_recovery_v2.py",
            "--root",
            ".",
            "--check",
        ],
        cwd=ROOT,
        check=True,
        timeout=30,
    )
    manifest = json.loads(
        (ROOT / "docs/evidence/evidence_authority_recovery_v2/evidence_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    paths = [row["path"] for row in manifest["records"]]
    assert paths == sorted(paths)
