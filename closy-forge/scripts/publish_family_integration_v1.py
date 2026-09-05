"""Publish completed Unit A artifacts without building geometry or running evaluators.

No existing files are changed. All validation precedes creation of a fresh output
directory; publication_manifest.json is written last and is the completion marker.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from closy_forge.blueprint_progress_v3 import build_requirement_inventory
from closy_forge.blueprint_progress_v3.checkpoint import (
    BASELINE_HEAD,
    BLUEPRINT_PATH,
    phase_overview,
)
from closy_forge.blueprint_progress_v3.crosswalk import build_migration_crosswalk

PR66 = BASELINE_HEAD
LOCK_PATH = "closy-forge/fixtures/strategy3_blob_authority_v3/repository_blob_lock.json"
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
LABELS = ("nominal", "variation1", "variation2")
PROFILE = "closy.all_family_integration.development.v1"
MAX_JSON_BYTES = 8 * 1024 * 1024


class PublicationError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PublicationError(code)


def safe_path(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and bool(relative), "empty_relative_path")
    parts = PurePosixPath(relative)
    require(
        not parts.is_absolute()
        and "\\" not in relative
        and ":" not in relative
        and all(part not in {"", ".", ".."} for part in relative.split("/")),
        "unsafe_relative_path",
    )
    root = root.absolute()
    require(not _linked(root), "linked_input_root")
    target = root
    for part in parts.parts:
        target = target / part
        require(not _linked(target), "linked_input_path")
    require(target.resolve().is_relative_to(root.resolve()), "path_outside_root")
    return target


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def read_bytes(root: Path, relative: str) -> bytes:
    path = safe_path(root, relative)
    require(path.is_file(), f"missing_input:{relative}")
    require(path.stat().st_size <= MAX_JSON_BYTES, f"input_too_large:{relative}")
    return path.read_bytes()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def decode(data: bytes) -> Any:
    def invalid_constant(value: str) -> None:
        raise PublicationError(f"nonfinite_json:{value}")

    def finite_float(value: str) -> float:
        number = float(value)
        require(math.isfinite(number), "nonfinite_json_number")
        return number

    return json.loads(
        data, object_pairs_hook=_object, parse_constant=invalid_constant, parse_float=finite_float
    )


def read_json(root: Path, relative: str) -> Any:
    return decode(read_bytes(root, relative))


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        capture_output=True,
        timeout=60,
        check=False,
    )
    require(completed.returncode == 0, f"git_read_failed:{args[0]}")
    return completed.stdout


def _git_blobs(repo: Path, specs: Sequence[str]) -> list[bytes]:
    payload = _git(repo, "cat-file", "--batch", input_bytes=("\n".join(specs) + "\n").encode())
    cursor = 0
    values = []
    for _ in specs:
        end = payload.find(b"\n", cursor)
        require(end >= 0, "git_blob_header_missing")
        header = payload[cursor:end].split()
        require(len(header) == 3 and header[1] == b"blob", "git_blob_missing_or_wrong_type")
        size = int(header[2])
        start = end + 1
        value = payload[start : start + size]
        require(
            len(value) == size and payload[start + size : start + size + 1] == b"\n",
            "git_blob_truncated",
        )
        require(blob_oid(value).encode() == header[0], "git_blob_oid_mismatch")
        values.append(value)
        cursor = start + size + 1
    require(cursor == len(payload), "git_blob_trailing_bytes")
    return values


def audit_repository(repo_root: Path) -> dict[str, Any]:
    """Compare raw Git blobs; separately classify Windows checkout line endings."""
    repo = repo_root.resolve(strict=True)
    base_lock = _git_blobs(repo, [f"{PR66}:{LOCK_PATH}"])[0]
    require(read_bytes(repo, LOCK_PATH) == base_lock, "protected_lock_changed")
    lock = decode(base_lock)
    rows = lock["blobs"]
    require(lock["blobCount"] == len(rows) == 84, "protected_lock_not_84")
    paths = [row["repositoryPath"] for row in rows]
    require(len(set(paths)) == 84, "protected_lock_duplicate_paths")
    for path in paths:
        safe_path(repo, path)
    base_blobs = _git_blobs(repo, [f"{PR66}:{path}" for path in paths])
    current_blobs = _git_blobs(repo, [f"HEAD:{path}" for path in paths])
    frozen_blobs = _git_blobs(repo, [row["rawBlobOid"] for row in rows])
    checks = []
    for row, base, head, frozen in zip(rows, base_blobs, current_blobs, frozen_blobs, strict=True):
        working = read_bytes(repo, row["repositoryPath"])
        checks.append(
            {
                "path": row["repositoryPath"],
                "baseBlobOid": blob_oid(base),
                "baseSha256": digest(base),
                "headSha256": digest(head),
                "historicalLockedObjectVerified": digest(frozen) == row["rawBlobSha256"]
                and len(frozen) == row["rawBlobByteLength"],
                "workingSha256": digest(working),
                "baseMatchesHistoricalLock": (
                    blob_oid(base) == row["rawBlobOid"] and digest(base) == row["rawBlobSha256"]
                ),
                "headByteExact": head == base,
                "workingByteExact": working == base,
                "checkoutLfToCrlfOnly": working != base
                and b"\r\n" not in base
                and base.replace(b"\n", b"\r\n") == working,
            }
        )
    changed = (
        _git(
            repo,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            "--diff-filter=CDMRTUXB",
            PR66,
            "--",
        )
        .decode()
        .strip("\0")
        .split("\0")
    )
    changed = [path for path in changed if path]
    require(not changed, f"existing_tracked_tree_changed:{','.join(changed)}")
    require(not _git(repo, "ls-files", "-u"), "unmerged_index")
    require(
        all(
            row["historicalLockedObjectVerified"]
            and row["headByteExact"]
            and (row["workingByteExact"] or row["checkoutLfToCrlfOnly"])
            for row in checks
        ),
        "protected_blob_bytes_changed",
    )
    return {
        "version": "closy.family_publication.protected_sources.v1",
        "base": PR66,
        "head": _git(repo, "rev-parse", "HEAD").decode().strip(),
        "tree": _git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
        "lockPath": LOCK_PATH,
        "lockSha256": digest(base_lock),
        "protectedBlobCount": 84,
        "byteExactCount": 84,
        "blobs": checks,
        "byteExactScope": "raw HEAD Git blobs versus raw PR66 Git blobs; no normalization",
        "baselineAlreadyDiffersFromHistoricalLock": [
            row["path"] for row in checks if not row["baseMatchesHistoricalLock"]
        ],
        "workingByteExactCount": sum(row["workingByteExact"] for row in checks),
        "checkoutLfToCrlfOnlyCount": sum(row["checkoutLfToCrlfOnly"] for row in checks),
        "existingTrackedTreeUnchanged": True,
        "existingChangedPaths": changed,
        "newFilesPermitted": True,
        "normalizationApplied": False,
        "sealedExperimentsExecuted": False,
    }


def validate_completed(
    protocol: Mapping[str, Any],
    result: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    index: Sequence[Mapping[str, Any]],
    source: Mapping[str, Any],
    protocol_bytes: bytes,
) -> dict[str, Any]:
    """Validate saved denominators/identities, not numerical geometry or physical qualification."""
    require(protocol.get("version") == "family_integration_development_v1", "unknown_protocol")
    require(result.get("version") == "closy.family_integration.result.v1", "unknown_result")
    require(
        protocol.get("buildCount") == result.get("buildDenominator") == 54
        and protocol.get("cleanRoots") == 2,
        "build_denominator_mismatch",
    )
    require(
        protocol.get("scientificCampaign") is False
        and result.get("physicalQualification") is False
        and result.get("globalPhase8Complete") is False,
        "unsupported_acceptance_claim",
    )
    require(result.get("protocolDigest") == digest(protocol_bytes), "protocol_digest_mismatch")
    require(result.get("sourceHead") == source.get("head"), "source_head_mismatch")
    require(
        result.get("sourceInventoryDigest") == digest(canonical(source["files"])),
        "source_inventory_digest_mismatch",
    )
    cases = protocol["cases"]
    expected_ids = {f"{family}/{label}" for family in FAMILIES for label in LABELS}
    require(
        len(cases) == 27 and {case["caseId"] for case in cases} == expected_ids,
        "case_inventory_mismatch",
    )
    by_case = {case["caseId"]: case for case in cases}
    require(
        all(case["family"] == case["caseId"].split("/")[0] for case in cases),
        "case_family_mismatch",
    )
    rows = result["rows"]
    require(len(rows) == 54, "evaluation_incomplete")
    require(
        checkpoint.get("rows") == rows
        and checkpoint.get("nextBuild") == 55
        and not checkpoint.get("active"),
        "checkpoint_not_terminal",
    )
    keys: set[tuple[int, str]] = set()
    for row in rows:
        require(type(row["repeat"]) is int and row["repeat"] in (1, 2), "invalid_repeat")
        key = (row["repeat"], row["caseId"])
        require(key not in keys and row["caseId"] in by_case, "duplicate_or_unknown_case")
        keys.add(key)
        case = by_case[row["caseId"]]
        require(
            row["family"] == case["family"] and row["changes"] == case["changes"],
            "row_protocol_mismatch",
        )
        require(row["terminal"] in {"passed", "failed"}, "nonterminal_row")
        if row["terminal"] == "passed":
            audit = row["audit"]
            require(
                re.fullmatch(r"[0-9a-f]{64}", row["packageIdentity"]) is not None,
                "package_identity_invalid",
            )
            require(
                audit["packageIdentity"] == row["packageIdentity"]
                and audit["family"] == row["family"]
                and audit["profile"] == PROFILE,
                "audit_identity_mismatch",
            )
            require(
                audit["validConventionalGeometry"] is True
                and audit["semanticsValid"] is True
                and audit["canonicalTopologyPreserved"] is True,
                "passed_row_invalid_audit",
            )
            require(audit["physicalQualityPassed"] is False, "physical_scope_promoted")
            require(
                set(audit["geometry"]) == {"rest", "simulation", "render"},
                "geometry_stages_incomplete",
            )
            require(
                all(
                    stage["valid"] is True
                    and stage["invalidTriangleCount"] == 0
                    and stage["triangleCount"] > 0
                    and stage["vertexCount"] > 0
                    and stage["minimumAreaM2"] > protocol["areaThresholdM2"]
                    and math.isfinite(stage["minimumAreaM2"])
                    for stage in audit["geometry"].values()
                ),
                "passed_geometry_inconsistent",
            )
            require(
                audit["bindingCoverage"] == audit["renderVertexCount"] > 0
                and 0 <= audit["maximumBindingErrorM"] <= protocol["bindingFloat32ToleranceM"],
                "passed_binding_inconsistent",
            )
            boundaries = audit["boundaries"]
            gap = boundaries["maximumPairedSeamGapM"]
            require(
                math.isfinite(gap)
                and gap >= 0
                and boundaries["physicalSeamAcceptance"] is (gap <= 0.008)
                and boundaries["allOpeningsNoncollapsed"] is True,
                "seam_or_opening_claim_inconsistent",
            )
        else:
            require(
                isinstance(row.get("error"), str) and bool(row["error"]), "failed_row_no_reason"
            )
    require(
        keys == {(repeat, case) for repeat in (1, 2) for case in expected_ids},
        "terminal_matrix_incomplete",
    )
    counts = Counter(row["terminal"] for row in rows)
    require(result["passedBuilds"] == counts["passed"], "passed_count_mismatch")
    by_key = {(row["repeat"], row["caseId"]): row for row in rows}
    deterministic = all(
        by_key[1, case]["terminal"] == by_key[2, case]["terminal"] == "passed"
        and by_key[1, case]["packageIdentity"] == by_key[2, case]["packageIdentity"]
        for case in expected_ids
    )
    require(result["deterministicTwoRoots"] is deterministic, "determinism_claim_mismatch")
    require(
        len(index) == 27 and {row["caseId"] for row in index} == expected_ids,
        "family_index_incomplete",
    )
    for row in index:
        expected = by_key[1, row["caseId"]]
        require(
            all(
                row.get(key) == expected.get(key)
                for key in (
                    "family",
                    "terminal",
                    "packageIdentity",
                    "audit",
                )
            ),
            "family_index_result_mismatch",
        )
    captures = result["captures"]
    require(
        len(captures) == 9 and {row["family"] for row in captures} == set(FAMILIES),
        "capture_denominator_mismatch",
    )
    require(all(type(row.get("passed")) is bool for row in captures), "nonterminal_capture")
    negatives = result["negatives"]
    require(
        len(negatives) == 18
        and {(row["family"], row["input"]) for row in negatives}
        == {(family, value) for family in FAMILIES for value in ("nan", "-100")},
        "negative_denominator_mismatch",
    )
    require(all(type(row.get("rejected")) is bool for row in negatives), "nonterminal_negative")
    return {
        "builds": {
            "planned": 54,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "notRun": 0,
        },
        "captures": {
            "planned": 9,
            "passed": sum(row["passed"] for row in captures),
            "failed": sum(not row["passed"] for row in captures),
        },
        "negativeControls": {
            "planned": 18,
            "rejected": sum(row["rejected"] for row in negatives),
            "notRejected": sum(not row["rejected"] for row in negatives),
        },
        "deterministicTwoRoots": deterministic,
    }


def compact_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    boundaries = audit["boundaries"]
    return {
        "validConventionalGeometry": audit["validConventionalGeometry"],
        "semanticsValid": audit["semanticsValid"],
        "canonicalTopologyPreserved": audit["canonicalTopologyPreserved"],
        "geometry": {
            stage: {
                key: record[key]
                for key in (
                    "valid",
                    "triangleCount",
                    "vertexCount",
                    "minimumAreaM2",
                    "invalidTriangleCount",
                    "firstFailure",
                )
            }
            for stage, record in audit["geometry"].items()
        },
        "bindingCoverage": audit["bindingCoverage"],
        "renderVertexCount": audit["renderVertexCount"],
        "maximumBindingErrorM": audit["maximumBindingErrorM"],
        "maximumPairedSeamGapM": boundaries["maximumPairedSeamGapM"],
        "physicalSeamAcceptance": boundaries["physicalSeamAcceptance"],
        "allOpeningsNoncollapsed": boundaries["allOpeningsNoncollapsed"],
        "openingMetricScope": boundaries["openingMetricScope"],
        "physicalQualityPassed": audit["physicalQualityPassed"],
        "motionSupport": audit["motionSupport"],
        "layerSupport": audit["layerSupport"],
    }


def current_blueprint(
    forge: Path, counts: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = (forge / BLUEPRINT_PATH).read_text(encoding="utf-8")
    inventory = build_requirement_inventory(text, source_blob_oid=blob_oid(text.encode()))
    crosswalk = build_migration_crosswalk(
        inventory,
        historical_239=read_json(
            forge, "docs/evidence/static_zeroone_runtime_v2/blueprint_inventory.json"
        ),
        historical_101=read_json(forge, "docs/blueprint_coverage.json"),
    )
    # One copy of each requirement's text; crosswalk additions reference inventory IDs.
    crosswalk["newlyIncludedRequirementIds"] = [
        row["id"] for row in crosswalk.pop("newlyIncludedRequirements")
    ]
    inventory.pop("blocks")
    overview = phase_overview()
    overview["overviewVersion"] = "closy.blueprint_phase_overview.family_integration.v1"
    overview["newUnitOutcomes"] = {
        "A": {"counts": dict(counts), "qualityScope": "conventional_validity_not_full_acceptance"},
        "B": "pending_parent_update",
        "C": "pending_parent_update",
    }
    overview["developmentQuality"] = (
        "Unit A saved matrix incorporated; seam/physics and image estimation remain unmet. "
        "PR63-66 historical failures preserved; B/C publication pending."
    )
    for row in overview["phases"]:
        phase = row["roadmapPhase"]
        if phase in (1, 8):
            row["currentUnitAEvidence"] = (
                f"{counts['builds']['passed']}/54 conventional builds passed; "
                f"{counts['builds']['failed']} failed; two-root determinism "
                f"{counts['deterministicTwoRoots']}. Not seam/physics acceptance."
            )
        elif phase in (2, 3, 4):
            row["currentUnitAEvidence"] = (
                f"{counts['captures']['passed']}/9 known-parameter capture round trips pass. "
                "No new image parameter estimator; historical capture gates unchanged."
            )
        elif phase == 6:
            row["currentUnitAEvidence"] = "Canonical binding fidelity only; manual-shell B pending."
        elif phase in (10, 11, 12, 13):
            row["currentUnitAEvidence"] = "No new Unit C acceptance; package-layer/runtime pending."
    return {"inventory": inventory, "phaseOverview": overview}, crosswalk


class Inputs:
    """Track exact saved inputs; reject changes between validation and publication."""

    def __init__(self, forge: Path) -> None:
        self.forge = forge.resolve(strict=True)
        self.records: dict[str, dict[str, Any]] = {}

    def record(self, path: Path) -> bytes:
        require(path.absolute().is_relative_to(self.forge), "input_outside_forge")
        relative = path.relative_to(self.forge).as_posix()
        data = read_bytes(self.forge, relative)
        if relative in self.records:
            require(
                digest(data) == self.records[relative]["sha256"],
                f"input_changed_during_publication:{relative}",
            )
        self.records[relative] = {"path": relative, "sha256": digest(data), "byteSize": len(data)}
        return data

    def json(self, path: Path) -> Any:
        return decode(self.record(path))

    def unchanged(self) -> None:
        for relative, row in self.records.items():
            require(
                digest(read_bytes(self.forge, relative)) == row["sha256"],
                f"input_changed_during_publication:{relative}",
            )


def source_closure(forge: Path, entry_paths: Sequence[str]) -> dict[str, str]:
    """Conservative AST closure, including relative imports and package initializers.

    Never import/execute a family module. All explicit dynamic family targets are
    seeded by the caller; unexpected dynamic loaders fail closed for manual review.
    """
    queued = list(entry_paths)
    result: dict[str, str] = {}

    def module_files(name: str) -> list[str]:
        if name != "closy_forge" and not name.startswith("closy_forge."):
            return []
        parts = name.split(".")
        require(all(part.isidentifier() for part in parts), "invalid_import_module")
        files = []
        for index in range(1, len(parts) + 1):
            package = "src/" + "/".join(parts[:index]) + "/__init__.py"
            if safe_path(forge, package).is_file():
                files.append(package)
        module = "src/" + "/".join(parts) + ".py"
        if safe_path(forge, module).is_file():
            files.append(module)
        return files

    while queued:
        path = queued.pop()
        if path in result:
            continue
        data = read_bytes(forge, path)
        result[path] = digest(data)
        tree = ast.parse(data, filename=path)
        parts = PurePosixPath(path).with_suffix("").parts
        module_parts = list(parts[1:]) if path.startswith("src/") else []
        package_parts = module_parts[:-1]
        if module_parts:
            queued.extend(module_files(".".join(package_parts)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    queued.extend(module_files(alias.name))
            elif isinstance(node, ast.ImportFrom):
                parent = package_parts[: len(package_parts) - node.level + 1] if node.level else []
                name = ".".join(parent + ([node.module] if node.module else []))
                queued.extend(module_files(name))
                for alias in node.names:
                    if alias.name != "*":
                        queued.extend(module_files(name + "." + alias.name))
            elif isinstance(node, ast.Call):
                loader = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                    or isinstance(node.func, ast.Name)
                    and node.func.id == "__import__"
                )
                if not loader:
                    continue
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(
                        node.args[0].value,
                        str,
                    )
                ):
                    queued.extend(module_files(node.args[0].value))
                else:
                    require(
                        path == "src/closy_forge/family_integration_v1/registry.py",
                        f"unresolved_dynamic_import:{path}",
                    )
    return dict(sorted(result.items()))


def _source_review(forge: Path, source: Mapping[str, Any]) -> dict[str, Any]:
    dynamic = [
        f"src/closy_forge/garments/{family}/{module}.py"
        for family in FAMILIES
        for module in ("parameters", "pattern_generator", "semantic_graph", "assembly")
    ]
    entries = ["scripts/evaluate_family_integration_v1.py", *dynamic]
    closure = source_closure(forge, entries)
    start = source["files"]
    reachable = []
    for path, actual in closure.items():
        if not path.startswith("src/"):
            continue
        require(path in start, f"reachable_source_missing_from_start_inventory:{path}")
        require(actual == start[path], f"evaluation_reachable_source_changed:{path}")
        reachable.append({"path": path, "sha256": actual})
    outside_changes = []
    for path, expected in start.items():
        require(path.startswith("src/") and path.endswith(".py"), "source_inventory_path_invalid")
        target = safe_path(forge, path)
        outside_actual = digest(read_bytes(forge, path)) if target.is_file() else None
        if path not in closure and outside_actual != expected:
            outside_changes.append(
                {
                    "path": path,
                    "evaluationSha256": expected,
                    "publicationSha256": outside_actual,
                    "scope": "outside_unit_a_closure",
                }
            )
    additions = [
        path.relative_to(forge).as_posix()
        for path in sorted((forge / "src").rglob("*.py"))
        if path.relative_to(forge).as_posix() not in start
    ]
    return {
        "method": "AST absolute/relative imports, package initializers, explicit family dispatch",
        "recordedFileCount": len(start),
        "reachableSourceCount": len(reachable),
        "reachableSources": reachable,
        "reachableSourceDigest": digest(canonical(reachable)),
        "reachableRecordedSourcesUnchanged": True,
        "explicitDynamicFamilyModules": dynamic,
        "outsideClosureChanges": outside_changes,
        "addedOutsideStartInventory": additions,
        "outsideClosurePolicy": (
            "outside A imports; broad snapshot preserved, not forged into a freeze"
        ),
        "evaluatorScriptStartHash": "not recorded by evaluator; current receipt only",
        "externalImports": (
            "environment dependencies; not asserted covered by repository AST digest"
        ),
    }


def _verify_package(inputs: Inputs, package: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    manifest = inputs.json(package / "manifest.json")
    identity = {key: value for key, value in manifest.items() if key != "packageIdentity"}
    require(
        digest(canonical(identity)) == row["packageIdentity"] == manifest["packageIdentity"],
        "package_manifest_identity_mismatch",
    )
    require(
        manifest["family"] == row["family"] and manifest["profile"] == PROFILE,
        "package_family_profile_mismatch",
    )
    require(inputs.json(package / "audit.json") == row["audit"], "saved_audit_result_mismatch")
    seen = set()
    for item in manifest["inventory"]:
        relative = item["path"]
        require(relative not in seen, "duplicate_package_inventory_path")
        seen.add(relative)
        path = safe_path(package, relative)
        data = inputs.record(path)
        require(
            len(data) == item["byteSize"] and digest(data) == item["sha256"],
            f"package_payload_changed:{relative}",
        )
    require(
        {
            "render/fallback.glb",
            "simulation/rest.glb",
            "simulation/simulation_mesh.glb",
            "simulation/settling.json",
            "binding/sim_to_render.bin",
        }
        <= seen,
        "package_inventory_incomplete",
    )
    return dict(inputs.json(package / "simulation/settling.json"))


def prepare_publication(
    evaluation_root: Path,
    *,
    forge_root: Path,
    initial_root: Path,
    prototype_roots: Sequence[Path],
) -> dict[str, bytes]:
    """Read and validate everything; return compact output bytes without writing them."""
    forge = forge_root.resolve(strict=True)
    root = evaluation_root.absolute()
    require(root != initial_root.absolute(), "initial_and_final_roots_must_differ")
    require(len(prototype_roots) == 2, "two_prototype_roots_required")
    require(len({path.absolute() for path in prototype_roots}) == 2, "duplicate_prototype_root")
    inputs = Inputs(forge)
    protocol_bytes = inputs.record(root / "protocol.json")
    protocol = decode(protocol_bytes)
    result = inputs.json(root / "result.json")
    index = inputs.json(root / "family_index.json")
    checkpoint = inputs.json(root / "checkpoint.json")
    source_bytes = inputs.record(root / "source_inventory.json")
    source = decode(source_bytes)
    counts = validate_completed(protocol, result, checkpoint, index, source, protocol_bytes)
    protection = audit_repository(forge.parent)
    review = _source_review(forge, source)
    compact_rows = []
    for row in result["rows"]:
        compact = {key: value for key, value in row.items() if key != "audit"}
        compact["packagePath"] = f"build{row['repeat']}/{row['caseId']}"
        if row["terminal"] == "passed":
            settling = _verify_package(inputs, root / compact["packagePath"], row)
            compact["audit"] = compact_audit(row["audit"])
            compact["settling"] = settling
        compact_rows.append(compact)
    for capture in result["captures"]:
        if "packageIdentity" not in capture:
            require(
                capture["passed"] is False and bool(capture.get("error")),
                "capture_failure_without_reason",
            )
            continue
        nominal = next(
            row
            for row in result["rows"]
            if row["repeat"] == 1 and row["caseId"] == f"{capture['family']}/nominal"
        )
        if nominal["terminal"] == "passed":
            require(
                capture["packageIdentity"] == nominal["packageIdentity"], "capture_package_mismatch"
            )
        else:
            manifest = inputs.json(root / "build1" / nominal["caseId"] / "manifest.json")
            require(
                capture["packageIdentity"]
                == manifest["packageIdentity"]
                == digest(
                    canonical(
                        {key: value for key, value in manifest.items() if key != "packageIdentity"}
                    )
                ),
                "failed_package_capture_identity_mismatch",
            )
        folder = root / "captures" / capture["family"]
        require(inputs.json(folder / "roundtrip.json") == capture, "capture_summary_mismatch")
        require(
            capture["knownParametersSupplied"] is True
            and capture["pixelParameterEstimator"] == "unsupported_in_this_profile"
            and capture["physicalCaptureEvidence"] is False,
            "capture_scope_promoted",
        )
        require(
            {view["view"] for view in capture["views"]} == {"front", "back"}
            and len(capture["views"]) == 2,
            "capture_views_incomplete",
        )
        require(
            capture["passed"]
            is (
                all(view["passed"] for view in capture["views"])
                and capture["correction"]["changed"]
            ),
            "capture_pass_claim_inconsistent",
        )
        for view in capture["views"]:
            label = view["view"]
            require(
                0 <= view["causallyChangedSamples"] <= view["projectedSamples"]
                and view["passed"] is (view["causallyChangedSamples"] > 0),
                "capture_view_claim_inconsistent",
            )
            require(
                digest(inputs.record(folder / f"{label}.png")) == view["sourceSha256"],
                "capture_source_changed",
            )
            require(
                digest(inputs.record(folder / f"{label}_panel_projection.json"))
                == view["projectionDigest"],
                "capture_projection_changed",
            )
            inputs.record(folder / f"{label}_pixel_correction.png")
    initial_checkpoint = inputs.json(initial_root.absolute() / "checkpoint.json")
    initial_protocol = inputs.json(initial_root.absolute() / "protocol.json")
    initial_source = inputs.json(initial_root.absolute() / "source_inventory.json")
    require(
        any(row["terminal"] == "failed" for row in initial_checkpoint["rows"]),
        "initial_failed_rows_missing",
    )
    retained: dict[str, Any] = {
        "initial": {
            "root": initial_root.absolute().relative_to(forge).as_posix(),
            "checkpoint": initial_checkpoint,
            "protocol": initial_protocol,
            "status": "interrupted_development_not_a_completed_matrix",
            "planned": initial_protocol["buildCount"],
            "recorded": len(initial_checkpoint["rows"]),
            "notRun": initial_protocol["buildCount"] - len(initial_checkpoint["rows"]),
            "terminalCounts": dict(Counter(row["terminal"] for row in initial_checkpoint["rows"])),
            "sourceInventoryChangesVersusFinal": {
                path: {"initialSha256": value, "finalSha256": source["files"].get(path)}
                for path in sorted(set(initial_source["files"]) | set(source["files"]))
                if (value := initial_source["files"].get(path)) != source["files"].get(path)
            },
        },
        "longSleevePrototypes": [],
        "includedInFinal54Denominator": False,
    }
    for folder in prototype_roots:
        folder = folder.absolute()
        audit = inputs.json(folder / "audit.json")
        require(audit["family"] == "long_sleeved_top", "prototype_family_mismatch")
        retained["longSleevePrototypes"].append(
            {
                "root": folder.relative_to(forge).as_posix(),
                "audit": audit,
                "settling": inputs.json(folder / "simulation/settling.json"),
                "scope": "exposed_prototype_geometry_not_physical_acceptance",
            }
        )
    current_receipt = {}
    for relative in (
        BLUEPRINT_PATH,
        "docs/blueprint_coverage.json",
        "docs/evidence/static_zeroone_runtime_v2/blueprint_inventory.json",
        "scripts/publish_family_integration_v1.py",
        "scripts/evaluate_family_integration_v1.py",
        "tests/unit/test_family_integration_v1.py",
        "tests/unit/test_family_publication_v1.py",
    ):
        current_receipt[relative] = digest(inputs.record(forge / relative))
    for path in sorted((forge / "src/closy_forge/blueprint_progress_v3").glob("*.py")):
        inputs.record(path)
    blueprint, crosswalk = current_blueprint(forge, counts)
    seam_rows = [row for row in compact_rows if "audit" in row]
    seam_passes = sum(row["audit"]["physicalSeamAcceptance"] is True for row in seam_rows)
    summary = {
        "version": "closy.family_integration.publication_result.v1",
        "evaluationVersion": result["version"],
        "counts": counts,
        "sourceHead": result["sourceHead"],
        "host": result["host"],
        "elapsedWallSeconds": result["elapsedWallSeconds"],
        "classification": "exposed_development_host_cpu",
        "rows": compact_rows,
        "negatives": result["negatives"],
        "captureSummaryFile": "capture_summaries.json",
        "seamAcceptance": {
            "planned": 54,
            "passed": seam_passes,
            "failed": len(seam_rows) - seam_passes,
            "notRun": 54 - len(seam_rows),
            "thresholdM": 0.008,
        },
        "quality": {
            "unitAComplete": False,
            "globalPhase8Complete": False,
            "physicalQualification": False,
            "captureParameterEstimation": "unsupported",
            "manualProviderUnitB": "pending_parent_update",
            "packageLayerRuntimeUnitC": "pending_parent_update",
        },
        "verificationScope": (
            "saved record consistency and file integrity; no geometry re-evaluation"
        ),
    }
    family_index = [
        {
            **{key: row.get(key) for key in ("family", "caseId", "terminal", "packageIdentity")},
            "profile": PROFILE,
            "resultRow": position,
            "repeat": 1,
            "supportedMotion": "analytic_binding_fidelity_only",
            "layerSupport": "separate_semantic_parts_not_collision_qualified",
        }
        for position, row in enumerate(compact_rows)
        if row["repeat"] == 1
    ]
    documents = {
        "protocol.json": protocol_bytes,
        "source_inventory.json": source_bytes,
        "result.json": canonical(summary),
        "family_index.json": canonical(family_index),
        "capture_summaries.json": canonical(
            {
                "counts": counts["captures"],
                "rows": result["captures"],
                "inputClass": "known_parameter_synthetic_roundtrip",
            }
        ),
        "retained_development.json": canonical(retained),
        "protected_sources.json": canonical(protection),
        "blueprint_current.json": canonical(blueprint),
        "blueprint_crosswalk.json": canonical(crosswalk),
        "progress.md": render_progress(summary, blueprint).encode(),
    }
    inputs.unchanged()
    require(
        _source_review(forge, source)["reachableSourceDigest"] == review["reachableSourceDigest"],
        "source_changed_during_publication",
    )
    require(audit_repository(forge.parent) == protection, "repository_changed_during_publication")
    documents["provenance.json"] = canonical(
        {
            "version": "closy.family_integration.publication_provenance.v1",
            "basePr66": PR66,
            "publicationHead": protection["head"],
            "publicationTree": protection["tree"],
            "evaluationRoot": root.relative_to(forge).as_posix(),
            "sourceReview": review,
            "inputs": list(inputs.records.values()),
            "currentScriptTestReceipt": current_receipt,
            "receiptScope": (
                "publication-time hashes; neither start-time freeze nor passing test receipt"
            ),
            "rawEvaluationResultPreservedAtSource": True,
            "copiesExcluded": [
                "GLB meshes",
                "binding binaries",
                "PNG images",
                "projection samples",
            ],
            "evaluatorReexecuted": False,
            "scientificQualification": False,
        }
    )
    return documents


def render_progress(result: Mapping[str, Any], blueprint: Mapping[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        "# Family Integration V1: Saved Unit A Evidence",
        "",
        f"PR66 base `{PR66}`; B/C pending parent update.",
        "",
        f"Conventional builds: {counts['builds']['passed']}/54 passed, "
        f"{counts['builds']['failed']} failed. Deterministic: {counts['deterministicTwoRoots']}.",
        "Geometry validity is not seam convergence, physical qualification or image estimation.",
        f"Seam predicate: {result['seamAcceptance']['passed']}/54 pass; "
        f"{result['seamAcceptance']['failed']} fail; {result['seamAcceptance']['notRun']} not run.",
        "",
        "[Result](result.json) | [Capture](capture_summaries.json) | "
        "[Retained failures/prototypes](retained_development.json) | [Provenance](provenance.json)",
        "",
        "## Phase 0-14",
        "",
        "PR66 implementation/evidence below is retained; Unit A additions are separately labeled.",
        "| Phase | Baseline supported scope | Unit A update | Unmet gates / dependencies |",
        "|---|---|---|---|",
    ]
    for row in blueprint["phaseOverview"]["phases"]:
        code = row["implementationAnchors"][0]
        evidence = row["evidenceAnchors"][0]
        lines.append(
            f"| {row['roadmapPhase']}: {row['title']} | "
            f"[{row['supportedScope']}](../../../{code}) "
            f"[Baseline evidence](../../../{evidence}) | "
            f"{row.get('currentUnitAEvidence', 'No new phase acceptance.')} | "
            f"{row['unmetGates']} {row['dependencies']} |"
        )
    lines += [
        "",
        "[Current inventory](blueprint_current.json) | "
        "[Historical crosswalk](blueprint_crosswalk.json). No overall completion percentage.",
        "",
        "Only a verified publication_manifest.json marks this directory complete.",
        "",
    ]
    return "\n".join(lines)


def write_fresh(output: Path, documents: Mapping[str, bytes]) -> dict[str, Any]:
    require(not output.exists() and not output.is_symlink(), "publication_output_must_be_fresh")
    require("publication_manifest.json" not in documents, "reserved_manifest_name")
    require(sum(map(len, documents.values())) <= 8 * 1024 * 1024, "publication_not_compact")
    for relative in documents:
        safe_path(output.parent, f"{output.name}/{relative}")
    manifest: dict[str, Any] = {
        "version": "closy.family_integration.publication_manifest.v1",
        "completion": "complete_saved_artifact_publication_not_quality_acceptance",
        "files": [
            {"path": name, "byteSize": len(data), "sha256": digest(data)}
            for name, data in sorted(documents.items())
        ],
        "selfReferencePolicy": "publicationIdentity hashes manifest without publicationIdentity",
    }
    manifest["publicationIdentity"] = digest(canonical(manifest))
    output.mkdir(parents=True, exist_ok=False)
    # Exclusive writes and a last-written marker leave interrupted outputs visibly incomplete.
    for relative, data in documents.items():
        path = safe_path(output, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
    with (output / "publication_manifest.json").open("xb") as handle:
        handle.write(canonical(manifest))
    return verify_publication(output, expected_identity=manifest["publicationIdentity"])


def verify_publication(output: Path, *, expected_identity: str | None = None) -> dict[str, Any]:
    manifest = dict(read_json(output, "publication_manifest.json"))
    identity = manifest.get("publicationIdentity")
    require(
        identity
        == digest(
            canonical(
                {key: value for key, value in manifest.items() if key != "publicationIdentity"}
            )
        ),
        "publication_identity_mismatch",
    )
    require(expected_identity is None or identity == expected_identity, "unexpected_publication")
    names = set()
    for row in manifest["files"]:
        require(
            row["path"] not in names and row["path"] != "publication_manifest.json",
            "publication_inventory_duplicate_or_self_reference",
        )
        names.add(row["path"])
        data = read_bytes(output, row["path"])
        require(
            digest(data) == row["sha256"] and len(data) == row["byteSize"],
            "publication_file_hash_mismatch",
        )
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    require(actual == names | {"publication_manifest.json"}, "publication_file_set_mismatch")
    return manifest


def publish(
    evaluation_root: Path,
    output: Path,
    *,
    forge_root: Path,
    initial_root: Path | None = None,
    prototype_roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    forge = forge_root.resolve(strict=True)
    safe_path(forge, output.absolute().relative_to(forge).as_posix())
    require(output.absolute().is_relative_to(forge / "docs/evidence"), "output_outside_evidence")
    require(not output.exists(), "publication_output_must_be_fresh")
    documents = prepare_publication(
        evaluation_root,
        forge_root=forge,
        initial_root=initial_root or forge / ".tmp/family-final-v1",
        prototype_roots=prototype_roots
        or (
            forge / ".tmp/family-dev-01/long_sleeved_top",
            forge / ".tmp/family-dev-02/long_sleeved_top",
        ),
    )
    return write_fresh(output, documents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--forge-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = publish(
        args.evaluation_root.absolute(),
        (args.output or args.forge_root / "docs/evidence/family_integration_v1").absolute(),
        forge_root=args.forge_root,
    )
    print(
        json.dumps(
            {
                "publicationIdentity": manifest["publicationIdentity"],
                "fileCount": len(manifest["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()
