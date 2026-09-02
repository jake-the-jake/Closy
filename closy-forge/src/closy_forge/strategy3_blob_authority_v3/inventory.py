from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from collections import deque
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from .common import canonical_bytes
from .git_blobs import GitBlobReader, validate_path_set

SCIENTIFIC_PREFIX = "closy-forge/"
EXECUTION_PREFIXES = (
    "closy-forge/src/closy_forge/contracts",
    "closy-forge/src/closy_forge/final_strategy3_v2",
    "closy-forge/src/closy_forge/geometry",
    "closy-forge/src/closy_forge/package_io",
    "closy-forge/src/closy_forge/simulation",
)
SCIENTIFIC_SINGLE_PATHS = (
    "closy-forge/src/closy_forge/__init__.py",
    "closy-forge/src/closy_forge/recovery_foundation_v2/__init__.py",
    "closy-forge/src/closy_forge/recovery_foundation_v2/topology_holdout.py",
    "closy-forge/src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py",
    "closy-forge/fixtures/final_strategy3_v2/final_implementation_lock.json",
    "closy-forge/fixtures/final_strategy3_v2/strategy_design_reservation.json",
    "closy-forge/docs/evidence/final_strategy3_v2/public_conformance.json",
    "closy-forge/docs/evidence/phy1_topology_strategy3_diagnosis_v1/starting_authority.json",
)
WRAPPER_PREFIX = "closy-forge/src/closy_forge/strategy3_blob_authority_v3"
WRAPPER_PATHS = (
    ".github/workflows/forge-unit-y1-strategy3-blob-authority-v3.yml",
    "closy-forge/docker/strategy3_blob_authority_v3/Dockerfile",
    "closy-forge/docker/strategy3_blob_authority_v3/Dockerfile.dockerignore",
    "closy-forge/docker/strategy3_blob_authority_v3/entrypoint.sh",
    "closy-forge/docker/strategy3_blob_authority_v3/isolation_canary.py",
    "closy-forge/docker/strategy3_blob_authority_v3/runner.py",
    "closy-forge/scripts/build_strategy3_blob_lock_v3.py",
    "closy-forge/scripts/materialize_strategy3_blob_context_v3.py",
    "closy-forge/scripts/run_strategy3_blob_authority_v3.py",
    "closy-forge/scripts/run_strategy3_blob_preflight_v3.py",
    "closy-forge/scripts/verify_strategy3_blob_artifacts_v3.py",
    "closy-forge/tests/corruption/test_strategy3_blob_authority_v3_corruption.py",
    "closy-forge/tests/unit/test_strategy3_blob_authority_v3.py",
    "closy-forge/schemas/v1/strategy3-blob-lock-v3.schema.json",
    "closy-forge/schemas/v1/strategy3-blob-preflight-v3.schema.json",
    "closy-forge/schemas/v1/strategy3-blob-result-v3.schema.json",
    "closy-forge/pyproject.toml",
    "closy-forge/requirements-dev.lock",
)
CONTAINER_WRAPPER_PATHS = frozenset(
    {
        "closy-forge/docker/strategy3_blob_authority_v3/Dockerfile",
        "closy-forge/docker/strategy3_blob_authority_v3/Dockerfile.dockerignore",
        "closy-forge/docker/strategy3_blob_authority_v3/entrypoint.sh",
        "closy-forge/docker/strategy3_blob_authority_v3/isolation_canary.py",
        "closy-forge/docker/strategy3_blob_authority_v3/runner.py",
    }
)
BASE_IMAGE_PATTERN = re.compile(r"^FROM\s+[^@\s]+@sha256:([0-9a-f]{64})\s*$", re.MULTILINE)
ACTION_PATTERN = re.compile(r"uses:\s*([^\s@]+)@([0-9a-f]{40})")


def build_inventory(
    reader: GitBlobReader, *, scientific_commit: str, wrapper_commit: str
) -> dict[str, Any]:
    scientific = reader.resolve_commit(scientific_commit)
    wrapper = reader.resolve_commit(wrapper_commit)
    scientific_paths: set[str] = set(SCIENTIFIC_SINGLE_PATHS)
    for prefix in EXECUTION_PREFIXES:
        scientific_paths.update(reader.list_paths(scientific, prefix))
    scientific_paths.update(_python_import_closure(reader, scientific, scientific_paths))
    wrapper_paths = set(reader.list_paths(wrapper, WRAPPER_PREFIX))
    wrapper_paths.update(WRAPPER_PATHS)
    all_paths = sorted(scientific_paths | wrapper_paths)
    validate_path_set(all_paths)
    duplicates = sorted(scientific_paths & wrapper_paths)
    if duplicates:
        raise ValueError(f"strategy3_v3_cross_anchor_duplicate:{duplicates}")
    rows: list[dict[str, Any]] = []
    for ordinal, path in enumerate(all_paths):
        source = scientific if path in scientific_paths else wrapper
        identity = reader.identity(source, path)
        role = _role(path, source == scientific)
        execution_image = path in scientific_paths and _is_execution_path(path)
        if path in CONTAINER_WRAPPER_PATHS:
            execution_image = True
        rows.append(
            {
                "ordinal": ordinal,
                "repository": "jake-the-jake/Closy",
                "commit": identity.commit,
                "rootTreeObjectId": identity.root_tree_object_id,
                "repositoryPath": identity.repository_path,
                "materializedPath": path.removeprefix(SCIENTIFIC_PREFIX),
                "gitMode": identity.git_mode,
                "objectType": identity.object_type,
                "rawBlobOid": identity.blob_oid,
                "rawBlobSha256": identity.sha256,
                "rawBlobByteLength": identity.byte_length,
                "declaredRole": role,
                "entersExecutionImage": execution_image,
            }
        )
    dockerfile = reader.blob_at(
        wrapper, "closy-forge/docker/strategy3_blob_authority_v3/Dockerfile"
    ).decode("utf-8")
    workflow = reader.blob_at(
        wrapper, ".github/workflows/forge-unit-y1-strategy3-blob-authority-v3.yml"
    ).decode("utf-8")
    base_match = BASE_IMAGE_PATTERN.search(dockerfile)
    if base_match is None:
        raise ValueError("strategy3_v3_base_image_not_digest_pinned")
    actions = sorted(
        (
            {"action": action, "commit": commit}
            for action, commit in ACTION_PATTERN.findall(workflow)
        ),
        key=lambda row: (row["action"], row["commit"]),
    )
    if not actions:
        raise ValueError("strategy3_v3_workflow_action_inventory_empty")
    _validate_import_coverage(reader, scientific, rows)
    document = {
        "inventoryVersion": "closy.strategy3.repository_blob_inventory.v3",
        "repository": "jake-the-jake/Closy",
        "scientificSourceCommit": scientific,
        "scientificSourceTree": reader.root_tree(scientific),
        "authorityWrapperSourceCommit": wrapper,
        "authorityWrapperSourceTree": reader.root_tree(wrapper),
        "baseImageDigest": f"sha256:{base_match.group(1)}",
        "actions": actions,
        "blobCount": len(rows),
        "executionImageBlobCount": sum(row["entersExecutionImage"] for row in rows),
        "rows": rows,
        "inventoryDigest": "",
    }
    document["inventoryDigest"] = _digest_without(document, "inventoryDigest")
    return document


def _python_import_closure(
    reader: GitBlobReader, commit: str, initial_paths: Iterable[str]
) -> set[str]:
    discovered = {path for path in initial_paths if path.endswith(".py")}
    pending = deque(sorted(discovered))
    while pending:
        path = pending.popleft()
        for module in _imports(reader.blob_at(commit, path), path):
            candidate = _module_path(module)
            package = candidate.removesuffix(".py") + "/__init__.py"
            resolved = None
            for option in (candidate, package):
                try:
                    reader.identity(commit, option)
                except (subprocess.CalledProcessError, ValueError):
                    continue
                resolved = option
                break
            if resolved is not None and resolved not in discovered:
                discovered.add(resolved)
                pending.append(resolved)
    return discovered


def _imports(payload: bytes, source_path: str) -> set[str]:
    tree = ast.parse(payload.decode("utf-8"), filename=source_path)
    package = PurePosixPath(source_path).parent.parts
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(
                alias.name for alias in node.names if alias.name.startswith("closy_forge")
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package[2:])
                trim = max(node.level - 1, 0)
                if trim:
                    base = base[:-trim]
                name = ".".join(["closy_forge", *base[1:], node.module or ""]).strip(".")
            else:
                name = node.module or ""
            if name.startswith("closy_forge"):
                modules.add(name)
    return modules


def _module_path(module: str) -> str:
    return f"closy-forge/src/{module.replace('.', '/')}.py"


def _validate_import_coverage(
    reader: GitBlobReader, scientific_commit: str, rows: list[dict[str, Any]]
) -> None:
    declared = {str(row["repositoryPath"]) for row in rows}
    for row in rows:
        path = str(row["repositoryPath"])
        if row["commit"] != scientific_commit or not path.endswith(".py"):
            continue
        for module in _imports(reader.blob_at(scientific_commit, path), path):
            options = {
                _module_path(module),
                _module_path(module).removesuffix(".py") + "/__init__.py",
            }
            if not options & declared:
                raise ValueError(f"strategy3_v3_import_not_locked:{path}:{module}")


def _is_execution_path(path: str) -> bool:
    return path.startswith(tuple(f"{prefix}/" for prefix in EXECUTION_PREFIXES)) or path in {
        "closy-forge/src/closy_forge/__init__.py",
        "closy-forge/src/closy_forge/recovery_foundation_v2/__init__.py",
        "closy-forge/src/closy_forge/recovery_foundation_v2/topology_holdout.py",
        "closy-forge/src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py",
    }


def _role(path: str, scientific: bool) -> str:
    if scientific:
        if "topology_holdout_oracle" in path:
            return "oracle"
        if "topology_holdout" in path:
            return "generator"
        if "/final_strategy3_v2/" in path or "/simulation/" in path:
            return "contestant_or_evaluator"
        if path.endswith(".json"):
            return "frozen_protocol_or_evidence"
        return "transitive_scientific_dependency"
    if path.startswith(".github/workflows/"):
        return "workflow"
    if "/docker/" in path:
        return "packaging_or_isolation"
    if "/schemas/" in path:
        return "schema"
    if "/tests/" in path:
        return "authority_test"
    return "authority_wrapper"


def _digest_without(document: Mapping[str, Any], field: str) -> str:
    return hashlib.sha256(canonical_bytes({**dict(document), field: ""})).hexdigest()
