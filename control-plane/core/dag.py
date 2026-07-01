"""DAG model for compiled Workflow_Definitions.

A :class:`Dag` is the validated, in-memory graph the Planner produces from a
Workflow_Definition and the DAG_Executor schedules against. Nodes carry their
declared dependencies (``depends_on``); the graph's structure is derived from
those declarations, so the topology helpers below treat ``depends_on`` as the
authoritative source of edges.

These types are pure logic with no persistence or I/O; they hold no behavior
beyond graph queries. Cycle detection and reference validation drive Planner
rejection (Requirements 1.1, 1.2); the layering/dependents helpers drive
executor scheduling (Requirement 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DagNode:
    """A single node in a compiled workflow graph.

    ``step_type`` is one of ``"agent"``, ``"tool"``, ``"approval"`` or
    ``"subworkflow"``. ``depends_on`` lists the ids of steps that must reach a
    completed state before this step may execute.
    """

    step_id: str
    step_type: str
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dag:
    """A directed acyclic graph of Workflow_Steps and their dependency edges.

    ``edges`` are ``(from_step, to_step)`` pairs where ``from_step`` must
    complete before ``to_step`` runs (i.e. ``to_step`` depends on
    ``from_step``). They mirror the per-node ``depends_on`` declarations.
    """

    nodes: dict[str, DagNode]
    edges: tuple[tuple[str, str], ...] = ()

    # -- internal adjacency helpers ---------------------------------------

    def _predecessors(self) -> dict[str, set[str]]:
        """Map each step to the set of steps it directly depends on.

        Dependencies that do not correspond to a known node are ignored here;
        missing references are reported separately by the Planner
        (Requirement 1.3).
        """
        preds: dict[str, set[str]] = {step_id: set() for step_id in self.nodes}
        for step_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep in self.nodes:
                    preds[step_id].add(dep)
        return preds

    def _successors(self) -> dict[str, set[str]]:
        """Map each step to the set of steps that directly depend on it."""
        succs: dict[str, set[str]] = {step_id: set() for step_id in self.nodes}
        for step_id, deps in self._predecessors().items():
            for dep in deps:
                succs[dep].add(step_id)
        return succs

    # -- public topology API ----------------------------------------------

    def detect_cycle(self) -> list[str] | None:
        """Return a list of step ids forming a dependency cycle, or ``None``.

        The returned path lists the steps involved in one detected cycle in
        traversal order, with the repeated step appended to close the loop
        (e.g. ``["a", "b", "a"]``). Used by the Planner to reject cyclic
        definitions and name the offending steps (Requirement 1.2).
        """
        preds = self._predecessors()
        WHITE, GREY, BLACK = 0, 1, 2
        color: dict[str, int] = {step_id: WHITE for step_id in self.nodes}
        stack: list[str] = []

        def visit(step_id: str) -> list[str] | None:
            color[step_id] = GREY
            stack.append(step_id)
            for dep in sorted(preds[step_id]):
                if color[dep] == GREY:
                    # Found a back edge: slice the current path from the
                    # recurrence point and close the loop.
                    idx = stack.index(dep)
                    return stack[idx:] + [dep]
                if color[dep] == WHITE:
                    found = visit(dep)
                    if found is not None:
                        return found
            stack.pop()
            color[step_id] = BLACK
            return None

        for step_id in sorted(self.nodes):
            if color[step_id] == WHITE:
                found = visit(step_id)
                if found is not None:
                    return found
        return None

    def topological_layers(self) -> list[list[str]]:
        """Return steps grouped into dependency layers via Kahn's algorithm.

        Layer 0 holds the roots (no dependencies); each subsequent layer holds
        steps whose dependencies are all satisfied by earlier layers. Steps
        within a layer are independent and may run concurrently
        (Requirement 3.2). Each layer is sorted for determinism.

        Raises:
            ValueError: if the graph contains a cycle and cannot be fully
                ordered.
        """
        preds = self._predecessors()
        succs = self._successors()
        remaining = {step_id: len(deps) for step_id, deps in preds.items()}

        layers: list[list[str]] = []
        current = sorted(step_id for step_id, count in remaining.items() if count == 0)
        resolved = 0
        while current:
            layers.append(current)
            resolved += len(current)
            nxt: list[str] = []
            for step_id in current:
                for dependent in succs[step_id]:
                    remaining[dependent] -= 1
                    if remaining[dependent] == 0:
                        nxt.append(dependent)
            current = sorted(nxt)

        if resolved != len(self.nodes):
            cycle = self.detect_cycle()
            raise ValueError(
                f"DAG contains a cycle; cannot compute topological layers: {cycle}"
            )
        return layers

    def dependents_of(self, step_id: str) -> set[str]:
        """Return the set of steps that transitively depend on ``step_id``.

        Follows successor edges to collect every step reachable from
        ``step_id`` (excluding ``step_id`` itself). Used to compute the retry
        closure of a failed step (Requirement 4.4). Unknown ids yield an empty
        set.
        """
        if step_id not in self.nodes:
            return set()
        succs = self._successors()
        result: set[str] = set()
        frontier = [step_id]
        while frontier:
            current = frontier.pop()
            for dependent in succs[current]:
                if dependent not in result:
                    result.add(dependent)
                    frontier.append(dependent)
        return result

    def roots(self) -> list[str]:
        """Return the steps with no dependencies, sorted for determinism."""
        return sorted(
            step_id for step_id, node in self.nodes.items() if not node.depends_on
        )
