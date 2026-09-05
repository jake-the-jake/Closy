from __future__ import annotations

import copy
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.capture_reconstruction_v2.common import (
    canonical_digest,
    read_json,
    sha256_bytes,
    write_json,
)
from closy_forge.capture_reconstruction_v2.status_inventory import (
    STATUS_ORDER,
    build_inventory_transition,
    validate_decorated_inventory,
)

PROTOCOL_ID = "CLOSY-STATIC-ZEROONE-RUNTIME-V2-20260904"
PROTOCOL_DIGEST = "b67193ebd322340fb758d98411334aec26084554f9ce7eefec5698ce90a6ed01"
SOURCE_COMMIT = "afd2101b2dbfa5da067cc8b1f9d3038a8950af1a"
SOURCE_TREE = "f60156c948a108996390fe31c85a8ca3b59f41f1"
ZEROONE_COMMIT = "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027"
ZEROONE_TREE = "6e058711449fdd98c41c82d05294339b3f21fc16"
ZEROONE_EXECUTABLE_SHA256 = "38adb7797344b9fcbbe814ed0bb47c0b23b40577341ecda92d911410ad8ba1a6"
TRUSTED_BUILD_RECORD_SHA256 = "aea342d86a550a28a5e88c90ffb2c2595836c36568eef3a7c8eed5491cdde375"

FAMILIES = (
    "tshirt",
    "sleeveless_top",
    "long_sleeved_top",
    "simple_skirt",
    "simple_trousers",
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
)
PROFILES = ("cpu-balanced-64k-v2", "cpu-compact-32k-v2")
RESUME_POINTS = ("first", "middle", "final")
STAGES = ("Z3", "Z4", "Z5", "Z6", "Z7", "Z8")
TERMINAL_OUTCOMES = {
    "passed",
    "failed",
    "abstained",
    "timed_out",
    "unsupported",
    "corrupt_or_invalid",
    "not_run",
    "dependency_blocked",
    "integrity_error",
    "authorised_excluded",
}
NEGATIVE_CASES = {
    "corrupt_chunk",
    "truncated_stream",
    "trailing_stream",
    "stale_version",
    "cross_package_chunk",
    "decompression_bomb",
    "cancelled_transfer",
    "storage_quota_exceeded",
    "last_good_rollback",
}

PR64_HEAD = "b56c172fac076c47dd3ea101a024ab3793e4fe0d"
PR65_HEAD = "58766731742be3dbd406aafc9d57e079e30b53ec"
PR64_ANCHOR = "closy-forge/docs/evidence/solver_material_v2/canonical_result_envelope.json"
PR65_ANCHOR = "closy-forge/docs/evidence/manual_provider_c3_v1/result.json"
PR66_ANCHOR = "closy-forge/docs/evidence/static_zeroone_runtime_v2/result.json"

PR65_PARTIAL_IDS = {
    "BP-SRC-9BD74E06D1639B12",
    "BP-SRC-3564DB72B3C39459",
    "BP-SRC-77A79811A94F4F4D",
    "BP-SRC-8703F90E49A24DA4",
    "BP-SRC-C52302B7B11DC044",
    "BP-SRC-62599B1A8E535F3A",
    "BP-SRC-0636A88BAE100E2C",
    "BP-SRC-E775EA49E710172F",
    "BP-SRC-BB4B35A831CF4679",
    "BP-SRC-1FC2CEFFA43FF97E",
    "BP-SRC-FA08EF914A1CFE5A",
    "BP-SRC-B4B88DB92B38EA1B",
    "BP-SRC-54B108AADDFC9788",
    "BP-SRC-A8BA79B512147EA7",
    "BP-SRC-A556ECFFF5D99EC0",
}
PR66_PARTIAL_IDS = {
    "BP-SRC-D3DEB46A775A9D33",
    "BP-SRC-590A1EED6C767582",
    "BP-SRC-EF0CF22EA8DB1655",
    "BP-SRC-C6213C19A1163BA0",
    "BP-SRC-D8485DC822A49F84",
    "BP-SRC-FAC5918B4B1CF301",
    "BP-SRC-78D946C921704E6D",
    "BP-SRC-85271FDA43C96FBF",
    "BP-SRC-A98D2DAF0842628F",
    "BP-SRC-50FC1A9E50F7A65F",
    "BP-SRC-399B9A460B87AEE6",
    "BP-SRC-816902514138C2CE",
    "BP-SRC-3D2A970DA8E2F142",
    "BP-SRC-20D9CD5E450CC21E",
    "BP-SRC-937D9197AA6CD4A4",
    "BP-SRC-7B9EB3AAF744D3A7",
    "BP-SRC-56651B0C321513C4",
    "BP-SRC-2B63B012BA93FAA4",
}
PR66_NOT_RUN_IDS = {
    "BP-SRC-B16A9C1A71AB28DF",
    "BP-SRC-B7CBFEC6EE5F5AD7",
    "BP-SRC-1816251ED8387929",
    "BP-SRC-EF70B9A6CDF52599",
    "BP-SRC-07CD84A1017E09F6",
    "BP-SRC-6A66D202B32E11FB",
    "BP-SRC-FB0A0595E30E8F10",
    "BP-SRC-E0C1EFC6EF3426DB",
    "BP-SRC-2E910C9F974AB137",
}


def check_result_file(result_path: Path, schema_path: Path) -> dict[str, Any]:
    payload = result_path.read_bytes()
    result = read_json(result_path)
    schema = read_json(schema_path)
    failures = validate_schema_instance(result, schema)
    failures.extend(check_result(result))
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "checkerVersion": "closy.static_zeroone_runtime_v2.independent_checker.v1",
        "status": "passed" if not failures else "failed",
        "failures": sorted(set(failures)),
        "resultSha256": sha256_bytes(payload),
        "resultBytes": len(payload),
        "schemaSha256": sha256_bytes(schema_path.read_bytes()),
        "producerRerun": False,
        "independentChecksExecuted": 19,
    }
    receipt["checkerDigest"] = canonical_digest(receipt)
    return receipt


def check_result(result: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    _expect(
        result.get("resultVersion") == "closy.static_zeroone_runtime_v2.result.v2",
        "result_version",
        failures,
    )
    _expect(result.get("protocolId") == PROTOCOL_ID, "protocol_id", failures)
    _expect(result.get("protocolDigest") == PROTOCOL_DIGEST, "protocol_digest", failures)
    _expect(
        result.get("classification") == "public_synthetic_static_runtime_engineering_host_cpu_only",
        "classification",
        failures,
    )
    source = _mapping(result.get("source"))
    _expect(source.get("closyCommit") == SOURCE_COMMIT, "source_commit", failures)
    _expect(source.get("closyTree") == SOURCE_TREE, "source_tree", failures)
    _expect(source.get("zeroOneCommit") == ZEROONE_COMMIT, "zeroone_commit", failures)
    _expect(source.get("zeroOneTree") == ZEROONE_TREE, "zeroone_tree", failures)
    _expect(
        source.get("zeroOneExecutableSha256") == ZEROONE_EXECUTABLE_SHA256,
        "zeroone_executable",
        failures,
    )
    _expect(
        source.get("trustedBuildRecordSha256") == TRUSTED_BUILD_RECORD_SHA256,
        "trusted_build_record",
        failures,
    )

    static_rows = _mapping_rows(result.get("staticZeroOne"), "static_rows", failures)
    _check_static_rows(static_rows, failures)
    runtime_rows = _mapping_rows(result.get("conventionalRuntime"), "runtime_rows", failures)
    _check_runtime_rows(runtime_rows, failures)
    negative = _mapping(result.get("negativeCases"))
    _check_negative_cases(negative, failures)
    _check_denominators(result, static_rows, runtime_rows, negative, failures)
    _check_stages(result, static_rows, failures)
    _check_acceptance(result, static_rows, runtime_rows, negative, failures)
    _check_performance(result, failures)
    failures.extend(_path_hygiene_failures(result))
    _expect(_all_finite(result), "nonfinite_numeric_value", failures)
    return sorted(set(failures))


def publish_static_runtime_v2(repository: Path, transition_commit: str) -> dict[str, Any]:
    evidence = repository / "closy-forge/docs/evidence/static_zeroone_runtime_v2"
    result_path = evidence / "result.json"
    schema_path = repository / "closy-forge/schemas/static_zeroone_runtime_v2/result.schema.json"
    before = result_path.read_bytes()
    receipt = check_result_file(result_path, schema_path)
    if receipt["status"] != "passed":
        raise ValueError(
            "static_runtime_v2_independent_check_failed:" + ",".join(receipt["failures"])
        )
    write_json(evidence / "independent_checker_receipt.json", receipt)

    inventories = build_inventory_chain(repository, transition_commit)
    for name, payload in inventories.items():
        write_json(evidence / name, payload)

    result = read_json(result_path)
    support_counts = Counter(str(row["capabilitySupport"]) for row in result["staticZeroOne"])
    static_outcomes = Counter(str(row["terminalOutcome"]) for row in result["staticZeroOne"])
    runtime_outcomes = Counter(str(row["terminalOutcome"]) for row in result["conventionalRuntime"])
    execution_history = _execution_history(receipt)
    write_json(evidence / "execution_history.json", execution_history)
    write_json(evidence / "host_environment_attestation.json", _host_attestation(result))
    write_json(evidence / "protocol_deviations.json", _protocol_deviations(result))
    write_json(evidence / "blocker_ledger.json", _blocker_ledger(result))
    write_json(
        evidence / "blueprint_status.json",
        _blueprint_status(inventories["blueprint_inventory.json"]),
    )
    write_json(evidence / "stack_manifest.json", _stack_manifest(transition_commit))
    payload = _pr_body_payload(
        result,
        receipt,
        inventories["blueprint_inventory.json"],
        support_counts,
        static_outcomes,
        runtime_outcomes,
        transition_commit,
    )
    write_json(evidence / "pr_body_payload.json", payload)
    write_json(evidence / "resume.json", _resume(payload))
    (evidence / "REPORT.md").write_text(_report(payload), encoding="utf-8", newline="\n")
    (evidence / "README.md").write_text(_readme(), encoding="utf-8", newline="\n")

    if result_path.read_bytes() != before:
        raise ValueError("static_runtime_v2_result_mutated_during_publication")
    inventory = _publication_inventory(evidence)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "publicationVersion": "closy.static_zeroone_runtime_v2.publication.v1",
        "status": "published_failed_engineering_result",
        "resultSha256": receipt["resultSha256"],
        "resultBytes": receipt["resultBytes"],
        "checkerDigest": receipt["checkerDigest"],
        "inventory": inventory,
        "inventoryDigest": canonical_digest(inventory),
        "canonicalEvaluatorRerunCount": 0,
    }
    manifest["publicationDigest"] = canonical_digest(manifest)
    write_json(evidence / "publication_manifest.json", manifest)
    return manifest


def check_publication(repository: Path) -> list[str]:
    failures: list[str] = []
    evidence = repository / "closy-forge/docs/evidence/static_zeroone_runtime_v2"
    result_path = evidence / "result.json"
    schema_path = repository / "closy-forge/schemas/static_zeroone_runtime_v2/result.schema.json"
    receipt = check_result_file(result_path, schema_path)
    if read_json(evidence / "independent_checker_receipt.json") != receipt:
        failures.append("publication_checker_receipt_stale")

    transition66 = read_json(evidence / "inventory_transition_pr66.json")
    transition_commit = str(transition66.get("transitionCommit", ""))
    expected_inventories = build_inventory_chain(repository, transition_commit)
    for name, expected in expected_inventories.items():
        if read_json(evidence / name) != expected:
            failures.append(f"publication_inventory_stale:{name}")

    result = read_json(result_path)
    support = Counter(str(row["capabilitySupport"]) for row in result["staticZeroOne"])
    static_outcomes = Counter(str(row["terminalOutcome"]) for row in result["staticZeroOne"])
    runtime_outcomes = Counter(str(row["terminalOutcome"]) for row in result["conventionalRuntime"])
    final_inventory = expected_inventories["blueprint_inventory.json"]
    expected_payload = _pr_body_payload(
        result,
        receipt,
        final_inventory,
        support,
        static_outcomes,
        runtime_outcomes,
        transition_commit,
    )
    expected_json = {
        "execution_history.json": _execution_history(receipt),
        "host_environment_attestation.json": _host_attestation(result),
        "protocol_deviations.json": _protocol_deviations(result),
        "blocker_ledger.json": _blocker_ledger(result),
        "blueprint_status.json": _blueprint_status(final_inventory),
        "stack_manifest.json": _stack_manifest(transition_commit),
        "pr_body_payload.json": expected_payload,
        "resume.json": _resume(expected_payload),
    }
    for name, expected in expected_json.items():
        if read_json(evidence / name) != expected:
            failures.append(f"publication_artifact_stale:{name}")
    if (evidence / "REPORT.md").read_text(encoding="utf-8") != _report(expected_payload):
        failures.append("publication_report_stale")
    if (evidence / "README.md").read_text(encoding="utf-8") != _readme():
        failures.append("publication_readme_stale")

    manifest = read_json(evidence / "publication_manifest.json")
    inventory = _publication_inventory(evidence)
    if manifest.get("inventory") != inventory:
        failures.append("publication_file_inventory_stale")
    if manifest.get("inventoryDigest") != canonical_digest(inventory):
        failures.append("publication_inventory_digest_invalid")
    if manifest.get("publicationDigest") != canonical_digest(manifest, "publicationDigest"):
        failures.append("publication_digest_invalid")
    if manifest.get("resultSha256") != receipt["resultSha256"]:
        failures.append("publication_result_substituted")
    for path in evidence.glob("*.json"):
        failures.extend(f"{path.name}:{item}" for item in _path_hygiene_failures(read_json(path)))
    return sorted(set(failures))


def build_inventory_chain(repository: Path, transition_commit: str) -> dict[str, dict[str, Any]]:
    parent = read_json(
        repository / "closy-forge/docs/evidence/capture_reconstruction_v2/blueprint_inventory.json"
    )
    pr64 = _updated_inventory(
        parent,
        "solver_material_v2_current",
        {
            str(row["id"]): (
                "partial",
                [PR64_ANCHOR],
                "solver_material_v2_executed_but_failed_SMV2_01_and_real_coupon_physical_validation_not_run",
            )
            for row in parent["requirements"]
            if str(row["phase"]) == "7"
        },
    )
    pr65 = _updated_inventory(
        pr64,
        "manual_provider_c3_v1_current",
        {
            requirement_id: (
                "partial",
                [PR65_ANCHOR],
                "manual_provider_topology_semantics_binding_and_9x11_C3_executed_but_strict_scoped_C3_failed_MPC3_09",
            )
            for requirement_id in PR65_PARTIAL_IDS
        },
    )
    pr66_updates = {
        requirement_id: (
            "partial",
            [PR66_ANCHOR],
            "static_host_CPU_runtime_v2_executed_with_conventional_and_ZeroOne_partial_failures_no_dynamic_mobile_or_product_claim",
        )
        for requirement_id in PR66_PARTIAL_IDS
    }
    pr66_updates.update(
        {
            requirement_id: (
                "not_run",
                [PR66_ANCHOR],
                "explicitly_not_run_by_static_runtime_v2_scope_or_failed_prerequisite",
            )
            for requirement_id in PR66_NOT_RUN_IDS
        }
    )
    pr66 = _updated_inventory(pr65, "static_zeroone_runtime_v2_current", pr66_updates)
    transition64 = build_inventory_transition(parent, pr64, PR64_HEAD)
    transition65 = build_inventory_transition(pr64, pr65, PR65_HEAD)
    transition66 = build_inventory_transition(pr65, pr66, transition_commit)
    transitions: dict[str, Any] = {
        "schemaVersion": 1,
        "transitionSetVersion": "closy.blueprint_inventory_transition_set.v1",
        "transitions": [transition64, transition65, transition66],
    }
    transitions["transitionSetDigest"] = canonical_digest(transitions)
    for inventory in (pr64, pr65, pr66):
        failures = validate_decorated_inventory(repository, inventory)
        if failures:
            raise ValueError("static_runtime_v2_inventory_invalid:" + ",".join(failures))
    return {
        "blueprint_inventory_pr64.json": pr64,
        "blueprint_inventory_pr65.json": pr65,
        "blueprint_inventory.json": pr66,
        "inventory_transition_pr64.json": transition64,
        "inventory_transition_pr65.json": transition65,
        "inventory_transition_pr66.json": transition66,
        "inventory_transitions.json": transitions,
    }


def validate_schema_instance(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    failures: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None and not _schema_type_matches(value, expected_type):
        return [f"schema_type:{path}:{expected_type}"]
    if "const" in schema and value != schema["const"]:
        failures.append(f"schema_const:{path}")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"schema_enum:{path}")
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                failures.append(f"schema_required:{path}.{key}")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, Mapping):
                    failures.extend(
                        validate_schema_instance(value[key], child_schema, f"{path}.{key}")
                    )
        if schema.get("additionalProperties") is False and isinstance(properties, Mapping):
            for key in value:
                if key not in properties:
                    failures.append(f"schema_additional_property:{path}.{key}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            failures.append(f"schema_min_items:{path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            failures.append(f"schema_max_items:{path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                failures.extend(validate_schema_instance(item, item_schema, f"{path}[{index}]"))
    return failures


def _check_static_rows(rows: list[Mapping[str, Any]], failures: list[str]) -> None:
    _expect(len(rows) == 9, "static_row_count", failures)
    _expect(
        {str(row.get("family")) for row in rows} == set(FAMILIES), "static_family_set", failures
    )
    for row in rows:
        family = str(row.get("family"))
        support = row.get("capabilitySupport")
        outcome = row.get("terminalOutcome")
        _expect(support in {"supported", "unsupported"}, f"static_support:{family}", failures)
        _expect(outcome in TERMINAL_OUTCOMES, f"static_outcome:{family}", failures)
        _expect(
            row.get("fallbackSha256Before") == row.get("fallbackSha256After"),
            f"fallback_identity:{family}",
            failures,
        )
        _expect(
            row.get("conventionalFallbackAvailable") is True,
            f"fallback_available:{family}",
            failures,
        )
        audit = _mapping(row.get("conventionalFallbackGeometryAudit"))
        expected_valid = audit.get("status") == "pass"
        _expect(
            row.get("conventionalFallbackGeometryValid") is expected_valid,
            f"fallback_geometry_state:{family}",
            failures,
        )
        _expect(
            row.get("optionalDerivativeSelectedForRuntime") is (outcome == "passed"),
            f"derivative_selection:{family}",
            failures,
        )


def _check_runtime_rows(rows: list[Mapping[str, Any]], failures: list[str]) -> None:
    expected_keys = {
        (family, profile, rebuild)
        for family in FAMILIES
        for profile in PROFILES
        for rebuild in (1, 2)
    }
    actual_keys = {
        (str(row.get("family")), str(row.get("profileId")), row.get("rebuild")) for row in rows
    }
    _expect(len(rows) == 36 and actual_keys == expected_keys, "runtime_matrix", failures)
    digests: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = f"{row.get('family')}:{row.get('profileId')}:{row.get('rebuild')}"
        outcome = row.get("terminalOutcome")
        _expect(outcome in TERMINAL_OUTCOMES, f"runtime_outcome:{key}", failures)
        audit = _mapping(row.get("glbGeometryAudit"))
        expected_outcome = "passed" if audit.get("status") == "pass" else "corrupt_or_invalid"
        _expect(outcome == expected_outcome, f"runtime_geometry_outcome:{key}", failures)
        _expect(
            (row.get("failureReason") is None) is (outcome == "passed"),
            f"runtime_failure_reason:{key}",
            failures,
        )
        _expect(
            _bounded_number(row.get("maximumDecodedPageBytes"), 0, 65_536),
            f"runtime_page_bound:{key}",
            failures,
        )
        _expect(
            _bounded_number(row.get("maximumDecompressionRatio"), 0, 128),
            f"runtime_ratio_bound:{key}",
            failures,
        )
        _expect(
            _bounded_number(row.get("maximumPosePositionErrorMeters"), 0, 1e-6),
            f"runtime_pose_error:{key}",
            failures,
        )
        _expect(
            row.get("poseBoundsContainEveryVertex") is True, f"runtime_pose_bounds:{key}", failures
        )
        _expect(
            row.get("uniqueCompressedBlobCount", 0) > 0, f"runtime_compressed_blob:{key}", failures
        )
        _expect(
            row.get("smallerThanEquivalentDuplicateStorageV1") is True,
            f"runtime_compression:{key}",
            failures,
        )
        fallback = _mapping(row.get("fallbackPrefix"))
        _expect(fallback.get("verified") is True, f"runtime_fallback_prefix:{key}", failures)
        resumes = row.get("resume")
        _expect(
            isinstance(resumes, list) and len(resumes) == 3, f"runtime_resume_count:{key}", failures
        )
        if isinstance(resumes, list):
            _expect(
                {str(item.get("point")) for item in resumes if isinstance(item, Mapping)}
                == set(RESUME_POINTS),
                f"runtime_resume_points:{key}",
                failures,
            )
            _expect(
                all(
                    isinstance(item, Mapping) and item.get("aggregateHashMatch") is True
                    for item in resumes
                ),
                f"runtime_resume_identity:{key}",
                failures,
            )
        claims = _mapping(row.get("claims"))
        _expect(
            claims == {"hostCpu": True, "mobile": False, "gpu": False, "network": False},
            f"runtime_claims:{key}",
            failures,
        )
        digests[(str(row.get("family")), str(row.get("profileId")))].add(
            str(row.get("packageDigest"))
        )
    _expect(
        all(len(values) == 1 for values in digests.values()), "runtime_rebuild_identity", failures
    )


def _check_negative_cases(cases: Mapping[str, Any], failures: list[str]) -> None:
    _expect(set(cases) == NEGATIVE_CASES, "negative_case_set", failures)
    for name, row_value in cases.items():
        row = _mapping(row_value)
        _expect(isinstance(row.get("passed"), bool), f"negative_terminal:{name}", failures)
    cross = _mapping(cases.get("cross_package_chunk"))
    _expect(cross.get("passed") is False, "cross_package_result_changed", failures)
    _expect(
        cross.get("failureReason") == "transfer_chunk_size_mismatch",
        "cross_package_observed_reason",
        failures,
    )


def _check_denominators(
    result: Mapping[str, Any],
    static_rows: list[Mapping[str, Any]],
    runtime_rows: list[Mapping[str, Any]],
    negative: Mapping[str, Any],
    failures: list[str],
) -> None:
    denominators = _mapping(result.get("denominators"))
    static_counts = Counter(str(row.get("terminalOutcome")) for row in static_rows)
    runtime_counts = Counter(str(row.get("terminalOutcome")) for row in runtime_rows)
    expected = {
        "staticFamilyCount": 9,
        "staticPassedCount": static_counts["passed"],
        "staticFailedCount": static_counts["failed"],
        "staticUnsupportedCount": static_counts["unsupported"],
        "staticCorruptOrInvalidCount": static_counts["corrupt_or_invalid"],
        "runtimeBuildCount": 36,
        "runtimePassedCount": runtime_counts["passed"],
        "runtimeFailedCount": runtime_counts["failed"],
        "runtimeCorruptOrInvalidCount": runtime_counts["corrupt_or_invalid"],
        "profileCount": 2,
        "cleanRebuildsPerProfile": 2,
        "poseCountPerBuild": 4,
        "resumePointCountPerBuild": 3,
        "negativeCaseCount": len(negative),
    }
    _expect(denominators == expected, "denominators", failures)
    _expect(sum(static_counts.values()) == 9, "static_terminal_conservation", failures)
    _expect(sum(runtime_counts.values()) == 36, "runtime_terminal_conservation", failures)


def _check_stages(
    result: Mapping[str, Any], rows: list[Mapping[str, Any]], failures: list[str]
) -> None:
    published = _mapping(result.get("stageOutcome"))
    _expect(set(published) == set(STAGES), "stage_set", failures)
    for stage in STAGES:
        row = _mapping(published.get(stage))
        terminal = sum(
            int(row.get(name, 0))
            for name in ("passed", "failed", "not_run", "dependency_blocked", "corrupt_or_invalid")
        )
        _expect(row.get("planned") == len(rows), f"stage_planned:{stage}", failures)
        _expect(
            terminal == len(rows) and row.get("terminalConservation") is True,
            f"stage_conservation:{stage}",
            failures,
        )


def _check_acceptance(
    result: Mapping[str, Any],
    static_rows: list[Mapping[str, Any]],
    runtime_rows: list[Mapping[str, Any]],
    negative: Mapping[str, Any],
    failures: list[str],
) -> None:
    acceptance = _mapping(result.get("acceptance"))
    static_all = all(row.get("terminalOutcome") == "passed" for row in static_rows)
    runtime_all = all(row.get("terminalOutcome") == "passed" for row in runtime_rows)
    negative_all = all(_mapping(row).get("passed") is True for row in negative.values())
    _expect(
        acceptance.get("allNineFamiliesAccounted") is True, "acceptance_family_accounting", failures
    )
    _expect(acceptance.get("allNineFamiliesProcessed") is static_all, "acceptance_static", failures)
    _expect(
        acceptance.get("allThirtySixRuntimeBuildsPassed") is runtime_all,
        "acceptance_runtime",
        failures,
    )
    _expect(
        acceptance.get("allNegativeCasesRejectedOrRecovered") is negative_all,
        "acceptance_negative",
        failures,
    )
    _expect(
        result.get("literalOutcome") == "static_runtime_v2_engineering_failed_global_partial",
        "literal_outcome",
        failures,
    )
    for claim in (
        "canonicalAuthorityChanged",
        "productRuntimeDefaultChanged",
        "dynamicZ2Claimed",
        "mobileClaimed",
        "gpuClaimed",
        "productionNetworkClaimed",
        "globalBlueprintComplete",
    ):
        _expect(acceptance.get(claim) is False, f"forbidden_claim:{claim}", failures)


def _check_performance(result: Mapping[str, Any], failures: list[str]) -> None:
    performance = _mapping(result.get("performance"))
    for key in (
        "totalWallNanoseconds",
        "totalCpuNanoseconds",
        "pythonTracedPeakBytes",
        "zeroOnePeakMemoryBytesMaximum",
    ):
        _expect(
            isinstance(performance.get(key), int) and performance[key] > 0,
            f"performance:{key}",
            failures,
        )
    host = _mapping(result.get("host"))
    _expect(host.get("cpuOnly") is True, "host_cpu_only", failures)
    _expect(
        host.get("measurementScope") == "host_cpu_not_mobile_gpu_battery_thermal_or_network",
        "host_scope",
        failures,
    )


def _updated_inventory(
    parent: Mapping[str, Any],
    label: str,
    updates: Mapping[str, tuple[str, list[str], str]],
) -> dict[str, Any]:
    inventory = copy.deepcopy(dict(parent))
    rows = {str(row["id"]): row for row in inventory["requirements"]}
    missing = set(updates) - set(rows)
    if missing:
        raise ValueError("blueprint_update_ids_missing:" + ",".join(sorted(missing)))
    for requirement_id, (status, anchors, reason) in updates.items():
        row = rows[requirement_id]
        row["status"] = status
        row["evidenceAnchors"] = anchors
        row["reason"] = reason
    counts = Counter(str(row["status"]) for row in inventory["requirements"])
    phases: defaultdict[str, list[str]] = defaultdict(list)
    for row in inventory["requirements"]:
        phases[str(row["phase"])].append(str(row["status"]))
    inventory["inventoryLabel"] = label
    inventory["statusCounts"] = {status: counts.get(status, 0) for status in STATUS_ORDER}
    inventory["phaseSummaries"] = {
        phase: _reduce_phase(states) for phase, states in sorted(phases.items())
    }
    inventory["summaryReductionVersion"] = "closy.phase_status_reduction.v2"
    inventory["inventoryDigest"] = canonical_digest(inventory, "inventoryDigest")
    return inventory


def _reduce_phase(statuses: list[str]) -> str:
    if statuses and all(status == "complete" for status in statuses):
        return "complete"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status in {"partial", "superseded"} for status in statuses):
        return "partial"
    if statuses and all(status == "dependency_blocked" for status in statuses):
        return "dependency_blocked"
    if any(status == "discovery_pending" for status in statuses):
        return "discovery_pending"
    return "not_started"


def _execution_history(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "historyVersion": "closy.static_zeroone_runtime_v2.execution_history.v1",
        "events": [
            {
                "ordinal": 1,
                "terminalOutcome": "failed",
                "reason": "managed_root_path_length_native_page_pack_metadata_publication_failed",
                "resultPublished": False,
            },
            {
                "ordinal": 2,
                "terminalOutcome": "integrity_error",
                "reason": "external_session_interrupted_before_atomic_result_publication",
                "resultPublished": False,
            },
            {
                "ordinal": 3,
                "terminalOutcome": "failed",
                "reason": "zeroone_static_family_process_failed_before_conventional_matrix",
                "family": "long_sleeved_top",
                "resultPublished": False,
            },
            {
                "ordinal": 4,
                "terminalOutcome": "failed",
                "reason": "conventional_fallback_geometry_invalid_before_terminal_accounting_fix",
                "family": "long_sleeved_top",
                "resultPublished": False,
            },
            {
                "ordinal": 5,
                "terminalOutcome": "passed",
                "reason": "atomic_result_publication_completed",
                "resultPublished": True,
                "resultSha256": receipt["resultSha256"],
            },
        ],
        "publishedResultCount": 1,
        "scientificAttemptConsumed": False,
        "y2AuthorityConsumed": False,
        "canonicalCandidateConsumed": False,
        "topologyStrategyConsumed": False,
    }
    value["historyDigest"] = canonical_digest(value)
    return value


def _host_attestation(result: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "attestationVersion": "closy.static_zeroone_runtime_v2.host_environment.v1",
        "resultHost": result["host"],
        "cpuModel": "Intel(R) Core(TM) i7-6700HQ CPU @ 2.60GHz",
        "physicalCoreCount": 4,
        "logicalProcessorCount": 8,
        "physicalMemoryBytes": 17_124_024_320,
        "operatingSystem": "Microsoft Windows 10 Home",
        "operatingSystemVersion": "10.0.19045",
        "operatingSystemBuild": "19045",
        "operatingSystemArchitecture": "64-bit",
        "physicalMobileDeviceCount": 0,
        "mobileLatency": "not_run",
        "mobileMemory": "not_run",
        "mobileThermal": "not_run",
        "mobileBattery": "not_run",
        "dynamicZ2": "not_run",
        "productionRuntime": False,
    }
    value["attestationDigest"] = canonical_digest(value)
    return value


def _protocol_deviations(result: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "deviationVersion": "closy.static_zeroone_runtime_v2.protocol_deviations.v1",
        "negativeCaseNaming": {
            "preregistered": "truncated_chunk",
            "observed": "truncated_stream",
            "semanticCoverage": "stream_payload_truncation_rejected_before_materialization",
            "classification": "name_mismatch_disclosed_not_silently_equated",
        },
        "crossPackageControl": {
            "expectedFailureReason": "transfer_chunk_hash_mismatch",
            "observedFailureReason": _mapping(
                _mapping(result["negativeCases"])["cross_package_chunk"]
            ).get("failureReason"),
            "terminalOutcome": "failed",
            "firstUnmetPredicate": "cross_package_control_exact_failure_reason",
        },
    }
    value["deviationDigest"] = canonical_digest(value)
    return value


def _blocker_ledger(result: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "ledgerVersion": "closy.static_zeroone_runtime_v2.blockers.v1",
        "firstUnmetPredicate": "allConventionalFallbackGeometryValid",
        "engineeringResult": result["literalOutcome"],
        "blocked": [
            {
                "area": "real_private_capture",
                "state": "dependency_blocked",
                "dependency": "consented private captures and independent custody",
            },
            {
                "area": "physical_material",
                "state": "dependency_blocked",
                "dependency": "measured fabric coupons equipment environment and uncertainty",
            },
            {
                "area": "licensed_avatar",
                "state": "dependency_blocked",
                "dependency": "licensed body/avatar models or authorised biometric inputs",
            },
            {
                "area": "provider_weights",
                "state": "dependency_blocked",
                "dependency": "approved weights licence compute or paid-service authority",
            },
            {
                "area": "physical_mobile",
                "state": "not_run",
                "dependency": "physical target mobile devices",
            },
            {
                "area": "human_review",
                "state": "dependency_blocked",
                "dependency": "human perceptual and garment-expert review",
            },
            {
                "area": "new_scientific_attempt",
                "state": "dependency_blocked",
                "dependency": "new Y2/scientific-attempt authority",
            },
        ],
        "ordinaryProjectWorkBlocked": False,
    }
    value["ledgerDigest"] = canonical_digest(value)
    return value


def _blueprint_status(inventory: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "statusVersion": "closy.blueprint_status.static_runtime_v2.v1",
        "inventoryDigest": inventory["inventoryDigest"],
        "statusCounts": inventory["statusCounts"],
        "phaseSummaries": inventory["phaseSummaries"],
        "sourceBlockCounts": inventory["sourceBlockCounts"],
        "sourceBlockCount": inventory["sourceBlockCount"],
        "mappedNormativeBlockCount": inventory["mappedNormativeBlockCount"],
        "unmappedNormativeBlockCount": inventory["unmappedNormativeBlockCount"],
        "globalBlueprintComplete": False,
    }
    value["statusDigest"] = canonical_digest(value)
    return value


def _stack_manifest(transition_commit: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "stackVersion": "closy.forge.pr62_66.stack.v1",
        "pullRequests": [
            {
                "number": 62,
                "head": "0189d2f969ff9a17cdfec8c1843b26981ffa388a",
                "parent": "8ccf6fa95d6ac5653f3c9dd45f2cf605038c73c8",
            },
            {
                "number": 63,
                "head": "fad7ff76b1a92643229c2db1d7fb62b57e4ce90d",
                "parent": "0189d2f969ff9a17cdfec8c1843b26981ffa388a",
            },
            {"number": 64, "head": PR64_HEAD, "parent": "fad7ff76b1a92643229c2db1d7fb62b57e4ce90d"},
            {"number": 65, "head": PR65_HEAD, "parent": PR64_HEAD},
            {
                "number": 66,
                "evidenceTransitionCommit": transition_commit,
                "parent": PR65_HEAD,
                "finalHeadExternalAttestationRequired": True,
            },
        ],
        "exactLinearAncestry": True,
        "createdPullRequestAllowanceConsumed": 4,
        "additionalPullRequestAuthorised": False,
    }
    value["stackDigest"] = canonical_digest(value)
    return value


def _pr_body_payload(
    result: Mapping[str, Any],
    receipt: Mapping[str, Any],
    inventory: Mapping[str, Any],
    support: Counter[str],
    static_outcomes: Counter[str],
    runtime_outcomes: Counter[str],
    transition_commit: str,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "payloadVersion": "closy.static_zeroone_runtime_v2.pr_body.v1",
        "parentHead": PR65_HEAD,
        "sourceCommit": SOURCE_COMMIT,
        "sourceTree": SOURCE_TREE,
        "checkerTransitionCommit": transition_commit,
        "protocolDigest": PROTOCOL_DIGEST,
        "resultSha256": receipt["resultSha256"],
        "checkerDigest": receipt["checkerDigest"],
        "literalOutcome": result["literalOutcome"],
        "firstUnmetPredicate": "allConventionalFallbackGeometryValid",
        "staticCapabilitySupport": dict(sorted(support.items())),
        "staticTerminalOutcomes": dict(sorted(static_outcomes.items())),
        "runtimeTerminalOutcomes": dict(sorted(runtime_outcomes.items())),
        "denominators": result["denominators"],
        "blueprintInventoryDigest": inventory["inventoryDigest"],
        "blueprintStatusCounts": inventory["statusCounts"],
        "evidenceTier": "public_synthetic_static_host_cpu_engineering",
        "unsupportedTiers": [
            "real_private",
            "physical_coupon",
            "physical_mobile",
            "dynamic_Z2",
            "production_runtime",
        ],
        "workflowUrlsExcludedFromCanonicalPayload": True,
    }
    value["payloadDigest"] = canonical_digest(value)
    return value


def _resume(payload: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "resumeVersion": "closy.static_zeroone_runtime_v2.resume.v1",
        "status": "bounded_pass_complete_with_failed_engineering_result",
        "nextBranchProposedOnly": "codex/closy-forge-all-family-layer-integration-v1",
        "nextBase": "final_PR66_head_external_attestation",
        "resultSha256": payload["resultSha256"],
        "inventoryDigest": payload["blueprintInventoryDigest"],
        "newPullRequestAuthorised": False,
    }
    value["resumeDigest"] = canonical_digest(value)
    return value


def _report(payload: Mapping[str, Any]) -> str:
    return (
        "# Static ZeroOne and conventional runtime V2\n\n"
        f"- Result: `{payload['literalOutcome']}`\n"
        f"- Result SHA-256: `{payload['resultSha256']}`\n"
        f"- First unmet predicate: `{payload['firstUnmetPredicate']}`\n"
        f"- Static outcomes: `{payload['staticTerminalOutcomes']}`\n"
        f"- Runtime outcomes: `{payload['runtimeTerminalOutcomes']}`\n"
        "- Scope: public synthetic, static host CPU engineering only.\n"
        "- Mobile, dynamic Z2, GPU, networking, and production runtime were not claimed.\n"
        "- The canonical garment package and conventional GLB remain authoritative; "
        "ZeroOne bytes are derivative.\n"
    )


def _readme() -> str:
    return (
        "# Evidence contents\n\n"
        "This directory contains the immutable producer result, independent checker receipt, "
        "append-only execution history, source-derived blueprint transitions, and publication "
        "manifest. Workflow URLs and final GitHub job states are intentionally external to "
        "canonical artifacts.\n"
    )


def _publication_inventory(evidence: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(evidence).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_bytes(path.read_bytes()),
        }
        for path in sorted(evidence.rglob("*"))
        if path.is_file() and path.name != "publication_manifest.json"
    ]


def _schema_type_matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_schema_type_matches(value, item) for item in expected)
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(str(expected), True)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any, label: str, failures: list[str]) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        failures.append(label)
        return []
    return list(value)


def _bounded_number(value: Any, minimum: float, maximum: float) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and minimum <= value <= maximum
    )


def _all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return all(_all_finite(item) for item in value)
    return True


def _path_hygiene_failures(value: Any, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(value, str):
        if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/Users/", "/home/")):
            failures.append(f"absolute_path:{path}")
        if any(token in value.lower() for token in ("zlerk", "z1w")):
            failures.append(f"private_path_token:{path}")
    elif isinstance(value, Mapping):
        for key, child in value.items():
            failures.extend(_path_hygiene_failures(child, f"{path}.{key}"))
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for index, child in enumerate(value):
            failures.extend(_path_hygiene_failures(child, f"{path}[{index}]"))
    return failures


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)
