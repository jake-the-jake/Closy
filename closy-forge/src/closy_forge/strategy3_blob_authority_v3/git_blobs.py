from __future__ import annotations

import hashlib
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

FULL_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_GLOBAL_TREE_CACHE: dict[tuple[str, str], str] = {}
_GLOBAL_BLOB_CACHE: dict[tuple[str, str], bytes] = {}
_GLOBAL_ENTRY_CACHE: dict[tuple[str, str], dict[str, tuple[str, str, str]]] = {}


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
        self._tree_cache: dict[str, str] = {}
        self._blob_cache: dict[str, bytes] = {}
        self._identity_cache: dict[tuple[str, str], BlobIdentity] = {}
        self._assert_unambiguous_repository()

    def resolve_commit(self, revision: str) -> str:
        commit = self.text("rev-parse", f"{revision}^{{commit}}")
        if not FULL_SHA1.fullmatch(commit):
            raise ValueError("strategy3_v3_commit_identity_invalid")
        return commit

    def root_tree(self, commit: str) -> str:
        cached = self._tree_cache.get(commit)
        if cached is not None:
            return cached
        global_key = (self.repo_root.as_posix(), commit)
        tree = _GLOBAL_TREE_CACHE.get(global_key)
        if tree is None:
            tree = self.text("rev-parse", f"{commit}^{{tree}}")
            _GLOBAL_TREE_CACHE[global_key] = tree
        if not FULL_SHA1.fullmatch(tree):
            raise ValueError("strategy3_v3_tree_identity_invalid")
        self._tree_cache[commit] = tree
        return tree

    def identity(self, commit: str, repository_path: str) -> BlobIdentity:
        normalized = normalize_repository_path(repository_path)
        cached = self._identity_cache.get((commit, normalized))
        if cached is not None:
            return cached
        entry = self._entries(commit).get(normalized)
        if entry is None:
            raise ValueError(f"strategy3_v3_blob_missing_or_ambiguous:{normalized}")
        mode, object_type, oid = entry
        if object_type != "blob" or mode in {"120000", "160000"}:
            raise ValueError(f"strategy3_v3_non_regular_blob:{normalized}")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"strategy3_v3_mode_unsupported:{normalized}:{mode}")
        payload = self.blob(oid)
        if git_blob_oid(payload) != oid:
            raise ValueError(f"strategy3_v3_blob_oid_recompute_failed:{normalized}")
        identity = BlobIdentity(
            repository_path=normalized,
            commit=commit,
            root_tree_object_id=self.root_tree(commit),
            git_mode=mode,
            object_type=object_type,
            blob_oid=oid,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_length=len(payload),
        )
        self._identity_cache[(commit, normalized)] = identity
        return identity

    def list_paths(self, commit: str, prefix: str) -> list[str]:
        normalized = normalize_repository_path(prefix)
        paths = [
            path
            for path in self._entries(commit)
            if path == normalized or path.startswith(f"{normalized}/")
        ]
        validate_path_set(paths)
        return sorted(paths)

    def blob(self, oid: str) -> bytes:
        if not FULL_SHA1.fullmatch(oid):
            raise ValueError("strategy3_v3_blob_oid_invalid")
        cached = self._blob_cache.get(oid)
        if cached is not None:
            return cached
        global_key = (self.repo_root.as_posix(), oid)
        payload = _GLOBAL_BLOB_CACHE.get(global_key)
        if payload is None:
            payload = self.raw("cat-file", "blob", oid)
            _GLOBAL_BLOB_CACHE[global_key] = payload
        self._blob_cache[oid] = payload
        return payload

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

    def _entries(self, commit: str) -> dict[str, tuple[str, str, str]]:
        key = (self.repo_root.as_posix(), commit)
        cached = _GLOBAL_ENTRY_CACHE.get(key)
        if cached is not None:
            return cached
        raw = self.raw("ls-tree", "-r", "-z", commit)
        entries: dict[str, tuple[str, str, str]] = {}
        for row in (item for item in raw.split(b"\0") if item):
            metadata, path_raw = row.split(b"\t", 1)
            mode, object_type, oid = metadata.decode("ascii").split(" ", 2)
            path = path_raw.decode("utf-8")
            if path in entries:
                raise ValueError(f"strategy3_v3_duplicate_tree_path:{path}")
            entries[path] = (mode, object_type, oid)
        validate_path_set(list(entries))
        _GLOBAL_ENTRY_CACHE[key] = entries
        return entries

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
