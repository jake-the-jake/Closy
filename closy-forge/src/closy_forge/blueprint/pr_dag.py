from __future__ import annotations

from typing import Any


def validate_pr_dag(stack: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    nodes = stack.get("nodes")
    edges = stack.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["pr_dag_nodes_or_edges_missing"]
    by_id = {str(node.get("id")): node for node in nodes if isinstance(node, dict)}
    if len(by_id) != len(nodes):
        issues.append("pr_dag_node_ids_not_unique")
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "kind"}:
            issues.append("pr_dag_edge_invalid")
            continue
        source = str(edge["from"])
        destination = str(edge["to"])
        if source not in by_id or destination not in by_id:
            issues.append("pr_dag_edge_node_missing")
            continue
        adjacency[source].add(destination)
    if _contains_cycle(adjacency):
        issues.append("pr_dag_cycle_detected")
    for node_id, node in by_id.items():
        required = {
            "id",
            "repository",
            "pullRequest",
            "capabilityRole",
            "branch",
            "baseRef",
            "baseSha",
            "headSha",
            "parentIds",
            "dependencyIds",
            "uniqueCommitRange",
            "integrationMappings",
            "sourceOnly",
            "superseded",
            "mergeEligible",
            "neverMergeWith",
            "latestExactHeadForgeRun",
        }
        if not required.issubset(node):
            issues.append(f"pr_dag_node_fields_missing:{node_id}")
            continue
        if node["uniqueCommitRange"] != f"{node['baseSha']}..{node['headSha']}":
            issues.append(f"pr_dag_unique_range_invalid:{node_id}")
        if node["sourceOnly"] and node["mergeEligible"]:
            issues.append(f"pr_dag_source_only_merge_eligible:{node_id}")
        for relationship in (*node["parentIds"], *node["dependencyIds"], *node["neverMergeWith"]):
            if relationship not in by_id:
                issues.append(f"pr_dag_relationship_missing:{node_id}")
        expected_parents = {
            str(edge["from"])
            for edge in edges
            if isinstance(edge, dict) and edge.get("to") == node_id and edge.get("kind") == "parent"
        }
        if set(node["parentIds"]) != expected_parents:
            issues.append(f"pr_dag_parent_edges_mismatch:{node_id}")
    validation = stack.get("validation", {})
    if validation != {
        "acyclic": True,
        "exactMergeBases": True,
        "replayedCommonAncestryAbsent": True,
        "mode": "read_only_git_graph_verification",
    }:
        issues.append("pr_dag_validation_record_invalid")
    return sorted(set(issues))


def _contains_cycle(adjacency: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in adjacency[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in adjacency)
