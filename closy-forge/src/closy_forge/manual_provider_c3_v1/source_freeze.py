from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .common import digest_value, read_json, validate_embedded_digest, write_json

SOURCE_PATHS = (
    "closy-forge/fixtures/manual_provider_c3_v1/protocol.json",
    "closy-forge/fixtures/manual_provider_c3_v1/raw_source_freeze.json",
    "closy-forge/scripts/author_manual_provider_c3_v1_sources.py",
)
SOURCE_GLOBS = (
    "closy-forge/src/closy_forge/manual_provider_c3_v1/*.py",
    "closy-forge/tests/unit/test_manual_provider_c3_v1*.py",
)


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()


def source_inventory(repository: Path, commit: str) -> list[dict[str, Any]]:
    paths = set(SOURCE_PATHS)
    for pattern in SOURCE_GLOBS:
        paths.update(
            _git(repository, "ls-tree", "-r", "--name-only", commit, "--", pattern).splitlines()
        )
    records = []
    for relative in sorted(path for path in paths if path):
        entry = _git(repository, "ls-tree", commit, "--", relative).split()
        if len(entry) < 3 or entry[1] != "blob":
            raise ValueError(f"source_freeze_path_not_blob:{relative}")
        blob = subprocess.check_output(["git", "cat-file", "blob", entry[2]], cwd=repository)
        records.append(
            {
                "path": relative,
                "gitMode": entry[0],
                "gitBlobOid": entry[2],
                "bytes": len(blob),
                "sha256": __import__("hashlib").sha256(blob).hexdigest(),
            }
        )
    return records


def create_source_freeze(repository: Path, output_path: Path) -> dict[str, Any]:
    commit = _git(repository, "rev-parse", "HEAD")
    forge_root = repository / "closy-forge"
    protocol = read_json(forge_root / "fixtures" / "manual_provider_c3_v1" / "protocol.json")
    validate_embedded_digest(protocol, "protocolDigest")
    raw_freeze = read_json(
        forge_root / "fixtures" / "manual_provider_c3_v1" / "raw_source_freeze.json"
    )
    validate_embedded_digest(raw_freeze, "freezeDigest")
    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "sourceFreezeVersion": "closy.manual_provider_c3_v1.source_freeze.v1",
        "sourceCommit": commit,
        "sourceTree": _git(repository, "rev-parse", f"{commit}^{{tree}}"),
        "protocolDigest": protocol["protocolDigest"],
        "rawSourceFreezeDigest": raw_freeze["freezeDigest"],
        "sourceFiles": source_inventory(repository, commit),
        "sourceFileCount": 0,
        "policy": {
            "postFreezeImplementationChangesForbidden": True,
            "exactlyOneFinalBenchmarkRun": True,
            "thresholdChangesAfterFreezeForbidden": True,
        },
    }
    freeze["sourceFileCount"] = len(freeze["sourceFiles"])
    freeze["sourceFreezeDigest"] = digest_value(freeze)
    write_json(output_path, freeze)
    return freeze


def verify_source_freeze(repository: Path, freeze: dict[str, Any]) -> None:
    validate_embedded_digest(freeze, "sourceFreezeDigest")
    if _git(repository, "rev-parse", f"{freeze['sourceCommit']}^{{tree}}") != freeze["sourceTree"]:
        raise ValueError("source_tree_identity_mismatch")
    expected = source_inventory(repository, str(freeze["sourceCommit"]))
    if expected != freeze["sourceFiles"] or len(expected) != freeze["sourceFileCount"]:
        raise ValueError("source_file_inventory_mismatch")
    for record in expected:
        current_entry = _git(repository, "ls-tree", "HEAD", "--", record["path"]).split()
        if len(current_entry) < 3 or current_entry[2] != record["gitBlobOid"]:
            raise ValueError(f"post_freeze_source_drift:{record['path']}")
