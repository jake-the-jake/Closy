from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .common import canonical_bytes, records
from .git_blobs import GitBlobReader, git_blob_oid, normalize_repository_path


@contextmanager
def materialized_context(
    repo_root: Path, lock: Mapping[str, Any]
) -> Iterator[tuple[Path, dict[str, Any]]]:
    validate_materialization_rows(lock)
    reader = GitBlobReader(repo_root)
    with tempfile.TemporaryDirectory(prefix="closy-strategy3-v3-blobs-") as temporary:
        root = Path(temporary) / "context"
        root.mkdir()
        manifest_rows: list[dict[str, Any]] = []
        for row in records(lock.get("blobs")):
            if row.get("entersExecutionImage") is not True:
                continue
            path = normalize_repository_path(str(row["materializedPath"]))
            target = root.joinpath(*_parts(path))
            _mkdir_parents_no_links(root, target.parent)
            payload = reader.blob(str(row["rawBlobOid"]))
            _verify_payload(row, payload)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, 0o600)
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_size != len(payload):
                    raise ValueError(f"strategy3_v3_staged_file_invalid:{path}")
            finally:
                os.close(descriptor)
            mode = 0o755 if row["gitMode"] == "100755" else 0o644
            target.chmod(mode)
            os.utime(target, (0, 0), follow_symlinks=False)
            staged = target.read_bytes()
            _verify_payload(row, staged)
            manifest_rows.append(
                {
                    "ordinal": len(manifest_rows),
                    "path": path,
                    "gitMode": row["gitMode"],
                    "rawBlobOid": row["rawBlobOid"],
                    "sha256": row["rawBlobSha256"],
                    "byteLength": row["rawBlobByteLength"],
                }
            )
        actual_files = sorted(
            path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
        )
        declared_files = sorted(str(row["path"]) for row in manifest_rows)
        if actual_files != declared_files:
            raise ValueError("strategy3_v3_materialized_allowlist_mismatch")
        manifest = {
            "manifestVersion": "closy.strategy3.materialized_build_context.v3",
            "fixedTimestampEpochSeconds": 0,
            "fileCount": len(manifest_rows),
            "rows": manifest_rows,
            "contextDigest": hashlib.sha256(canonical_bytes(manifest_rows)).hexdigest(),
        }
        yield root, manifest
        # TemporaryDirectory removes the context after verification/build use.


def build_container_image(
    repo_root: Path, lock: Mapping[str, Any], *, image_tag: str
) -> dict[str, Any]:
    with materialized_context(repo_root, lock) as (context, manifest):
        command = [
            "docker",
            "build",
            "--pull=false",
            "--network=none",
            "-f",
            "docker/strategy3_blob_authority_v3/Dockerfile",
            "-t",
            image_tag,
            ".",
        ]
        subprocess.run(command, cwd=context, check=True, timeout=300)
        image_id = subprocess.run(
            ["docker", "image", "inspect", image_tag, "--format", "{{.Id}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {**manifest, "imageTag": image_tag, "imageId": image_id}


def validate_materialization_rows(lock: Mapping[str, Any]) -> None:
    rows = records(lock.get("blobs"))
    paths = [
        str(row.get("materializedPath", "")) for row in rows if row.get("entersExecutionImage")
    ]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("strategy3_v3_materialized_path_order_invalid")
    folded: dict[str, str] = {}
    for path in paths:
        normalized = normalize_repository_path(path)
        previous = folded.setdefault(normalized.casefold(), normalized)
        if previous != normalized:
            raise ValueError("strategy3_v3_materialized_case_collision")


def _verify_payload(row: Mapping[str, Any], payload: bytes) -> None:
    if git_blob_oid(payload) != row.get("rawBlobOid"):
        raise ValueError(f"strategy3_v3_materialized_oid_mismatch:{row.get('materializedPath')}")
    if hashlib.sha256(payload).hexdigest() != row.get("rawBlobSha256"):
        raise ValueError(f"strategy3_v3_materialized_sha_mismatch:{row.get('materializedPath')}")
    if len(payload) != row.get("rawBlobByteLength"):
        raise ValueError(f"strategy3_v3_materialized_size_mismatch:{row.get('materializedPath')}")


def _mkdir_parents_no_links(root: Path, directory: Path) -> None:
    relative = directory.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise ValueError("strategy3_v3_staging_parent_invalid")
        else:
            current.mkdir(mode=0o755)


def _parts(path: str) -> tuple[str, ...]:
    return tuple(path.split("/"))
