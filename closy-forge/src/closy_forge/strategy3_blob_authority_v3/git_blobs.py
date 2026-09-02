from __future__ import annotations

import hashlib
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

FULL_SHA1 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class BlobIdentity:
    repository_path: str
    commit: str
    root_tree_object_id: str
    git_mode: str
    object_type: str
    blob_oid: str
    sha256: str
    byte_length: int


class GitBlobReader:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self._assert_unambiguous_repository()

    def resolve_commit(self, revision: str) -> str:
        commit = self.text("rev-parse", f"{revision}^{{commit}}")
        if not FULL_SHA1.fullmatch(commit):
            raise ValueError("strategy3_v3_commit_identity_invalid")
        return commit

    def root_tree(self, commit: str) -> str:
        tree = self.text("rev-parse", f"{commit}^{{tree}}")
        if not FULL_SHA1.fullmatch(tree):
            raise ValueError("strategy3_v3_tree_identity_invalid")
        return tree

    def identity(self, commit: str, repository_path: str) -> BlobIdentity:
        normalized = normalize_repository_path(repository_path)
        raw = self.raw("ls-tree", "-z", commit, "--", normalized)
        rows = [row for row in raw.split(b"\0") if row]
        if len(rows) != 1:
            raise ValueError(f"strategy3_v3_blob_missing_or_ambiguous:{normalized}")
        metadata, actual_raw = rows[0].split(b"\t", 1)
        mode, object_type, oid = metadata.decode("ascii").split(" ", 2)
        actual = actual_raw.decode("utf-8")
        if actual != normalized:
            raise ValueError(f"strategy3_v3_path_alias:{normalized}")
        if object_type != "blob" or mode in {"120000", "160000"}:
            raise ValueError(f"strategy3_v3_non_regular_blob:{normalized}")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"strategy3_v3_mode_unsupported:{normalized}:{mode}")
        payload = self.blob(oid)
        if git_blob_oid(payload) != oid:
            raise ValueError(f"strategy3_v3_blob_oid_recompute_failed:{normalized}")
        return BlobIdentity(
            repository_path=normalized,
            commit=commit,
            root_tree_object_id=self.root_tree(commit),
            git_mode=mode,
            object_type=object_type,
            blob_oid=oid,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_length=len(payload),
        )

    def list_paths(self, commit: str, prefix: str) -> list[str]:
        normalized = normalize_repository_path(prefix)
        raw = self.raw("ls-tree", "-r", "-z", "--name-only", commit, "--", normalized)
        paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
        validate_path_set(paths)
        return sorted(paths)

    def blob(self, oid: str) -> bytes:
        if not FULL_SHA1.fullmatch(oid):
            raise ValueError("strategy3_v3_blob_oid_invalid")
        return self.raw("cat-file", "blob", oid)

    def blob_at(self, commit: str, repository_path: str) -> bytes:
        return self.blob(self.identity(commit, repository_path).blob_oid)

    def raw(self, *args: str, input_bytes: bytes | None = None) -> bytes:
        environment = {
            **os.environ,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            env=environment,
            input=input_bytes,
            check=True,
            capture_output=True,
        ).stdout

    def text(self, *args: str) -> str:
        return self.raw(*args).decode("utf-8").strip()

    def _assert_unambiguous_repository(self) -> None:
        if self.text("replace", "-l"):
            raise ValueError("strategy3_v3_replace_refs_forbidden")
        grafts = Path(self.text("rev-parse", "--git-path", "info/grafts"))
        if not grafts.is_absolute():
            grafts = self.repo_root / grafts
        if grafts.is_file() and grafts.stat().st_size:
            raise ValueError("strategy3_v3_grafts_forbidden")
        object_format = self.text("rev-parse", "--show-object-format")
        if object_format != "sha1":
            raise ValueError(f"strategy3_v3_object_format_unsupported:{object_format}")


def normalize_repository_path(value: str) -> str:
    if not value or "\\" in value or "\0" in value:
        raise ValueError(f"strategy3_v3_repository_path_invalid:{value}")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"strategy3_v3_repository_path_not_nfc:{value}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"strategy3_v3_repository_path_unsafe:{value}")
    return value


def validate_path_set(paths: list[str]) -> None:
    normalized = [normalize_repository_path(path) for path in paths]
    if len(normalized) != len(set(normalized)):
        raise ValueError("strategy3_v3_duplicate_repository_path")
    folded: dict[str, str] = {}
    for path in normalized:
        key = unicodedata.normalize("NFC", path).casefold()
        previous = folded.setdefault(key, path)
        if previous != path:
            raise ValueError(f"strategy3_v3_case_or_unicode_collision:{previous}:{path}")


def git_blob_oid(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()
