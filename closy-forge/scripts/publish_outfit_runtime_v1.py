"""Publish saved receipts only, including failures. Never execute campaign code.

First --capture-expected PATH after all roots are complete. Review and retain its
printed SHA-256 externally. Then --expected PATH --expected-sha256 HASH --output
FRESH_DIRECTORY. This is an artifact trust snapshot, not a new experiment protocol.
The active resume pointer and Git publication are deliberately parent-owned.
After repairs select the completed attempt roots explicitly. External memory is
opt-in: pass historical samples as --probe, not as the current --host-memory.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import re
import stat
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_family_integration_v1 import (  # noqa: E402
    FAMILIES,
    audit_repository,
    canonical,
    decode,
    digest,
    require,
    safe_path,
)

from closy_forge.security.evidence_hygiene import (  # noqa: E402
    scan_evidence_files,
    scan_evidence_text,
)

FORGE = Path(__file__).resolve().parents[1]
VERSION = "closy.outfit_runtime.saved_publication.v1"
PROJECTION_VERSION = "closy.saved_receipt.portable_projection.v1"
MAX_FILE = 128 * 1024 * 1024
MAX_COMPACT = 64 * 1024 * 1024
MAX_FILES = 20000
SHA = re.compile(r"[0-9a-f]{64}\Z")
OUTFIT_STATES = ("neutral", "reach_left", "twist_right", "step_left")
POSES = ("pose.arms_up", "pose.neutral", "pose.torso_twist", "pose.walk_stride")
PROFILES = ("cpu-balanced-64k-v2", "cpu-compact-32k-v2")
NEGATIVES = (
    "cycle",
    "missing",
    "duplicate",
    "units",
    "avatar",
    "stale_binding",
    "impossible_clearance",
    "geometry",
    "nonfinite_geometry",
    "nonfinite_material",
    "opening_policy",
    "tampered_report",
    "forged_empty_witnesses",
)
ROOT_FILES = {
    "outfit": ("protocol.json", "source_inventory.json", "checkpoint.json", "result.json"),
    "runtime": ("protocol.json", "checkpoint.json", "result.json", "controls.xml", "controls.log"),
    "static": ("protocol.json", "source_receipt.json", "receipt_manifest.json", "result.json"),
    "prior_static": (
        "protocol.json",
        "source_receipt.json",
        "receipt_manifest.json",
        "result.json",
    ),
    "demo": ("report.json", "output_inventory.json", "index.html"),
    "binding": ("protocol.json", "source_inventory.json", "input_inventory.json", "result.json"),
    "blueprint": ("blueprint_current.json",),
}


class PortableProjection:
    """Aliases are presentation only. Raw receipts remain the verification authority."""

    _windows = r"(?:[A-Za-z]:[\\/]+|\\\\[A-Za-z0-9._-]+[\\/]+)"
    _posix = r"/(?:home|Users|root|tmp|private|var|opt|usr|mnt|workspace|workspaces)/"
    _start = rf"(?:{_windows}|{_posix})"
    _quoted = re.compile(rf"(?P<quote>[\"'`])(?P<path>{_start}[^\r\n]*?)(?P=quote)")
    _bare = re.compile(rf"(?<![A-Za-z0-9]){_start}[^\s\"'`<>|;,(){{}}\[\]]*")

    def __init__(self, aliases: dict[str, str]):
        self.patterns: list[tuple[re.Pattern[str], str]] = []
        self.catalog: dict[str, dict[str, str]] = {}
        for alias, raw in sorted(aliases.items(), key=lambda pair: (-len(pair[1]), pair[0])):
            normalized = re.sub(r"[\\/]+", "/", raw).rstrip("/")
            require(bool(normalized), "empty_projection_root")
            expression = r"[\\/]+".join(re.escape(p) for p in normalized.split("/"))
            expression += r"(?=$|[\\/\s\"'`<>),;])"
            self.patterns.append((re.compile(expression, re.I), alias))
            self.catalog[alias] = {
                "alias": alias,
                "rawRootPathSha256": digest(raw.encode()),
                "kind": "declared_workspace_alias",
            }

    def _opaque(self, path: str) -> str:
        path_hash = digest(path.encode())
        alias = f"workspace/local-paths/{path_hash}"
        self.catalog[alias] = {
            "alias": alias,
            "rawPathSha256": path_hash,
            "kind": "unmapped_local_path_alias",
        }
        return alias

    def text(self, value: str) -> str:
        for pattern, alias in self.patterns:
            value = pattern.sub(alias.replace("\\", r"\\"), value)
        value = self._quoted.sub(lambda m: m["quote"] + self._opaque(m["path"]) + m["quote"], value)
        value = self._bare.sub(lambda m: self._opaque(m[0]), value)
        # Normalize only tails following an alias, not unrelated regular expressions.
        return re.sub(
            r"(?:inputs/|workspace/)[^\r\n\"'`<>]*", lambda m: re.sub(r"\\+", "/", m[0]), value
        )

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            projected: dict[str, Any] = {}
            for key, item in value.items():
                require(isinstance(key, str), "projection_non_string_key")
                name = self.text(key)
                require(name not in projected, "projection_key_collision")
                projected[name] = self.value(item)
            return projected
        return value


def portable_payload(
    payload: dict[str, bytes], raw_receipt_paths: set[str], aliases: dict[str, str]
) -> dict[str, bytes]:
    projector = PortableProjection(aliases)
    result: dict[str, bytes] = {}
    receipts = []
    for rel, raw in sorted(payload.items()):
        source_kind = (
            "raw_saved_receipt" if rel in raw_receipt_paths else "derived_before_projection"
        )
        metadata = {
            "version": PROJECTION_VERSION,
            "sourceKind": source_kind,
            "preProjectionSha256": digest(raw),
            "preProjectionBytes": len(raw),
            "embeddedSourceDigestsApplyTo": "original_unprojected_sources_not_this_projection",
            "publishedHashAuthority": "projection_manifest.json",
        }
        if rel in raw_receipt_paths:
            metadata["rawReceiptSha256"] = digest(raw)
        if Path(rel).suffix.lower() in {".json", ".md", ".txt", ".log", ".xml", ".html", ".csv"}:
            text = raw.decode("utf-8")
            non_path_findings = set(scan_evidence_text(text)) - {
                "windows_absolute_path",
                "posix_home_path",
            }
            require(not non_path_findings, f"unsafe_receipt_content:{rel}")
            if rel.endswith(".json"):
                document = projector.value(decode(raw))
                if isinstance(document, dict):
                    require(
                        "_publicationProjection" not in document, "projection_metadata_collision"
                    )
                    document["_publicationProjection"] = metadata
                published = canonical(document)
            else:
                published = projector.text(text).encode("utf-8")
            require(
                not scan_evidence_text(published.decode("utf-8")),
                f"unsafe_projected_evidence:{rel}",
            )
        else:
            published = raw
        result[rel] = published
        receipts.append(
            {
                "path": rel,
                **metadata,
                "publishedProjectionSha256": digest(published),
                "publishedProjectionBytes": len(published),
                "byteExact": published == raw,
            }
        )
    result["projection_manifest.json"] = canonical(
        {
            "version": PROJECTION_VERSION,
            "receipts": receipts,
            "aliases": [projector.catalog[key] for key in sorted(projector.catalog)],
            "rawReceiptsRetainedAtOriginalInputRoots": True,
            "publishedDocumentsAreNotRawReceiptBytes": True,
            "embeddedIdentitiesMustNotBeRecomputedAgainstProjectedDocuments": True,
            "hashAuthority": (
                "publishedProjectionSha256 identifies each published file; "
                "rawReceiptSha256 identifies its original receipt"
            ),
        }
    )
    require(
        not scan_evidence_text(result["projection_manifest.json"].decode()),
        "unsafe_projection_ledger",
    )
    return result


def projection_aliases(roots: dict[str, Path], forge: Path, family_root: Path) -> dict[str, str]:
    return {
        "workspace/repository": str(forge.parent.absolute()),
        "workspace/forge": str(forge.absolute()),
        "inputs/family": str(family_root.absolute()),
        **{f"inputs/{scope}": str(path.absolute()) for scope, path in roots.items()},
    }


def exact(a: Any, b: Any, code: str) -> None:
    require(canonical(a) == canonical(b), code)


def identity(doc: dict[str, Any], field: str) -> str:
    body = dict(doc)
    claimed = body.pop(field, None)
    require(
        isinstance(claimed, str) and digest(canonical(body)) == claimed,
        f"identity_mismatch:{field}",
    )
    return str(claimed)


def guarded(root: Path, relative: str) -> Path:
    path = safe_path(root, relative)
    require(
        not any(
            p.is_symlink()
            or (
                p.exists()
                and getattr(p.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            )
            for p in (path, *path.parents)
        ),
        "linked_path",
    )
    for part in relative.split("/"):
        require(
            not part.endswith((".", " "))
            and not re.match(r"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)", part, re.I),
            "windows_alias_path",
        )
    return path


class Reader:
    """Bounded reads, streaming asset hashes, and a final TOCTOU freshness check."""

    def __init__(self, roots: dict[str, Path]):
        self.roots = roots
        self.seen: dict[Path, tuple[str, int]] = {}
        self.copies: dict[str, bytes] = {}

    def file(self, root: Path, rel: str) -> Path:
        path = guarded(root, rel)
        require(path.is_file() and path.stat().st_size <= MAX_FILE, f"file_missing_or_large:{path}")
        return path

    def hash(self, root: Path, rel: str) -> str:
        path = self.file(root, rel)
        h = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                h.update(block)
        value = (h.hexdigest(), path.stat().st_size)
        if path in self.seen:
            exact(value, self.seen[path], "input_changed_during_verification")
        self.seen[path] = value
        require(len(self.seen) <= MAX_FILES, "file_count_budget")
        return value[0]

    def read(self, scope: str, rel: str, *, retain: bool = True) -> bytes:
        root = self.roots[scope].parent if scope.startswith("probe-") else self.roots[scope]
        path = self.file(root, rel)
        require(path.stat().st_size <= MAX_COMPACT, "compact_file_budget")
        raw = path.read_bytes()
        require(digest(raw) == self.hash(root, rel), "input_changed_during_read")
        if retain:
            self.copies[f"{scope}/{rel}"] = raw
            require(sum(map(len, self.copies.values())) <= MAX_COMPACT, "compact_total_budget")
        return raw

    def doc(self, scope: str, rel: str) -> Any:
        return decode(self.read(scope, rel))

    def external_doc(self, root: Path, rel: str) -> Any:
        path = self.file(root, rel)
        raw = path.read_bytes()
        require(digest(raw) == self.hash(root, rel), "external_document_changed")
        return decode(raw)

    def inventory(self, root: Path, rows: list[dict[str, Any]]) -> set[str]:
        require(isinstance(rows, list) and 0 < len(rows) <= MAX_FILES, "inventory_shape")
        seen: set[str] = set()
        for row in rows:
            rel = row["path"]
            require(isinstance(rel, str) and rel not in seen, "duplicate_inventory_path")
            seen.add(rel)
            size = row.get("byteSize", row.get("bytes"))
            if size is not None:
                require(type(size) is int and 0 <= size <= MAX_FILE, "inventory_size")
                require(self.file(root, rel).stat().st_size == size, "inventory_size_mismatch")
            require(self.hash(root, rel) == row["sha256"], f"inventory_hash_mismatch:{rel}")
        return seen

    def source(self, forge: Path, files: dict[str, str]) -> None:
        require(isinstance(files, dict) and bool(files), "source_inventory_empty")
        for rel, expected in files.items():
            require(self.hash(forge, rel) == expected, f"source_not_fresh:{rel}")

    def fresh(self) -> None:
        for path in list(self.seen):
            self.hash(path.parent, path.name)


def compact(reader: Reader) -> None:
    """Retain readable witnesses, not duplicate meshes or runtime archives."""
    for scope, files in ROOT_FILES.items():
        for rel in files:
            reader.read(scope, rel)
    for scope in ("static", "prior_static"):
        manifest = reader.doc(scope, "receipt_manifest.json")
        for row in manifest["files"]:
            reader.read(scope, row["path"])
    for scope, patterns in {
        "outfit": ("outfit*/*/manifest.json", "outfit*/*/report.json", "outfit*/*/context.json"),
        "runtime": (
            "*/receipt.json",
            "*/process.log",
            "*/package/manifest.json",
            "*/package/payload.closyruntime/build_report.json",
        ),
        "demo": ("inspection/*.png", "outfit/report.json", "outfit/manifest.json"),
    }.items():
        root = reader.roots[scope]
        for pattern in patterns:
            for p in sorted(root.glob(pattern)):
                reader.read(scope, p.relative_to(root).as_posix())
    for scope in reader.roots:
        if scope.startswith("probe-"):
            reader.read(scope, reader.roots[scope].name)


def capture_expected(roots: dict[str, Path], forge: Path) -> dict[str, Any]:
    reader = Reader(roots)
    compact(reader)
    snapshot = {
        "version": VERSION,
        "trustScope": "external_completed_artifact_snapshot_not_experiment_predeclaration",
        "roots": {s: str(p.resolve()) for s, p in roots.items()},
        "forge": str(forge.resolve()),
        "files": {p: digest(b) for p, b in sorted(reader.copies.items())},
        "denominators": {
            "outfit": 40,
            "adjacent": 30,
            "negatives": 13,
            "runtime": 44,
            "runtimeFamily": 36,
            "static": 9,
        },
    }
    reader.fresh()
    return snapshot


def verify_expected(
    reader: Reader, expected: dict[str, Any], expected_hash: str, forge: Path
) -> None:
    require(
        SHA.fullmatch(expected_hash) is not None and digest(canonical(expected)) == expected_hash,
        "external_snapshot_hash_mismatch",
    )
    exact(expected["version"], VERSION, "snapshot_version")
    exact(
        expected["roots"], {s: str(p.resolve()) for s, p in reader.roots.items()}, "snapshot_roots"
    )
    exact(expected["forge"], str(forge.resolve()), "snapshot_forge")
    compact(reader)
    exact(
        {p: digest(b) for p, b in sorted(reader.copies.items())},
        expected["files"],
        "artifact_or_protocol_snapshot_changed",
    )


def verify_manifest(
    reader: Reader, root: Path, field: str, expected_hash: str | None = None
) -> dict[str, Any]:
    if expected_hash is not None:
        require(reader.hash(root, "manifest.json") == expected_hash, "output_manifest_mismatch")
    doc = reader.external_doc(root, "manifest.json")
    identity(doc, field)
    reader.inventory(root, doc["inventory"])
    return dict(doc)


def outfit_summary(reader: Reader, forge: Path) -> dict[str, Any]:
    p, r = reader.doc("outfit", "protocol.json"), reader.doc("outfit", "result.json")
    exact(p["version"], "package_layering_matrix_v1", "outfit_protocol_version")
    exact(
        p["thresholds"],
        {
            "binding_tolerance_m": 2e-6,
            "iterations": 12,
            "max_displacement_m": 0.045,
            "max_step_m": 0.004,
            "opening_length_drift": 0.1,
            "residual_m": 0.00016,
            "seam_budget_m": 0.008,
        },
        "outfit_thresholds_changed",
    )
    exact(
        [p["stateDenominator"], p["adjacentSampleDenominator"], p["negativeDenominator"]],
        [40, 30, 13],
        "outfit_protocol_denominators",
    )
    exact([s["state_id"] for s in p["poseStates"]], list(OUTFIT_STATES), "outfit_states")
    cases = p["positiveCases"]
    exact([c["caseId"] for c in cases], [f"outfit{i:02d}" for i in range(1, 11)], "outfit_cases")
    require(
        r["protocolHash"] == reader.hash(reader.roots["outfit"], "protocol.json"),
        "outfit_protocol_hash",
    )
    reader.source(forge, reader.doc("outfit", "source_inventory.json")["files"])
    require(r["sourcesUnchanged"] is True, "outfit_declared_stale")
    exact(
        [(x["caseId"], x["pose"]) for x in r["rows"]],
        [(c["caseId"], s) for c in cases for s in OUTFIT_STATES],
        "outfit_row_denominator",
    )
    counts = Counter(x["terminal"] for x in r["rows"])
    require(set(counts) <= {"passed", "quality_failed", "failed"}, "outfit_terminal")
    exact(
        [r["denominator"], r["qualityPassed"], r["validGeometry"], r["failed"]],
        [
            40,
            counts["passed"],
            sum(x.get("geometryValid") is True for x in r["rows"]),
            counts["failed"],
        ],
        "outfit_forged_summary",
    )
    for row in r["rows"]:
        if row["terminal"] == "failed":
            continue
        root = reader.roots["outfit"] / row["caseId"] / row["pose"]
        manifest = verify_manifest(reader, root, "identity", row["manifestHash"])
        report = reader.external_doc(root, "report.json")
        exact(report["ready"], row["terminal"] == "passed", "outfit_ready_mismatch")
        exact(report["before"], row["before"], "outfit_before_mismatch")
        after = dict(report["after"])
        after.pop("witnesses", None)
        exact(after, row["after"], "outfit_after_mismatch")
        case = next(c for c in cases if c["caseId"] == row["caseId"])
        sources = {}
        for layer in case["layers"]:
            source = verify_manifest(reader, Path(layer["package"]), "packageIdentity")
            sources[layer["layer_id"]] = source["packageIdentity"]
        exact(manifest["sources"], sources, "outfit_source_identity_mismatch")
    exact(
        [(a["caseId"], a["from"], a["to"]) for a in r["adjacentSamples"]],
        [
            (c["caseId"], a, b)
            for c in cases
            for a, b in zip(OUTFIT_STATES, OUTFIT_STATES[1:], strict=False)
        ],
        "outfit_adjacent_denominator",
    )
    exact([x["case"] for x in r["negatives"]], list(NEGATIVES), "outfit_negative_denominator")
    return {
        "denominator": 40,
        "qualityPassed": counts["passed"],
        "qualityFailed": counts["quality_failed"],
        "executionFailed": counts["failed"],
        "validGeometry": r["validGeometry"],
        "adjacentDenominator": 30,
        "adjacentExecuted": sum(x["terminal"] == "executed" for x in r["adjacentSamples"]),
        "negativeDenominator": 13,
        "negativeRejected": sum(x["terminal"] == "passed_rejection" for x in r["negatives"]),
        "contactRemeasuredByPublisher": False,
        "scope": "saved_independent_evaluator_receipts_not_new_contact_or_physical_validation",
    }


def junit_summary(raw: bytes, inventory: list[str]) -> dict[str, int]:
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "unsafe_junit")
    tree = ET.fromstring(raw)
    cases = list(tree.iter("testcase"))
    expected = [x.split("::", 1)[1] for x in inventory]
    exact(sorted(c.get("name") for c in cases), sorted(expected), "junit_control_inventory")
    return {
        "total": len(cases),
        "failed": sum(c.find("failure") is not None or c.find("error") is not None for c in cases),
        "skipped": sum(c.find("skipped") is not None for c in cases),
    }


def runtime_source(reader: Reader, source: dict[str, Any]) -> None:
    root = Path(source["root"])
    require(
        reader.hash(root, source["manifest"]) == source["manifestSha256"], "runtime_input_manifest"
    )
    manifest = reader.external_doc(root, source["manifest"])
    field = "packageIdentity"
    if manifest.get("packageVersion") == "closy.manual_provider_binding_v2.package.v2":
        field = "packageDigest"
        exact(source["bindingCodec"], "CLSYBV2_local_frame", "runtime_binding_codec")
    elif manifest.get("profile") == "package_mesh_layering_development_v1":
        field = "identity"
    identity(manifest, field)
    paths = reader.inventory(root, manifest["inventory"])
    require(
        source["provenance"] in (manifest.get("packageIdentity"), source["manifestSha256"]),
        "runtime_provenance",
    )
    for key in ("garmentId", "avatarId"):
        if key in manifest:
            exact(source[key], manifest[key], "runtime_source_external_identity")
    require(source["garmentId"].startswith("garment."), "runtime_garment_prefix")
    require(
        all(source[k] in paths for k in ("render", "cage", "binding")),
        "runtime_descriptor_path_not_in_inventory",
    )
    quality = source.get("sourceQuality", {})
    if "fitReady" in quality:
        require(
            reader.hash(root, "report.json") == quality["reportSha256"],
            "runtime_source_quality_report_hash",
        )
        exact(
            quality["fitReady"],
            reader.external_doc(root, "report.json")["ready"],
            "runtime_source_fit_claim",
        )


def runtime_summary(reader: Reader, forge: Path) -> dict[str, Any]:
    p, r = reader.doc("runtime", "protocol.json"), reader.doc("runtime", "result.json")
    identity(p, "protocolIdentity")
    exact(r["protocolIdentity"], p["protocolIdentity"], "runtime_protocol_identity")
    reader.source(forge, p["sourceInventory"])
    require(r["sourceFresh"] is True, "runtime_declared_stale")
    exact(
        [p["familyRows"], p["poseRowsPerBuild"], p["resumeRowsPerBuild"]],
        [36, 4, 3],
        "runtime_denominators",
    )
    exact(p["poseIds"], list(POSES), "runtime_poses")
    cases = p["cases"]
    exact(
        Counter(c["group"] for c in cases),
        {"family": 36, "binding": 4, "outfit": 4},
        "runtime_group_denominators",
    )
    ids = [c["id"] for c in cases]
    require(
        len(ids) == len(set(ids)) == 44 and set(ids) == set(r["rows"]), "runtime_row_denominator"
    )
    family_keys = {(c["case"], c["profile"], c["build"]) for c in cases if c["group"] == "family"}
    exact(
        sorted(family_keys),
        sorted((f, p, b) for f in FAMILIES for p in PROFILES for b in (1, 2)),
        "runtime_family_cross_product",
    )
    checkpoint = reader.doc("runtime", "checkpoint.json")
    exact(checkpoint["rows"], r["rows"], "runtime_checkpoint_rows")
    exact(checkpoint["controls"], r["controls"], "runtime_checkpoint_controls")
    by_group: dict[str, dict[str, int]] = {}
    for case in cases:
        row = r["rows"][case["id"]]
        require(row["status"] in ("pass", "fail", "unknown"), "runtime_terminal")
        group = by_group.setdefault(
            case["group"], {"denominator": 0, "pass": 0, "fail": 0, "unknown": 0}
        )
        group["denominator"] += 1
        group[row["status"]] += 1
        receipt = reader.doc("runtime", f"{case['id']}/receipt.json")
        exact(receipt, row, "runtime_worker_receipt")
        if row["status"] != "pass":
            continue
        exact(
            [row["poseCount"], row["workerExitCode"], row["processExitCode"]],
            [4, 0, 0],
            "runtime_worker_completion",
        )
        exact(row["protocolIdentity"], p["protocolIdentity"], "runtime_worker_protocol")
        exact(
            [x["point"] for x in row["resumes"]],
            ["first", "middle", "final"],
            "runtime_resume_denominator",
        )
        require(
            all(
                x["decodedIdentityMatch"] is True and x["aggregateHashMatch"] is True
                for x in row["resumes"]
            ),
            "runtime_resume_failed",
        )
        root = reader.roots["runtime"] / case["id"]
        manifest = verify_manifest(
            reader, root / "package", "packageIdentity", row["manifestSha256"]
        )
        exact(manifest["packageIdentity"], row["packageIdentity"], "runtime_package_identity")
        source = case["source"]
        exact(
            manifest["identity"],
            {
                "garmentId": source["garmentId"],
                "avatarId": source["avatarId"],
                "profileId": case["profile"],
                "provenance": source["provenance"],
            },
            "runtime_external_identity",
        )
        runtime_source(reader, source)
        for label in ("first", "middle", "final"):
            require(
                reader.hash(root, f"{label}.archive") == row["streamSha256"], "runtime_archive_hash"
            )
    pairs = []
    for case in cases:
        if case["build"] != 1:
            continue
        a = r["rows"][case["id"]]
        b = r["rows"][case["id"].removesuffix("build1") + "build2"]
        passed = a["status"] == b["status"] == "pass" and all(
            a.get(k) == b.get(k)
            for k in ("packageIdentity", "manifestSha256", "streamSha256", "transferIdentity")
        )
        pairs.append({"case": case["case"], "profile": case["profile"], "passed": passed})
    exact(pairs, r["determinism"], "runtime_determinism_summary")
    exact(
        r["family"],
        {k: by_group["family"][k] for k in ("pass", "fail", "unknown")},
        "runtime_forged_summary",
    )
    controls = junit_summary(reader.read("runtime", "controls.xml"), p["controlInventory"])
    if r["controls"]["status"] == "pass":
        require(
            controls["failed"] == controls["skipped"] == 0 and controls["total"] > 0,
            "runtime_false_controls_pass",
        )
    return {
        "groups": by_group,
        "controls": controls,
        "determinismPairs": len(pairs),
        "determinismPassed": sum(x["passed"] for x in pairs),
        "poseChecksPlanned": 176,
        "resumeChecksPlanned": 132,
        "representativeSourceQuality": {
            c["case"]: c.get("source", {}).get("sourceQuality", "not_declared")
            for c in cases
            if c["group"] != "family"
        },
        "scope": "analytic_cage_binding_fidelity_and_transport_not_avatar_cloth_or_mobile",
    }


def static_summary(reader: Reader, forge: Path, family_root: Path) -> dict[str, Any]:
    r = reader.doc("static", "result.json")
    p = reader.doc("static", "protocol.json")
    require(
        r["selectedCurrentFilesUnchanged"] is True and r["sourceEvaluationUnchanged"] is True,
        "static_declared_stale",
    )
    reader.source(forge, reader.doc("static", "source_receipt.json")["currentFiles"])
    for rel, value in p["sourceEvaluation"].items():
        require(reader.hash(family_root, rel) == value, "static_A_evaluation_changed")
    for scope in ("static", "prior_static"):
        receipt = reader.doc(scope, "receipt_manifest.json")
        reader.inventory(reader.roots[scope], receipt["files"])
    exact(r["familyDenominator"], 9, "static_denominator")
    exact([x["family"] for x in r["rows"]], list(FAMILIES), "static_family_rows")
    counts = Counter(x["terminal"] for x in r["rows"])
    require(set(counts) <= {"passed", "failed", "not_run"}, "static_terminal")
    exact(
        [r["passed"], r["failed"], r["notRun"]],
        [counts["passed"], counts["failed"], counts["not_run"]],
        "static_forged_summary",
    )
    for row in r["rows"]:
        if row["terminal"] != "passed":
            continue
        prefix = row["family"]
        audit = reader.doc("static", f"{prefix}/static_stage_audit.json")
        for key in ("passedStageIds", "failedStageIds", "notRunStageIds"):
            exact(row[key], audit[key], "static_stage_summary")
        current = reader.roots["static"] / prefix / "processor/current"
        reader.inventory(current, audit["inventory"]["files"])
        adapter = reader.doc("static", f"{prefix}/adapter_receipt.json")
        exact(adapter["adapterIdentity"], row["adapterIdentity"], "static_adapter_identity")
        source = family_root / "build1" / prefix / "nominal"
        for rel, value in adapter["source"]["files"].items():
            require(reader.hash(source, rel) == value, "static_A_package_changed")
        exact(
            adapter["source"]["packageIdentity"],
            row["sourcePackageIdentity"],
            "static_source_identity",
        )
    prior = reader.doc("prior_static", "result.json")
    return {
        "denominator": 9,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "notRun": counts["not_run"],
        "stageCounts": r["stageCounts"],
        "priorAttempt": {k: prior[k] for k in ("familyDenominator", "passed", "failed", "notRun")},
        "scope": "optional_static_CPU_Z3_Z7_and_dynamic_Z2_not_run",
    }


def binding_summary(reader: Reader, forge: Path) -> dict[str, Any]:
    r, p = reader.doc("binding", "result.json"), reader.doc("binding", "protocol.json")
    identity(r, "resultDigest")
    require(r["protocolDigest"] == digest(canonical(p)), "binding_protocol_digest")
    require(r["sourceAndInputsUnchanged"] is True and r["limitsUnchanged"] is True, "binding_stale")
    inventory = reader.doc("binding", "source_inventory.json")
    reader.source(forge, inventory["files"])
    exact(digest(canonical(inventory["files"])), r["sourceDigest"], "binding_source_digest")
    exact(
        [len(r["baselineRows"]), len(r["extraPositiveRows"]), len(r["extras"]), len(r["gates"])],
        [99, 44, 7, 17],
        "binding_denominators",
    )
    passed = sum(x["status"] == "pass" for x in r["baselineRows"])
    exact(
        [r["baselinePassedRows"], r["baselineFailedRows"]], [passed, 99 - passed], "binding_summary"
    )
    return {
        "baselinePassed": passed,
        "baselineDenominator": 99,
        "extraPositivePassed": sum(x["status"] == "pass" for x in r["extraPositiveRows"]),
        "extraPositiveDenominator": 44,
        "extraCases": 7,
        "gatesPassed": sum(x["status"] == "pass" for x in r["gates"]),
        "gateDenominator": 17,
        "resultDigest": r["resultDigest"],
        "unitACompatibility": r["unitACompatibility"],
        "scope": "exposed_manual_provider_not_global_C3",
    }


def demo_summary(reader: Reader) -> dict[str, Any]:
    report = reader.doc("demo", "report.json")
    files = reader.inventory(reader.roots["demo"], reader.doc("demo", "output_inventory.json"))
    images = ("family_contact_sheet.png", "sleeve_before_after.png", "binding_before_after.png")
    for name in images:
        rel = f"inspection/{name}"
        require(
            rel in files and reader.read("demo", rel).startswith(b"\x89PNG\r\n\x1a\n"),
            "demo_png_missing",
        )
    exact(len(report["familyAudits"]), 9, "demo_family_count")
    outfit = reader.doc("demo", "outfit/report.json")
    exact(report["outfitReady"], outfit["ready"], "demo_outfit_claim")
    exact(
        report["imageSource"],
        "actual_serialized_geometry_cpu_raster_no_generated_visuals",
        "demo_image_scope",
    )
    return {
        "familyAudits": 9,
        "outfitReady": report["outfitReady"],
        "imageCount": 3,
        "scope": "actual_geometry_inspection_not_photo_or_physical_acceptance",
    }


def overlay_blueprint(base: dict[str, Any], outcomes: dict[str, Any]) -> dict[str, Any]:
    """Add scoped evidence, never rewrite original gates, statuses or qualification."""
    result = copy.deepcopy(base)
    view = result["phaseOverview"]
    exact([p["roadmapPhase"] for p in view["phases"]], list(range(15)), "blueprint_phase_inventory")
    by_phase = {
        6: {"binding": outcomes["binding"]},
        8: {"static": outcomes["static"], "runtime": outcomes["runtime"]},
        10: {"static": outcomes["static"]},
        12: {"runtime": outcomes["runtime"]},
        13: {"outfit": outcomes["outfit"], "demo": outcomes["demo"]},
    }
    for phase in view["phases"]:
        if phase["roadmapPhase"] in by_phase:
            phase["currentBCDerivedOutcome"] = by_phase[phase["roadmapPhase"]]
            phase["historicalFieldsPreserved"] = True
    view["newUnitOutcomes"]["B"] = outcomes["binding"]
    view["newUnitOutcomes"]["C"] = {k: outcomes[k] for k in ("outfit", "runtime", "static", "demo")}
    view["successorEvidenceScope"] = "saved_artifact_development_overlay_no_qualification_change"
    return result


def external_memory_summary(reader: Reader) -> dict[str, Any]:
    scope = "probe-host-memory"
    if scope not in reader.roots:
        return {
            "status": "not_available",
            "maximumSampledProcessPeakBytes": None,
            "isolatedPerCaseMemory": "not_measured",
        }
    receipt = reader.doc(scope, reader.roots[scope].name)
    exact(
        receipt["scope"],
        "external_Windows_process_peak_sampling_not_per_case_isolated_memory",
        "memory_scope_invalid",
    )
    early = receipt["earlierRowsNotIndividuallySampled"]
    require(type(early) is int and 0 <= early <= 40, "memory_coverage_invalid")
    samples = receipt["samples"]
    require(isinstance(samples, list) and bool(samples), "memory_samples_missing")
    for sample in samples:
        require(
            type(sample["peakWorkingSetBytes"]) is int and sample["peakWorkingSetBytes"] > 0,
            "memory_sample_invalid",
        )
        require(
            type(sample["completedRows"]) is int and early <= sample["completedRows"] <= 40,
            "memory_sample_coverage_invalid",
        )
    return {
        "status": "sampled",
        "scope": receipt["scope"],
        "processId": receipt["processId"],
        "earlierRowsNotIndividuallySampled": early,
        "sampleCount": len(samples),
        "maximumSampledProcessPeakBytes": max(s["peakWorkingSetBytes"] for s in samples),
        "isolatedPerCaseMemory": "not_measured",
        "physicalMobile": "not_run",
        "receipt": f"{scope}/{reader.roots[scope].name}",
    }


def publish(
    roots: dict[str, Path],
    *,
    forge: Path,
    family_root: Path,
    output: Path,
    expected: dict[str, Any],
    expected_hash: str,
) -> dict[str, Any]:
    require(not output.exists(), "publication_output_must_be_fresh")
    guarded(output.parent, output.name)
    for root in (*roots.values(), forge / "src", forge / "tests", family_root):
        require(
            not output.resolve().is_relative_to(root.resolve())
            and not root.resolve().is_relative_to(output.resolve()),
            "publication_overlaps_input",
        )
    reader = Reader(roots)
    verify_expected(reader, expected, expected_hash, forge)
    lock = audit_repository(forge.parent)
    outcomes = {
        "outfit": outfit_summary(reader, forge),
        "runtime": runtime_summary(reader, forge),
        "static": static_summary(reader, forge, family_root),
        "binding": binding_summary(reader, forge),
        "demo": demo_summary(reader),
    }
    base = reader.doc("blueprint", "blueprint_current.json")
    view = overlay_blueprint(base, outcomes)
    payload = dict(reader.copies)
    payload["blueprint_current.json"] = canonical(view)
    payload["summary.json"] = canonical(
        {
            "version": VERSION,
            "outcomes": outcomes,
            "externalHostMemory": external_memory_summary(reader),
            "publicationStatus": "verified_saved_receipts_including_failures",
            "qualityStatus": "not_promoted",
            "scientificQualification": False,
            "physicalMobile": "not_run",
            "rawExpectedSnapshotSha256": expected_hash,
        }
    )
    payload["expected_snapshot.json"] = canonical(expected)
    payload["protected_sources.json"] = canonical(lock)
    payload["verification_inventory.json"] = canonical(
        [{"path": str(p), "sha256": h, "bytes": n} for p, (h, n) in sorted(reader.seen.items())]
    )
    payload["README.md"] = (
        "# Outfit and Runtime Saved Evidence\n\n"
        "Publication verifies saved hashes, identities and exact row inventories only. "
        "It does not rerun contacts, decode geometry, rebuild packages or grant qualification.\n\n"
        "Published text/JSON are portable projections, not raw receipts. Local paths "
        "use inputs/ and workspace/ aliases. projection_manifest.json records raw receipt "
        "SHA-256 and published projection SHA-256 separately. Embedded original protocol, "
        "package and result digests apply only to unprojected source receipts. JSON objects "
        "carry _publicationProjection notices; arrays/text are described by the same ledger. "
        "The raw expected snapshot remains outside evidence and must not be replaced by "
        "the projected expected_snapshot.json. Exact local commands belong in parent docs.\n\n"
        f"Outfit fit: {outcomes['outfit']['qualityPassed']}/40; "
        f"geometry: {outcomes['outfit']['validGeometry']}/40. "
        "Quality failures remain in result.json and the phase overlay.\n\n"
        "See summary.json, blueprint_current.json, retained protocols/results, runtime "
        "controls.xml, static and prior_static receipts, and demo/index.html. Binary assets "
        "remain at the input paths recorded in verification_inventory.json.\n\n"
        "Optional external memory samples describe cumulative Windows process peaks, "
        "not isolated per-case memory. Earlier unsampled rows and unavailable internal "
        "memory values are retained, never replaced with zero.\n\n"
        "docs/ACTIVE_BLUEPRINT_RESUME_OUTFIT_RUNTIME_V1.md is parent-owned; this publisher "
        "does not create or modify an active pointer.\n"
    ).encode()
    payload = portable_payload(
        payload,
        set(reader.copies) | {"expected_snapshot.json"},
        projection_aliases(roots, forge, family_root),
    )
    reader.fresh()
    require(sum(map(len, payload.values())) <= MAX_COMPACT, "publication_size_budget")
    output.mkdir(parents=True, exist_ok=False)
    for rel, raw in sorted(payload.items()):
        path = guarded(output, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    reader.fresh()
    text_paths = [
        guarded(output, rel)
        for rel in payload
        if Path(rel).suffix.lower() in {".json", ".md", ".txt", ".log", ".xml", ".html", ".csv"}
    ]
    require(not scan_evidence_files(text_paths), "published_evidence_hygiene_failed")
    manifest = {
        "version": VERSION,
        "projectionVersion": PROJECTION_VERSION,
        "rawExpectedSnapshotSha256": expected_hash,
        "publishedExpectedSnapshotSha256": digest(payload["expected_snapshot.json"]),
        "projectionManifestSha256": digest(payload["projection_manifest.json"]),
        "inventory": [
            {"path": p, "bytes": len(b), "sha256": digest(b)} for p, b in sorted(payload.items())
        ],
        "sourceAndInputsFresh": True,
        "geometryReevaluated": False,
        "activePointerUpdated": False,
        "scientificQualification": False,
    }
    manifest["publicationDigest"] = digest(canonical(manifest))
    require(not scan_evidence_text(canonical(manifest).decode()), "unsafe_publication_manifest")
    with (output / "publication_manifest.json").open("xb") as stream:
        stream.write(canonical(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outfit", type=Path, default=FORGE / ".tmp/outfit-final-v1")
    parser.add_argument("--runtime", type=Path, default=FORGE / ".tmp/runtime-v3-final")
    parser.add_argument("--static", type=Path, default=Path("E:/apps/closy-static-v3-02"))
    parser.add_argument("--prior-static", type=Path, default=FORGE / ".tmp/static-family-v3-01")
    parser.add_argument("--demo", type=Path, default=FORGE / ".tmp/demo-final-v1")
    parser.add_argument("--binding", type=Path, default=FORGE / ".tmp/binding-final-v2")
    parser.add_argument(
        "--blueprint", type=Path, default=FORGE / "docs/evidence/family_integration_v1"
    )
    parser.add_argument("--family-root", type=Path, default=FORGE / ".tmp/family-final-v2")
    parser.add_argument(
        "--output", type=Path, default=FORGE / "docs/evidence/outfit_layer_runtime_v1"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-expected", type=Path)
    mode.add_argument("--expected", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--host-memory",
        type=Path,
        help="Explicit finalized receipt for this attempt; historical memory belongs in --probe",
    )
    parser.add_argument(
        "--probe",
        type=Path,
        action="append",
        default=[],
        help="Additional saved probe receipt; repeat for multiple files",
    )
    args = parser.parse_args()
    roots = {s: getattr(args, s).absolute() for s in ROOT_FILES}
    roots.update({f"probe-{i}": path.absolute() for i, path in enumerate(args.probe)})
    if args.host_memory is not None:
        require(args.host_memory.is_file(), "explicit_host_memory_missing")
        roots["probe-host-memory"] = args.host_memory.absolute()
    if args.capture_expected:
        snapshot = capture_expected(roots, FORGE)
        path = guarded(args.capture_expected.parent, args.capture_expected.name)
        require(
            not any(path.resolve().is_relative_to(r.resolve()) for r in roots.values()),
            "snapshot_inside_input",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(canonical(snapshot))
        print(f"Expected snapshot SHA-256: {digest(canonical(snapshot))}")
    else:
        require(bool(args.expected_sha256), "expected_sha256_required")
        expected = decode(Reader({}).file(args.expected.parent, args.expected.name).read_bytes())
        manifest = publish(
            roots,
            forge=FORGE,
            family_root=args.family_root,
            output=args.output,
            expected=expected,
            expected_hash=args.expected_sha256,
        )
        print(f"Saved-artifact publication: {manifest['publicationDigest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
