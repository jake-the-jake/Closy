from __future__ import annotations

import math
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file

DIAGNOSTICS_VERSION = "closy.ci_sanitized_diagnostics.v1"
MAX_INPUT_FILE_BYTES = 1_000_000
MAX_SCANNED_FILES = 2_000
MAX_OUTPUT_FILES = 4
MAX_OUTPUT_TOTAL_BYTES = 200_000

FIXED_OUTPUT_FILES = (
    "summary.json",
    "package_inventory.json",
    "validation_summary.json",
    "rejections.json",
)

FORBIDDEN_SUFFIXES = {
    ".avif",
    ".bin",
    ".bmp",
    ".closygarment",
    ".gif",
    ".glb",
    ".gltf",
    ".heic",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".obj",
    ".pdf",
    ".png",
    ".tiff",
    ".webp",
    ".zip",
}

FORBIDDEN_MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "gif": b"GIF8",
    "glb": b"glTF",
    "zip": b"PK\x03\x04",
    "pdf": b"%PDF",
}

IDENTITY_NAME_RE = re.compile(
    r"(?i)(@|passport|license|licence|driver|face|selfie|profile|private|secret|token)"
)
ABSOLUTE_PATH_RE = re.compile(r"([A-Za-z]:\\[^\"'\s]+|/(?:home|Users|tmp|var|private)/[^\"'\s]+)")
HIGH_ENTROPY_RE = re.compile(r"[A-Za-z0-9_+/=-]{32,}")
BASE64_CAPTURE_RE = re.compile(r"(data:image/|iVBORw0KGgo|/9j/|R0lGOD|Z2xURg)")


@dataclass(frozen=True)
class Rejection:
    code: str
    extension: str


def export_sanitized_ci_diagnostics(
    source_dir: Path,
    output_dir: Path,
    *,
    label: str = "forge",
    force: bool = False,
) -> dict[str, Any]:
    source = source_dir.resolve()
    output = output_dir.resolve()
    _prepare_output_dir(source, output, force=force)

    scan = _scan_source(source)
    package_dirs = [path for path in sorted(source.glob("*.closygarment")) if path.is_dir()]
    packages = [_package_summary(path) for path in package_dirs]
    validations = [_validation_summary(path) for path in package_dirs]
    validations = [validation for validation in validations if validation is not None]

    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "diagnosticsVersion": DIAGNOSTICS_VERSION,
        "label": _safe_text(label),
        "sourceDirectoryLabel": "ci-source",
        "scannedFileCount": scan["scannedFileCount"],
        "rejectedInputCount": scan["rejectedInputCount"],
        "packageCandidateCount": len(packages),
        "validationSummaryCount": len(validations),
        "outputPolicy": {
            "mode": "strict_allowlist_generated_summaries_only",
            "copiesSourceBytes": False,
            "allowsPackages": False,
            "allowsImages": False,
            "allowsGlbOrBinaryPayloads": False,
            "allowsAbsolutePaths": False,
            "maxOutputFiles": MAX_OUTPUT_FILES,
            "maxOutputTotalBytes": MAX_OUTPUT_TOTAL_BYTES,
        },
    }
    rejections = {
        "schemaVersion": 1,
        "diagnosticsVersion": DIAGNOSTICS_VERSION,
        "countsByCode": dict(sorted(scan["countsByCode"].items())),
        "countsByExtension": dict(sorted(scan["countsByExtension"].items())),
    }

    write_canonical_json(output / "summary.json", summary)
    write_canonical_json(
        output / "package_inventory.json",
        {"packages": packages, "schemaVersion": 1},
    )
    write_canonical_json(
        output / "validation_summary.json",
        {"schemaVersion": 1, "validations": validations},
    )
    write_canonical_json(output / "rejections.json", rejections)
    _assert_output_allowlist(output)
    return summary


def _prepare_output_dir(source: Path, output: Path, *, force: bool) -> None:
    if output == source or _is_relative_to(output, source):
        raise ValueError("diagnostics output must not be inside the raw source directory")
    if output.exists():
        if not force:
            raise FileExistsError(f"{output} already exists; pass --force")
        if output.is_symlink() or not output.is_dir():
            raise ValueError("diagnostics output must be a real directory")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def _scan_source(source: Path) -> dict[str, Any]:
    if not source.exists():
        return {
            "scannedFileCount": 0,
            "rejectedInputCount": 0,
            "countsByCode": Counter(),
            "countsByExtension": Counter(),
        }
    counts_by_code: Counter[str] = Counter()
    counts_by_extension: Counter[str] = Counter()
    scanned = 0
    for path in sorted(source.rglob("*")):
        if scanned >= MAX_SCANNED_FILES:
            counts_by_code["scan_file_limit_reached"] += 1
            break
        if path.is_dir():
            continue
        scanned += 1
        rejection = _classify_input(path, source)
        if rejection is not None:
            counts_by_code[rejection.code] += 1
            counts_by_extension[rejection.extension] += 1
    return {
        "scannedFileCount": scanned,
        "rejectedInputCount": sum(counts_by_code.values()),
        "countsByCode": counts_by_code,
        "countsByExtension": counts_by_extension,
    }


def _classify_input(path: Path, source: Path) -> Rejection | None:
    suffix = path.suffix.lower() or "<none>"
    try:
        relative = path.relative_to(source)
    except ValueError:
        return Rejection("path_traversal", suffix)
    if path.is_symlink():
        return Rejection("symlink_rejected", suffix)
    if any(part in {"..", ""} for part in relative.parts):
        return Rejection("path_traversal", suffix)
    if IDENTITY_NAME_RE.search(str(relative).replace("\\", "/")):
        return Rejection("identity_bearing_name_rejected", suffix)
    stat = path.stat()
    if stat.st_nlink > 1:
        return Rejection("hardlink_rejected", suffix)
    if stat.st_size > MAX_INPUT_FILE_BYTES:
        return Rejection("file_too_large", suffix)
    if suffix in FORBIDDEN_SUFFIXES:
        return Rejection("forbidden_extension_rejected", suffix)
    head = path.read_bytes()[:4096]
    if any(head.startswith(magic) for magic in FORBIDDEN_MAGIC.values()):
        return Rejection("forbidden_magic_bytes_rejected", suffix)
    if b"\x00" in head:
        return Rejection("binary_payload_rejected", suffix)
    text = _read_text_sample(path)
    if text is None:
        return Rejection("non_text_payload_rejected", suffix)
    if BASE64_CAPTURE_RE.search(text):
        return Rejection("embedded_capture_payload_rejected", suffix)
    if _contains_high_entropy_secret(text):
        return Rejection("secret_like_text_rejected", suffix)
    if ABSOLUTE_PATH_RE.search(text):
        return Rejection("absolute_path_text_rejected", suffix)
    return None


def _package_summary(package_dir: Path) -> dict[str, Any]:
    manifest = _safe_json(package_dir / "manifest.json")
    inventory = manifest.get("inventory", []) if isinstance(manifest, dict) else []
    inventory_entries = [
        {
            "path": _safe_package_path(str(entry.get("path", ""))),
            "role": _safe_text(str(entry.get("role", ""))),
            "sha256": _safe_sha(str(entry.get("sha256", ""))),
            "canonical": bool(entry.get("canonical", False)),
        }
        for entry in inventory
        if isinstance(entry, dict)
    ]
    return {
        "packageLabel": _safe_text(package_dir.name),
        "canonicalPackageDigest": _safe_sha(str(manifest.get("canonicalPackageDigest", ""))),
        "garmentId": _safe_text(str(manifest.get("garmentId", ""))),
        "schemaVersion": manifest.get("schemaVersion") if isinstance(manifest, dict) else None,
        "inventoryCount": len(inventory_entries),
        "inventory": inventory_entries,
        "manifestSha256": sha256_file(package_dir / "manifest.json")
        if (package_dir / "manifest.json").is_file()
        else None,
    }


def _validation_summary(package_dir: Path) -> dict[str, Any] | None:
    validation_path = package_dir / "reports" / "package_validation.json"
    if not validation_path.is_file():
        return None
    validation = _safe_json(validation_path)
    issues = validation.get("issues", []) if isinstance(validation, dict) else []
    return {
        "packageLabel": _safe_text(package_dir.name),
        "status": _safe_text(str(validation.get("status", ""))),
        "counts": validation.get("counts", {}),
        "issueCodes": sorted(
            {
                _safe_text(str(issue.get("code", "")))
                for issue in issues
                if isinstance(issue, dict) and issue.get("code")
            }
        ),
        "issueSeverities": sorted(
            {
                _safe_text(str(issue.get("severity", "")))
                for issue in issues
                if isinstance(issue, dict) and issue.get("severity")
            }
        ),
        "validationSha256": sha256_file(validation_path),
    }


def _assert_output_allowlist(output: Path) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file())
    relative_names = [path.relative_to(output).as_posix() for path in files]
    if relative_names != sorted(FIXED_OUTPUT_FILES):
        raise ValueError(f"diagnostics output contains non-allowlisted files: {relative_names}")
    total_bytes = 0
    for path in files:
        if path.is_symlink():
            raise ValueError("diagnostics output must not contain symlinks")
        total_bytes += path.stat().st_size
        payload = path.read_bytes()
        if any(payload.startswith(magic) for magic in FORBIDDEN_MAGIC.values()):
            raise ValueError("diagnostics output contains forbidden binary magic")
        text = payload.decode("utf-8")
        if ABSOLUTE_PATH_RE.search(text):
            raise ValueError("diagnostics output contains an absolute path")
        if BASE64_CAPTURE_RE.search(text):
            raise ValueError("diagnostics output contains embedded capture payload")
        if _contains_high_entropy_secret(text):
            raise ValueError("diagnostics output contains secret-like text")
    if total_bytes > MAX_OUTPUT_TOTAL_BYTES:
        raise ValueError("diagnostics output exceeds total size budget")


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or _classify_input(path, path.parent.parent) is not None:
        return {}
    value = read_json(path)
    return value if isinstance(value, dict) else {}


def _safe_package_path(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("/")
    if ".." in normalized.split("/"):
        return "[redacted-path]"
    return _safe_text(normalized)


def _safe_text(value: str) -> str:
    text = ABSOLUTE_PATH_RE.sub("[redacted-path]", value)
    text = HIGH_ENTROPY_RE.sub("[redacted-token]", text)
    text = BASE64_CAPTURE_RE.sub("[redacted-capture-payload]", text)
    text = IDENTITY_NAME_RE.sub("[redacted-name]", text)
    return text[:500]


def _safe_sha(value: str) -> str:
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def _read_text_sample(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")[:8192]
    except UnicodeDecodeError:
        return None


def _contains_high_entropy_secret(text: str) -> bool:
    for match in HIGH_ENTROPY_RE.finditer(text):
        token = match.group(0)
        if len(token) >= 48 and _shannon_entropy(token) > 4.2:
            return True
    return False


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
