from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


class GraphError(Exception):
    """Raised when the DAG contains a cyclic dependency or invalid edges."""


def topological_sort(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """Return a topological ordering of the DAG or raise GraphError on cycles.

    Raises GraphError if an edge references a node not present in *nodes*.
    """
    node_set = set(nodes)
    graph: dict[str, list[str]] = {node: [] for node in nodes}
    in_degree: dict[str, int] = {node: 0 for node in nodes}

    for parent, child in edges:
        if parent not in node_set:
            raise GraphError(f"Edge references unknown parent node: {parent!r}")
        if child not in node_set:
            raise GraphError(f"Edge references unknown child node: {child!r}")
        graph[parent].append(child)
        in_degree[child] = in_degree.get(child, 0) + 1

    queue: deque[str] = deque(node for node in nodes if in_degree[node] == 0)
    sorted_nodes: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_nodes.append(node)

        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_nodes) != len(nodes):
        raise GraphError("Cyclic dependency detected in DAG")

    return sorted_nodes


@dataclass(frozen=True)
class DAG:
    nodes: list[dict[str, Any]]

    @staticmethod
    def from_nodes(nodes: list[dict[str, Any]]) -> DAG:
        return DAG(nodes=nodes)

    def ids(self) -> list[str]:
        return [n["id"] for n in self.nodes]

    def deps(self, node_id: str) -> list[str]:
        for n in self.nodes:
            if n["id"] == node_id:
                return list(n.get("deps", []))
        return []

    def topological_sort(self) -> list[str] | None:
        """Return a deterministic topological ordering or None on cycle.

        Iterates in the original node-list order so that the result is
        stable across runs.  Uses ``collections.deque`` for O(1) pops.
        """
        id_list = self.ids()
        id_set = set(id_list)
        graph: dict[str, list[str]] = {i: [] for i in id_list}
        indeg: dict[str, int] = {i: 0 for i in id_list}
        for i in id_list:
            deps = [d for d in self.deps(i) if d in id_set]
            for d in deps:
                graph[d].append(i)
                indeg[i] += 1
        q: deque[str] = deque(i for i in id_list if indeg[i] == 0)
        order: list[str] = []
        while q:
            cur = q.popleft()
            order.append(cur)
            for nxt in graph[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    q.append(nxt)
        if len(order) != len(id_list):
            return None
        return order


def dag_is_acyclic(dag: DAG) -> bool:
    """Check whether *dag* is acyclic using deterministic iteration order."""
    id_list = dag.ids()
    id_set = set(id_list)
    graph: dict[str, list[str]] = {i: [] for i in id_list}
    indeg: dict[str, int] = {i: 0 for i in id_list}
    for i in id_list:
        deps = [d for d in dag.deps(i) if d in id_set]
        for d in deps:
            graph[d].append(i)
            indeg[i] += 1
    q: deque[str] = deque(i for i in id_list if indeg[i] == 0)
    seen = 0
    while q:
        cur = q.popleft()
        seen += 1
        for nxt in graph[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    return seen == len(id_list)
