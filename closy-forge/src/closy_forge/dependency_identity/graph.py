from __future__ import annotations

from collections import deque
from typing import Any, Literal, TypedDict

DEPENDENCY_GRAPH_VERSION = "closy.dependency_identity_graph.d0.v1"
ChangeAction = Literal["invalidate", "rebuild", "byte_identical"]


class InvalidationResult(TypedDict):
    changedNodeIds: list[str]
    invalidatedNodeIds: list[str]
    rebuildNodeIds: list[str]
    retainedByteIdenticalNodeIds: list[str]
    failClosed: bool


class DependencyGraphError(ValueError):
    pass


def validate_dependency_graph(graph: dict[str, Any]) -> None:
    """Validate one candidate's authority graph without opening restricted inputs."""

    if graph.get("schemaVersion") != 1 or graph.get("graphVersion") != DEPENDENCY_GRAPH_VERSION:
        raise DependencyGraphError("dependency_graph_version_invalid")
    candidate = graph.get("packageCandidateId")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    policy = graph.get("identityPolicy")
    if not _sha(candidate) or not isinstance(nodes, list) or not isinstance(edges, list):
        raise DependencyGraphError("dependency_graph_shape_invalid")
    if not isinstance(policy, dict):
        raise DependencyGraphError("dependency_graph_policy_missing")

    by_id: dict[str, dict[str, Any]] = {}
    authorities: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise DependencyGraphError("dependency_node_invalid")
        required = {
            "nodeId",
            "stage",
            "identity",
            "authorityId",
            "classification",
            "portable",
            "packageCandidateId",
        }
        if set(node) != required:
            raise DependencyGraphError("dependency_node_shape_invalid")
        node_id = node["nodeId"]
        authority = node["authorityId"]
        if not isinstance(node_id, str) or not node_id or node_id in by_id:
            raise DependencyGraphError("dependency_node_duplicate")
        if not isinstance(authority, str) or not authority or authority in authorities:
            raise DependencyGraphError("dependency_authority_duplicate")
        if node["packageCandidateId"] != candidate:
            raise DependencyGraphError("dependency_cross_candidate_node")
        if node["classification"] not in {
            "public_fixture",
            "private_restricted",
            "portable_opaque",
            "runtime_authority",
        }:
            raise DependencyGraphError("dependency_classification_invalid")
        if not isinstance(node["portable"], bool):
            raise DependencyGraphError("dependency_portability_invalid")
        _validate_identity(node)
        by_id[node_id] = node
        authorities.add(authority)

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    edge_keys: set[tuple[str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {
            "fromNodeId",
            "toNodeId",
            "onUpstreamIdentityChange",
            "rationale",
        }:
            raise DependencyGraphError("dependency_edge_shape_invalid")
        parent = edge["fromNodeId"]
        child = edge["toNodeId"]
        if parent not in by_id or child not in by_id:
            raise DependencyGraphError("dependency_edge_unknown_node")
        if (parent, child) in edge_keys:
            raise DependencyGraphError("dependency_edge_duplicate")
        if edge["onUpstreamIdentityChange"] not in {
            "invalidate",
            "rebuild",
            "byte_identical",
        }:
            raise DependencyGraphError("dependency_edge_action_invalid")
        if not isinstance(edge["rationale"], str) or not edge["rationale"]:
            raise DependencyGraphError("dependency_edge_rationale_missing")
        adjacency[parent].append(child)
        edge_keys.add((parent, child))
    _reject_cycles(adjacency)


def calculate_invalidation(
    graph: dict[str, Any], changed_node_ids: set[str]
) -> InvalidationResult:
    """Propagate declared consequences and stop at byte-identical edges."""

    validate_dependency_graph(graph)
    known = {str(node["nodeId"]) for node in graph["nodes"]}
    unknown = changed_node_ids - known
    if unknown:
        raise DependencyGraphError(f"dependency_changed_node_unknown:{sorted(unknown)[0]}")
    edges_by_parent: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in known}
    for edge in graph["edges"]:
        edges_by_parent[str(edge["fromNodeId"])].append(edge)

    invalidated: set[str] = set()
    rebuild: set[str] = set()
    retained: set[str] = set()
    queue = deque(sorted(changed_node_ids))
    propagated = set(changed_node_ids)
    while queue:
        parent = queue.popleft()
        for edge in edges_by_parent[parent]:
            child = str(edge["toNodeId"])
            action: ChangeAction = edge["onUpstreamIdentityChange"]
            if action == "byte_identical":
                retained.add(child)
                continue
            (invalidated if action == "invalidate" else rebuild).add(child)
            retained.discard(child)
            if child not in propagated:
                propagated.add(child)
                queue.append(child)
    return {
        "changedNodeIds": sorted(changed_node_ids),
        "invalidatedNodeIds": sorted(invalidated),
        "rebuildNodeIds": sorted(rebuild),
        "retainedByteIdenticalNodeIds": sorted(retained - invalidated - rebuild),
        "failClosed": True,
    }


def _validate_identity(node: dict[str, Any]) -> None:
    identity = node["identity"]
    if not isinstance(identity, dict) or not identity:
        raise DependencyGraphError("dependency_identity_invalid")
    classification = node["classification"]
    portable = node["portable"]
    if classification == "private_restricted" and portable:
        raise DependencyGraphError("private_identity_cannot_be_portable")
    if portable:
        forbidden = {
            "rawSourcePath",
            "decodedSourcePath",
            "rawSourceSha256",
            "decodedSourceSha256",
            "privateFingerprint",
        }
        if forbidden & set(identity):
            raise DependencyGraphError("portable_identity_contains_restricted_source")
    if classification == "portable_opaque":
        handle = identity.get("opaqueLineageId")
        if not isinstance(handle, str) or not handle.startswith("lineage_"):
            raise DependencyGraphError("portable_opaque_lineage_invalid")
    elif not all(isinstance(value, str) and value for value in identity.values()):
        raise DependencyGraphError("dependency_identity_value_invalid")


def _reject_cycles(adjacency: dict[str, list[str]]) -> None:
    colour = {node_id: 0 for node_id in adjacency}

    def visit(node_id: str) -> None:
        if colour[node_id] == 1:
            raise DependencyGraphError("dependency_graph_cycle")
        if colour[node_id] == 2:
            return
        colour[node_id] = 1
        for child in adjacency[node_id]:
            visit(child)
        colour[node_id] = 2

    for node_id in sorted(adjacency):
        visit(node_id)


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
