from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from closy_forge.package_io.hashing import sha256_bytes

IMAGE_REFERENCE = (
    "python:3.11.11-slim-bookworm@"
    "sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5"
)
CONTAINER_UID = 65532
CONTAINER_GID = 65532
ALLOWED_OUTPUTS = frozenset({"probe.json", "prediction.json", "lineage.json"})
ALLOWED_ENVIRONMENT = frozenset({"LANG", "LC_ALL", "PATH", "PYTHONHASHSEED", "ROUTE_ID"})


def build_docker_run_command(
    input_directory: Path,
    output_directory: Path,
    *,
    route_id: str,
    image_reference: str = IMAGE_REFERENCE,
) -> list[str]:
    input_path = str(input_directory.resolve())
    output_path = str(output_directory.resolve())
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "64",
        "--cpus",
        "1.0",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--user",
        f"{CONTAINER_UID}:{CONTAINER_GID}",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "LC_ALL=C.UTF-8",
        "--env",
        "PYTHONHASHSEED=0",
        "--env",
        f"ROUTE_ID={route_id}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
        "--mount",
        f"type=bind,src={input_path},dst=/inputs,readonly",
        "--mount",
        f"type=bind,src={output_path},dst=/outputs",
        image_reference,
    ]


def windows_mount_render(path: PureWindowsPath) -> str:
    value = str(path)
    if not path.is_absolute() or not path.drive:
        raise ValueError("container_windows_mount_must_be_absolute")
    if any(part == ".." for part in path.parts):
        raise ValueError("container_windows_mount_traversal")
    return value


def validate_command(
    command: Sequence[str], *, expected_image_reference: str = IMAGE_REFERENCE
) -> list[str]:
    issues: list[str] = []
    joined = "\n".join(command)
    required_fragments = (
        "--network\nnone",
        "--read-only",
        "--cap-drop\nALL",
        "no-new-privileges:true",
        "--pids-limit\n64",
        "--cpus\n1.0",
        "--memory\n256m",
        f"--user\n{CONTAINER_UID}:{CONTAINER_GID}",
        "/inputs,readonly",
        "/outputs",
        "PYTHONHASHSEED=0",
        expected_image_reference,
    )
    for fragment in required_fragments:
        if fragment not in joined:
            issues.append(f"container_command_control_missing:{fragment.splitlines()[0]}")
    forbidden = ("docker.sock", ".git", "evaluator", "target", "credential", "HOME=")
    for token in forbidden:
        if token.lower() in joined.lower():
            issues.append(f"container_command_forbidden_mount_or_value:{token}")
    return sorted(set(issues))


def collect_outputs(
    output_directory: Path,
    *,
    allowed_names: frozenset[str] = ALLOWED_OUTPUTS,
    maximum_files: int = 8,
    maximum_file_bytes: int = 1_000_000,
    maximum_total_bytes: int = 2_000_000,
) -> list[dict[str, Any]]:
    root = output_directory.resolve()
    if not root.is_dir():
        raise ValueError("container_output_root_missing")
    records: list[dict[str, Any]] = []
    total = 0
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        relative = entry.relative_to(root)
        if len(relative.parts) != 1 or entry.name not in allowed_names:
            raise ValueError(f"container_output_name_or_depth_forbidden:{relative.as_posix()}")
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"container_output_symlink_forbidden:{entry.name}")
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"container_output_type_forbidden:{entry.name}")
        if metadata.st_nlink != 1:
            raise ValueError(f"container_output_hardlink_forbidden:{entry.name}")
        if metadata.st_size > maximum_file_bytes:
            raise ValueError(f"container_output_file_too_large:{entry.name}")
        total += metadata.st_size
        if total > maximum_total_bytes:
            raise ValueError("container_output_aggregate_too_large")
        descriptor = os.open(entry, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            data = b""
            while len(data) <= maximum_file_bytes:
                block = os.read(descriptor, min(65536, maximum_file_bytes + 1 - len(data)))
                if not block:
                    break
                data += block
        finally:
            os.close(descriptor)
        if len(data) != metadata.st_size:
            raise ValueError(f"container_output_changed_during_collection:{entry.name}")
        records.append(
            {
                "path": entry.name,
                "byteLength": len(data),
                "sha256": sha256_bytes(data),
            }
        )
        if len(records) > maximum_files:
            raise ValueError("container_output_file_count_exceeded")
    return records


def validate_environment(environment: Mapping[str, str]) -> list[str]:
    return sorted(key for key in environment if key not in ALLOWED_ENVIRONMENT)


def cap_diagnostic(data: bytes, *, maximum_bytes: int = 16_384) -> dict[str, Any]:
    clipped = data[:maximum_bytes]
    return {
        "capturedByteLength": len(clipped),
        "originalByteLength": len(data),
        "truncated": len(data) > maximum_bytes,
        "sha256": sha256_bytes(clipped),
    }


def build_container_capability() -> dict[str, Any]:
    command = build_docker_run_command(
        Path("C:/closy-canary-input"),
        Path("C:/closy-canary-output"),
        route_id="generic_canary",
    )
    return {
        "schemaVersion": 1,
        "boundaryVersion": "closy.d0_v3.container_boundary.v1",
        "imageReference": IMAGE_REFERENCE,
        "uid": CONTAINER_UID,
        "gid": CONTAINER_GID,
        "replicationRule": {"required": 3, "passed": 0, "officialPreflightRun": None},
        "rootReadOnly": True,
        "inputsReadOnly": True,
        "outputsWritable": True,
        "networkDisabled": True,
        "capabilitiesDropped": True,
        "noNewPrivileges": True,
        "boundedResources": True,
        "repositoryMounted": False,
        "evaluatorMounted": False,
        "dockerSocketMounted": False,
        "hostHomeMounted": False,
        "environmentAllowlist": sorted(ALLOWED_ENVIRONMENT),
        "outputAllowlist": sorted(ALLOWED_OUTPUTS),
        "commandValidationIssues": validate_command(command),
        "windowsPathConstructionTested": True,
        "windowsDockerIsolationClaimed": False,
        "officialSeedCreated": False,
    }
