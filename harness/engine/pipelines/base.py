"""Pipeline base classes — DAG nodes, edges, conditional branching, loops."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeType(StrEnum):
    COMPONENT = "component"      # DSPy Module
    TOOL = "tool"                # Tool registry call
    CONDITION = "condition"      # Branching decision
    LOOP = "loop"              # Iterate over collection
    MAP = "map"                # Parallel map over collection
    REDUCE = "reduce"          # Aggregate results
    INPUT = "input"            # Pipeline entry point
    OUTPUT = "output"          # Pipeline exit point


class Condition:
    """A branching condition evaluated against execution context."""

    def __init__(self, name: str, predicate: Callable[[dict[str, Any]], bool]) -> None:
        self.name = name
        self.predicate = predicate

    def evaluate(self, context: dict[str, Any]) -> bool:
        return self.predicate(context)


@dataclass
class PipelineNode:
    """A single node in the pipeline DAG."""

    id: str
    type: NodeType
    name: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    # For COMPONENT: {"module": dspy.Module instance or class}
    # For TOOL: {"tool_name": str, "params": dict}
    # For CONDITION: {"condition": Condition instance}
    # For LOOP: {"collection_input": str, "item_key": str}
    # For MAP: {"collection_input": str, "item_key": str}
    # For REDUCE: {"reducer": Callable}
    # For INPUT/OUTPUT: {}

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.id


@dataclass
class PipelineEdge:
    """Directed edge between two nodes."""

    source: str
    target: str
    label: str = ""
    condition: Condition | None = None
    input_map: dict[str, str] = field(default_factory=dict)
    # input_map: {target_field: source_field} maps outputs from source to inputs for target


class PipelineGraph:
    """A DAG of pipeline nodes with edges and optional conditional branches."""

    def __init__(self, name: str = "pipeline") -> None:
        self.name = name
        self._nodes: dict[str, PipelineNode] = {}
        self._edges: list[PipelineEdge] = []
        self._input_node: str | None = None
        self._output_node: str | None = None

    # ── Builder API ─────────────────────────────────────────────────────────

    def add_node(
        self,
        node_type: NodeType,
        name: str = "",
        node_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        nid = node_id or f"node_{uuid.uuid4().hex[:8]}"
        node = PipelineNode(
            id=nid,
            type=node_type,
            name=name or nid,
            config=config or {},
        )
        self._nodes[nid] = node
        if node_type == NodeType.INPUT:
            self._input_node = nid
        elif node_type == NodeType.OUTPUT:
            self._output_node = nid
        return nid

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
        condition: Condition | None = None,
        input_map: dict[str, str] | None = None,
    ) -> None:
        if source not in self._nodes:
            raise ValueError(f"Source node {source!r} not found")
        if target not in self._nodes:
            raise ValueError(f"Target node {target!r} not found")
        self._edges.append(
            PipelineEdge(
                source=source,
                target=target,
                label=label,
                condition=condition,
                input_map=input_map or {},
            )
        )

    def connect(self, source: str, *targets: str, label: str = "") -> None:
        """Connect source to multiple targets unconditionally."""
        for target in targets:
            self.add_edge(source, target, label=label)

    def branch(
        self,
        source: str,
        branches: list[tuple[str, Condition]],
    ) -> None:
        """Add conditional edges from source."""
        for target, condition in branches:
            self.add_edge(source, target, condition=condition)

    # ── Accessors ───────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> PipelineNode | None:
        return self._nodes.get(node_id)

    def outgoing_edges(self, node_id: str) -> list[PipelineEdge]:
        return [e for e in self._edges if e.source == node_id]

    def incoming_edges(self, node_id: str) -> list[PipelineEdge]:
        return [e for e in self._edges if e.target == node_id]

    def nodes(self) -> list[PipelineNode]:
        return list(self._nodes.values())

    def edges(self) -> list[PipelineEdge]:
        return list(self._edges)

    @property
    def input_node(self) -> str | None:
        return self._input_node

    @property
    def output_node(self) -> str | None:
        return self._output_node

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return list of validation errors (empty if valid)."""
        errors: list[str] = []
        if self._input_node is None:
            errors.append("Pipeline missing INPUT node")
        if self._output_node is None:
            errors.append("Pipeline missing OUTPUT node")
        # Check all non-output nodes have outgoing edges
        for node in self._nodes.values():
            if node.type != NodeType.OUTPUT and not self.outgoing_edges(node.id):
                errors.append(f"Node {node.id!r} has no outgoing edges")
        # Check all non-input nodes have incoming edges
        for node in self._nodes.values():
            if node.type != NodeType.INPUT and not self.incoming_edges(node.id):
                errors.append(f"Node {node.id!r} has no incoming edges")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type.value,
                    "name": n.name,
                    "config": {k: str(v) for k, v in n.config.items()},
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "label": e.label,
                    "conditional": e.condition is not None,
                }
                for e in self._edges
            ],
        }
