"""Publish verified saved V2 evidence without rebuilding or regenerating motion."""

from __future__ import annotations

import argparse
import math
import re
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb, audit_glb_geometry, read_glb_meshset
from closy_forge.manual_provider_binding_v2.checker import check_rest
from closy_forge.manual_provider_binding_v2.evaluation import (
    BASELINE_SOURCES,
    UNIT_A_FAMILIES,
    _baseline_metrics,
    _report,
    derive_gates,
    failed_rows,
    input_inventory,
    protocol_document,
    source_inventory,
)
from closy_forge.manual_provider_binding_v2.package import (
    PACKAGE_BYTE_LIMIT,
    PACKAGE_VERSION,
    RUNTIME_PATHS,
    digest_json,
    motion_row,
    read_positions,
    semantic_summary,
)
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import canonical_dumps, canonical_text_bytes
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import loads_strict_json_object

FORGE = Path(__file__).resolve().parents[1]
VERSION = "closy.binding_v2.saved_evidence_publication.v1"
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
STATE_IDS = [state.state_id for state in MOTION_STATES]
AUTHORITY = {
    "canonicalGarment": False,
    "globalC3Complete": False,
    "scientificQualification": False,
    "physicalOrMobileEvidence": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(f"binding_publication_{code}")


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(
        path.exists()
        and getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _file(root: Path, relative: str, *, limit: int = MAX_DOCUMENT_BYTES) -> Path:
    validate_package_relpath(relative)
    path = root / relative
    _require(not any(_linked(p) for p in (path, *path.parents)), "link_forbidden")
    _require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), "file_missing")
    _require(path.stat().st_size <= limit, "file_budget")
    return path


def _json(raw: bytes) -> Any:
    # Wrapping extends strict duplicate-key/nonfinite/shape checks to the rows array.
    result = loads_strict_json_object(
        '{"value":' + raw.decode("utf-8") + "}",
        maximum_bytes=MAX_DOCUMENT_BYTES + 16,
        maximum_items=1_000_000,
    )
    return result["value"]


def _document(root: Path, relative: str) -> Any:
    return _json(_file(root, relative).read_bytes())


def _identity(document: dict[str, Any], field: str) -> str:
    body = dict(document)
    digest = body.pop(field, None)
    _require(isinstance(digest, str) and digest_json(body) == digest, f"{field}_mismatch")
    return str(digest)


def _exact(actual: Any, expected: Any, code: str) -> None:
    # Unlike Python equality this distinguishes true/1 and numeric status forgeries.
    _require(canonical_dumps(actual) == canonical_dumps(expected), code)


def _rows(rows: list[dict[str, Any]], source_id: str, family: str) -> None:
    _exact([r.get("stateId") for r in rows], STATE_IDS, "state_inventory_mismatch")
    _require(
        all(
            r.get("sourceId") == source_id
            and r.get("family") == family
            and r.get("status") in ("pass", "fail")
            for r in rows
        ),
        "row_identity_mismatch",
    )


def _inventory(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    _require(not any(_linked(p) for p in (root, *root.parents)), "link_forbidden")
    rows = []
    pending = [root]
    directories = 0
    while pending:
        parent = pending.pop()
        directories += 1
        for path in sorted(parent.iterdir()):
            _require(not _linked(path), "link_forbidden")
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                _file(root, path.relative_to(root).as_posix(), limit=PACKAGE_BYTE_LIMIT)
                rows.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            _require(len(rows) + len(pending) + directories <= 128, "inventory_budget")
    return sorted(rows, key=lambda row: row["path"])


def validate_saved_package(
    root: Path, declared: dict[str, Any], *, source_id: str, family: str
) -> dict[str, Any]:
    """Independent rest and saved-position metrics; no motion source regeneration."""
    manifest = _document(root, "manifest.json")
    package_digest = _identity(manifest, "packageDigest")
    _require(
        manifest.get("schemaVersion") == 2
        and manifest.get("packageVersion") == PACKAGE_VERSION
        and manifest.get("units") == "metres"
        and manifest.get("scope") == "manual_provider_binding_v2_development",
        "package_contract_mismatch",
    )
    for key, value in (
        ("sourceId", source_id),
        ("family", family),
        ("packageId", f"package:{source_id}:manual-provider-binding-v2"),
    ):
        _exact(manifest.get(key), value, "package_identity_mismatch")
        _exact(declared.get(key), value, "attempt_package_identity_mismatch")
    _exact(declared.get("packageDigest"), package_digest, "attempt_package_digest_mismatch")
    _exact(manifest.get("runtime"), RUNTIME_PATHS, "runtime_contract_mismatch")
    _exact(manifest.get("authority"), AUTHORITY, "authority_claim_mismatch")
    inventory = _inventory(root)
    assets = [row for row in inventory if row["path"] != "manifest.json"]
    for row in manifest["inventory"]:
        validate_package_relpath(row["path"])
    _exact(manifest["inventory"], assets, "package_inventory_mismatch")
    _require(len(assets) <= 64, "package_inventory_budget")
    byte_count = sum(row["bytes"] for row in inventory)
    _exact(declared.get("packageBytes"), byte_count, "package_size_mismatch")
    for field, path in (
        ("inputCleanSha256", "render/clean.glb"),
        ("inputSemanticsSha256", "semantic/source.json"),
    ):
        _exact(manifest.get(field), sha256_file(_file(root, path)), "package_input_mismatch")
    rest = check_rest(
        root / "render/fallback.glb", root / "render/clean.glb", root / "binding/local_frame_v2.bin"
    )
    _exact(_document(root, "reports/rest.json"), rest, "serialized_rest_receipt_mismatch")
    _exact(declared.get("rest"), rest, "attempt_rest_receipt_mismatch")
    binding_report = _document(root, "reports/binding.json")
    for key in ("restMaximumErrorMeters", "restP95ErrorMeters", "restRmsErrorMeters"):
        if key == "restRmsErrorMeters" and key not in binding_report:
            continue
        metric = binding_report.get(key)
        _require(
            type(metric) in (int, float)
            and math.isfinite(metric)
            and abs(metric - rest[key]) <= 2e-6,
            "binding_rest_metric_mismatch",
        )
    geometry = {
        name: {"geometry": audit_glb_geometry(root / path), "attributes": audit_glb(root / path)}
        for name, path in (("render", "render/clean.glb"), ("cage", "render/fallback.glb"))
    }
    _exact(_document(root, "reports/geometry.json"), geometry, "geometry_report_mismatch")
    _exact(declared.get("geometry"), geometry, "attempt_geometry_mismatch")
    geometry_ok = all(
        g["geometry"]["status"] == "pass" and g["attributes"]["hasVec4Tangents"]
        for g in geometry.values()
    )
    clean = read_glb_meshset(root / "render/clean.glb")
    semantics = _document(root, "semantic/source.json")
    summary = semantic_summary(clean, semantics)
    _exact(_document(root, "reports/semantics.json"), summary, "semantics_report_mismatch")
    _exact(declared.get("semantics"), summary, "attempt_semantics_mismatch")
    motion = _document(root, "motion/manifest.json")
    _exact(motion.get("format"), "little_endian_float32_xyz_zlib9", "motion_format_mismatch")
    _exact(motion.get("stateIds"), STATE_IDS, "motion_states_mismatch")
    _exact(
        motion.get("stateParameters"),
        [asdict(s) for s in MOTION_STATES],
        "motion_parameters_mismatch",
    )
    _rows(motion["rows"], source_id, family)
    payloads = {
        name: read_positions(
            _file(root, f"motion/{name}_states.f32.zlib"), motion["payloads"][name]
        )
        for name in ("cage", "production", "reference")
    }
    for name, states in payloads.items():
        count = rest["cageVertexCount"] if name == "cage" else rest["renderVertexCount"]
        _require(len(states) == 11 and all(len(s) == count for s in states), "motion_payload_count")
    for index, state in enumerate(MOTION_STATES):
        observed = motion_row(
            clean,
            payloads["production"][index],
            payloads["reference"][index],
            semantics,
            state,
            source_id,
            family,
        )
        _exact(motion["rows"][index], observed, "saved_motion_metric_mismatch")
    _exact(declared.get("rows"), motion["rows"], "attempt_motion_rows_mismatch")
    expected_status = (
        "pass"
        if (
            rest["status"] == summary["status"] == "pass"
            and geometry_ok
            and all(row["status"] == "pass" for row in motion["rows"])
            and byte_count <= PACKAGE_BYTE_LIMIT
        )
        else "fail"
    )
    for field, expected in (
        ("status", expected_status),
        ("geometryValid", geometry_ok),
        ("inputCleanSha256", manifest["inputCleanSha256"]),
        ("motionStateCount", 11),
        ("independentRestReconstruction", True),
        ("motionVerification", "decoded_cage_runtime_and_immutable_dense_reference"),
        (
            "binding",
            {
                **binding_report,
                **rest,
                "coverage": rest["recordCount"] / rest["renderVertexCount"],
                "outOfDomainCount": 0,
            },
        ),
    ):
        _exact(declared.get(field), expected, f"package_{field}_mismatch")
    _exact(_inventory(root), inventory, "package_changed_during_validation")
    return {
        "id": source_id,
        "family": family,
        "manifest": manifest,
        "manifestSha256": sha256_file(root / "manifest.json"),
        "independentRest": rest,
        "status": expected_status,
        "packageBytes": byte_count,
        "motionCheckScope": "saved_positions_metrics_and_hashes_no_motion_regeneration",
    }


def _validate_attempt(
    attempt: dict[str, Any], root: Path, source_id: str, family: str
) -> dict[str, Any]:
    _rows(attempt["rows"], source_id, family)
    if "package" not in attempt:
        reason = attempt.get("error", attempt.get("reason"))
        _require(
            attempt.get("status") == "fail" and isinstance(reason, str) and bool(reason),
            "failed_attempt_reason_missing",
        )
        _exact(
            attempt["rows"], failed_rows(source_id, family, reason), "failed_attempt_rows_mismatch"
        )
        return {
            "id": source_id,
            "family": family,
            "status": "failed_no_package",
            "reason": reason,
            "retainedPartialFiles": _inventory(root),
        }
    package = attempt["package"]
    receipt = validate_saved_package(root, package, source_id=source_id, family=family)
    _exact(
        attempt["rows"],
        [{**row, "packageDigest": package["packageDigest"]} for row in package["rows"]],
        "row_package_association_mismatch",
    )
    return receipt


def prepare_publication(evaluation: Path, *, forge_root: Path = FORGE) -> dict[str, bytes]:
    """Validate completely before creating output; callers may inspect in memory."""
    names = (
        "protocol.json",
        "source_inventory.json",
        "input_inventory.json",
        "result.json",
        "baseline_rows.json",
        "checkpoint.json",
        "report.md",
    )
    raw = {name: _file(evaluation, name).read_bytes() for name in names}
    docs = {name: _json(data) for name, data in raw.items() if name.endswith(".json")}
    result, protocol, sources, inputs, checkpoint = (
        docs[name]
        for name in (
            "result.json",
            "protocol.json",
            "source_inventory.json",
            "input_inventory.json",
            "checkpoint.json",
        )
    )
    _identity(result, "resultDigest")
    _require(
        result.get("schemaVersion") == 2
        and result.get("version") == "closy.manual_provider_binding_v2.result.v2"
        and result.get("scope") == "manual_provider_binding_v2_development",
        "result_version_mismatch",
    )
    _exact(protocol, protocol_document(forge_root), "protocol_changed")
    _require(
        set(sources) == {"head", "files", "digest"}
        and re.fullmatch(r"[0-9a-f]{40}", str(sources["head"])) is not None,
        "source_inventory_shape",
    )
    _exact(sources["digest"], digest_json(sources["files"]), "source_inventory_digest")
    _exact(sources["files"], source_inventory(forge_root), "source_changed")
    input_body = dict(inputs)
    input_digest = input_body.pop("digest", None)
    _exact(input_digest, digest_json(input_body), "input_inventory_digest")
    source_root, unit_a_root = Path(input_body["sourceRoot"]), Path(input_body["unitARoot"])
    _require(source_root.is_absolute() and unit_a_root.is_absolute(), "input_roots_not_absolute")
    _exact(input_body, input_inventory(source_root, unit_a_root), "inputs_changed")
    identities = {
        "protocolDigest": digest_json(protocol),
        "sourceDigest": sources["digest"],
        "inputDigest": input_digest,
    }
    _exact(checkpoint.get("identities"), identities, "checkpoint_identity_mismatch")
    _require("active" in checkpoint and checkpoint["active"] is None, "checkpoint_not_terminal")
    for key, expected in identities.items():
        _exact(result.get(key), expected, "result_identity_mismatch")
    attempts, extras, probes = (
        result["packageAttempts"],
        result["extras"],
        result["unitACompatibility"],
    )
    for ck, saved in (("attempts", attempts), ("extras", extras), ("unitA", probes)):
        _exact(checkpoint.get(ck), saved, "checkpoint_rows_mismatch")
    expected_attempts = [
        (repeat, sid, family) for repeat in (1, 2) for sid, family in BASELINE_SOURCES
    ]
    _exact(
        [(r.get("repeat"), r.get("sourceId"), r.get("family")) for r in attempts],
        expected_attempts,
        "baseline_attempt_inventory",
    )
    packages = []
    for attempt in attempts:
        sid, family, repeat = attempt["sourceId"], attempt["family"], attempt["repeat"]
        receipt = _validate_attempt(attempt, evaluation / f"build{repeat}" / sid, sid, family)
        if "package" in attempt:
            _exact(attempt.get("status"), receipt["status"], "attempt_status_mismatch")
            original = _document(source_root / sid, "manifest.json")
            _exact(
                receipt["manifest"]["sourceIdentity"],
                {
                    "legacyPackageDigest": original["packageDigest"],
                    "legacyManifestSha256": sha256_file(source_root / sid / "manifest.json"),
                },
                "baseline_source_identity_mismatch",
            )
            for key, path in (
                ("inputCleanSha256", "render/clean.glb"),
                ("inputSemanticsSha256", "reports/semantics.json"),
            ):
                _exact(
                    receipt["manifest"][key],
                    sha256_file(_file(source_root / sid, path)),
                    "baseline_input_mismatch",
                )
        packages.append({**receipt, "repeat": repeat, "scope": "baseline"})
    first = sorted((r for r in attempts if r["repeat"] == 1), key=lambda r: r["sourceId"])
    second = sorted((r for r in attempts if r["repeat"] == 2), key=lambda r: r["sourceId"])
    rows = [row for attempt in first for row in attempt["rows"]]
    _exact(result["baselineRows"], rows, "baseline_rows_mismatch")
    _exact(docs["baseline_rows.json"], rows, "baseline_rows_file_mismatch")
    deterministic = all(
        a.get("package", {}).get("packageDigest") is not None
        and a["package"]["packageDigest"] == b.get("package", {}).get("packageDigest")
        for a, b in zip(first, second, strict=True)
    )
    metrics = _baseline_metrics(first, deterministic)
    _exact(result["metrics"], metrics, "aggregate_metrics_mismatch")
    gates = derive_gates(protocol, metrics)
    _exact(result["gates"], gates, "gate_status_mismatch")
    _exact(
        [r.get("caseId") for r in extras],
        [r["caseId"] for r in protocol["extraCases"]],
        "extra_case_inventory",
    )
    for extra, definition in zip(extras, protocol["extraCases"], strict=True):
        for key, expected in definition.items():
            # Evaluation replaces numeric grid rows with the saved motion rows.
            if key == "rows":
                continue
            _exact(extra.get(key), expected, "extra_definition_mismatch")
        sid = extra["caseId"]
        if "package" in extra:
            receipt = _validate_attempt(
                extra, evaluation / "extra_packages" / sid, sid, "development_two_panel_shell"
            )
            _exact(
                receipt["manifest"]["sourceIdentity"],
                {"fixtureDefinitionDigest": digest_json(definition)},
                "extra_source_identity_mismatch",
            )
            for key, path in (
                ("inputCleanSha256", "clean.glb"),
                ("inputSemanticsSha256", "semantics.json"),
            ):
                _exact(
                    receipt["manifest"][key],
                    sha256_file(_file(evaluation / "extra_inputs" / sid, path)),
                    "extra_input_mismatch",
                )
            status = (
                "pass" if extra["expected"] == "pass" and receipt["status"] == "pass" else "fail"
            )
            _exact(extra.get("outcome"), "built", "extra_outcome_mismatch")
            packages.append({**receipt, "scope": "extra"})
        elif extra["expected"] == "pass":
            receipt = _validate_attempt(
                extra, evaluation / "extra_packages" / sid, sid, "development_two_panel_shell"
            )
            status = "fail"
            packages.append({**receipt, "scope": "extra"})
        else:
            _exact(extra["rows"], [], "negative_rows_mismatch")
            reason = extra.get("reason", extra.get("error", ""))
            _require(isinstance(reason, str) and bool(reason), "negative_reason_missing")
            status = (
                "pass"
                if (
                    extra.get("outcome") == "rejected"
                    and reason.startswith("ValueError:")
                    and extra["expectedReason"] in reason
                )
                else "fail"
            )
            packages.append(
                {
                    "id": sid,
                    "scope": "negative",
                    "status": status,
                    "reason": reason,
                    "retainedPartialFiles": _inventory(evaluation / "extra_packages" / sid),
                }
            )
        _exact(extra.get("status"), status, "extra_status_mismatch")
    _exact([row.get("family") for row in probes], list(UNIT_A_FAMILIES), "unit_a_inventory")
    for probe in probes:
        _require(probe.get("status") in ("pass", "fail", "unsupported", "not_run"), "unit_a_status")
        _require(probe.get("fullC3Claim", False) is False, "unit_a_claim")
        if "unitAPackageIdentity" in probe:
            source = unit_a_root / probe["family"] / "nominal"
            original = _document(source, "manifest.json")
            _exact(
                probe["unitAPackageIdentity"],
                _identity(original, "packageIdentity"),
                "unit_a_package_identity_mismatch",
            )
            clean_path = _file(source, "render/fallback.glb")
            _exact(probe.get("inputCleanSha256"), sha256_file(clean_path), "unit_a_input_mismatch")
            _exact(
                probe.get("renderVertexCount"),
                read_glb_meshset(clean_path).vertex_count,
                "unit_a_vertex_count_mismatch",
            )
        if "rest" in probe:
            family = probe["family"]
            root = evaluation / "unit_a" / family
            rest = check_rest(
                _file(root, "cage.glb"),
                _file(unit_a_root / family / "nominal", "render/fallback.glb"),
                _file(root, "local_frame_v2.bin"),
            )
            _exact(probe["rest"], rest, "unit_a_rest_mismatch")
            _exact(probe["status"], rest["status"], "unit_a_rest_status")
        else:
            _require(
                probe.get("status") != "pass" and bool(probe.get("reason")), "unit_a_reason_missing"
            )
    _exact(result["otherFamilies"], protocol["otherUnitAFamilies"], "unsupported_scope_mismatch")
    extra_rows = [row for extra in extras if extra["expected"] == "pass" for row in extra["rows"]]
    _exact(result["extraPositiveRows"], extra_rows, "extra_positive_rows_mismatch")
    baseline_ok = all(g["status"] == "pass" for g in gates) and all(
        p["status"] == "pass" for p in first
    )
    _require(type(result.get("sourceAndInputsUnchanged")) is bool, "freshness_status_type")
    for key, expected in (
        ("baselineRowDenominator", 99),
        ("baselinePassedRows", sum(r["status"] == "pass" for r in rows)),
        ("baselineFailedRows", sum(r["status"] != "pass" for r in rows)),
        ("extraCaseDenominator", 7),
        ("extraPositiveRowDenominator", 44),
        ("extraPassedCases", sum(r["status"] == "pass" for r in extras)),
        ("extraFailedCases", sum(r["status"] != "pass" for r in extras)),
        ("baselineStatus", "pass" if baseline_ok else "fail"),
        (
            "status",
            "pass"
            if baseline_ok
            and all(r["status"] == "pass" for r in extras)
            and all(r["status"] in ("pass", "unsupported") for r in probes)
            and result["sourceAndInputsUnchanged"]
            else "fail",
        ),
        ("limitsUnchanged", True),
        ("scientificQualification", False),
        ("globalC3Complete", False),
        ("physicalMobileLatency", "not_run"),
        ("physicalMobileMemory", "not_run"),
    ):
        _exact(result.get(key), expected, f"{key}_mismatch")
    _require(len(rows) == 99 and len(extra_rows) == 44, "row_denominator_mismatch")
    _exact(
        raw["report.md"].decode().replace("\r\n", "\n"),
        canonical_text_bytes(_report(result)).decode(),
        "report_stale",
    )
    _exact(source_inventory(forge_root), sources["files"], "source_changed_during_validation")
    _exact(
        input_inventory(source_root, unit_a_root), input_body, "inputs_changed_during_validation"
    )
    for name, data in raw.items():
        _require(
            _file(evaluation, name).read_bytes() == data, "evaluation_changed_during_validation"
        )
    output = {name: data for name, data in raw.items() if name != "checkpoint.json"}
    output["package_index.json"] = canonical_dumps(packages).encode()
    publication: dict[str, Any] = {
        "version": VERSION,
        "sourceEvaluation": str(evaluation.resolve()),
        "evaluationResultDigest": result["resultDigest"],
        "baselineStatus": result["baselineStatus"],
        "evaluationStatus": result["status"],
        "scientificQualification": False,
        "sourceHeadAtEvaluationStart": sources["head"],
        "headEqualityRequired": False,
        "checkpointSha256": sha256_bytes(raw["checkpoint.json"]),
        "validationScope": "saved_hashes_rest_geometry_semantics_motion_metrics_no_regeneration",
        "motionGenerationReexecuted": False,
        "files": [
            {"path": name, "sha256": sha256_bytes(data), "byteSize": len(data)}
            for name, data in sorted(output.items())
        ],
    }
    publication["identity"] = digest_json(publication)
    output["publication_manifest.json"] = canonical_dumps(publication).encode()
    return output


def publish(evaluation: Path, destination: Path, *, forge_root: Path = FORGE) -> dict[str, Any]:
    evaluation, destination = evaluation.absolute(), destination.absolute()
    _require(
        not destination.exists()
        and not any(_linked(p) for p in (destination, *destination.parents)),
        "requires_fresh_destination",
    )
    _require(
        not destination.resolve().is_relative_to(evaluation.resolve())
        and not evaluation.resolve().is_relative_to(destination.resolve()),
        "destination_overlaps_source",
    )
    documents = prepare_publication(evaluation, forge_root=forge_root)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in documents.items():  # Completion manifest was inserted last.
        with (destination / name).open("xb") as stream:
            stream.write(data)
        _require((destination / name).read_bytes() == data, "write_verification_failed")
    result: dict[str, Any] = _json(documents["publication_manifest.json"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", required=True, type=Path)
    parser.add_argument(
        "--destination",
        type=Path,
        default=FORGE / "docs/evidence/manual_provider_binding_v2_development",
    )
    args = parser.parse_args()
    print(publish(args.evaluation, args.destination)["identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
