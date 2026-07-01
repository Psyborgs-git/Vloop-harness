"""Planner — compiles and validates a Workflow_Definition into a ``Dag``.

The Planner is the Control_Plane subsystem that turns a user-submitted
Workflow_Definition into a validated, in-memory :class:`~core.dag.Dag` the
DAG_Executor can schedule against. It is **pure**: it dispatches no model call
and starts no Kernel workload (Requirement 1.5). It also **never persists** and
**never assigns an identifier** — the caller (an HTTP handler) persists and
assigns an id only when :meth:`Planner.build_dag` succeeds, so rejected
definitions get neither (Requirements 1.2, 1.3, 1.4).

Validation rules
----------------
* **Structural** — the definition must be an object with a list of well-formed
  steps; every step needs a non-empty string ``id`` and ``type``, and step ids
  must be unique.
* **Dangling dependencies** — every ``dependsOn`` entry must name a known step
  (Requirement 1.2's "steps involved" surface area).
* **Missing references** — a step that *references* an agent, tool, or declared
  input that does not exist is rejected, and the error names the missing
  reference (Requirement 1.3). A reference that is simply *absent* (e.g. an
  agent step with no ``agent`` key) is not treated as a missing reference; only
  references that are present but unresolvable are flagged.
* **Cycles** — a dependency cycle is rejected and the error names the steps
  involved in the cycle (Requirement 1.2).

:meth:`Planner.validate` returns the full list of problems without side
effects; :meth:`Planner.build_dag` raises :class:`ValidationError` carrying all
problems on the first failure and otherwise returns the compiled ``Dag``.

Reference shape
---------------
Within a step's ``config``:

* agent steps reference an agent via ``"agent"`` (aliases: ``"agentId"``,
  ``"agent_id"``);
* tool steps reference a tool via ``"tool"`` (aliases: ``"toolName"``,
  ``"tool_name"``);
* any step may declare the inputs it consumes via ``"inputs"`` — a list of
  names that must each appear in the definition's top-level ``inputs`` map.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.dag import Dag, DagNode

# Config keys that carry a step's primary agent/tool reference, in priority
# order. The first present, non-empty value wins.
_AGENT_REF_KEYS: tuple[str, ...] = ("agent", "agentId", "agent_id")
_TOOL_REF_KEYS: tuple[str, ...] = ("tool", "toolName", "tool_name")


class ValidationError(Exception):
    """Raised when a Workflow_Definition is invalid.

    Carries a machine-readable ``code`` (the first/primary problem), a
    human-readable ``message``, and a ``detail`` dict. ``detail["problems"]``
    holds every problem found, so a caller can surface all of them at once.
    """

    def __init__(self, code: str, message: str, detail: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


@runtime_checkable
class AgentLookup(Protocol):
    """Minimal interface for resolving agent references.

    Satisfied by :class:`core.agent_orchestrator.AgentOrchestrator` (its
    ``get_agent`` returns ``None`` for unknown ids) and trivially mockable.
    """

    def get_agent(self, agent_id: str) -> Any | None: ...


@runtime_checkable
class ToolLookup(Protocol):
    """Minimal interface for resolving tool references.

    Will be satisfied by the Tool_Registry (task 19); trivially mockable.
    """

    def has_tool(self, tool_name: str) -> bool: ...


class ReferenceResolver:
    """Checks that referenced agents, tools, and inputs exist.

    Agents and tools are resolved through injected catalogs (an
    :class:`AgentLookup` such as ``AgentOrchestrator`` and a :class:`ToolLookup`
    such as the Tool_Registry); inputs are resolved against the definition's
    own declared ``inputs``. Both catalogs are optional so the resolver can be
    constructed and mocked in isolation — when a catalog is absent, any
    *present* reference of that kind is treated as unresolvable.
    """

    def __init__(
        self,
        agents: AgentLookup | None = None,
        tools: ToolLookup | None = None,
    ) -> None:
        self._agents = agents
        self._tools = tools

    def agent_exists(self, agent_ref: str | None) -> bool:
        """True when ``agent_ref`` resolves to a known agent."""
        if not agent_ref:
            return False
        if self._agents is None:
            return False
        return self._agents.get_agent(agent_ref) is not None

    def tool_exists(self, tool_ref: str | None) -> bool:
        """True when ``tool_ref`` resolves to a known tool."""
        if not tool_ref:
            return False
        if self._tools is None:
            return False
        return bool(self._tools.has_tool(tool_ref))

    @staticmethod
    def input_exists(input_ref: str, declared_inputs: dict[str, Any]) -> bool:
        """True when ``input_ref`` names a declared definition input."""
        return input_ref in declared_inputs


class Planner:
    """Compiles and validates Workflow_Definitions into ``Dag``s."""

    def __init__(self, registry: ReferenceResolver) -> None:
        self._registry = registry

    # -- public API --------------------------------------------------------

    def build_dag(self, definition: dict[str, Any]) -> Dag:
        """Compile ``definition`` into a validated :class:`~core.dag.Dag`.

        Pure: dispatches no model call and starts no Kernel workload
        (Requirement 1.5). Raises :class:`ValidationError` on any structural
        problem, dangling dependency, missing agent/tool/input reference
        (Requirement 1.3), or dependency cycle (Requirement 1.2). The Planner
        neither persists the definition nor assigns it an identifier; that is
        the caller's job and only on success (Requirement 1.4).
        """
        problems, nodes, edges = self._analyze(definition)
        if problems:
            primary = problems[0]
            raise ValidationError(
                code=primary["code"],
                message=primary["message"],
                detail={"problems": problems},
            )
        return Dag(nodes=nodes, edges=edges)

    def validate(self, definition: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a list of validation problems (empty = valid).

        Side-effect free (Requirement 1.5): performs only read-only reference
        lookups and never persists, assigns ids, calls models, or starts
        workloads. Each problem is a dict with ``code``, ``message``, and
        ``detail`` keys.
        """
        problems, _nodes, _edges = self._analyze(definition)
        return problems

    # -- internals ---------------------------------------------------------

    def _analyze(
        self, definition: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, DagNode], tuple[tuple[str, str], ...]]:
        """Single analysis pass shared by ``validate`` and ``build_dag``.

        Returns the ordered problem list together with the compiled node map
        and edge tuple (both empty when structural problems prevent building a
        graph). Problems are ordered structural → reference → cycle so that the
        first problem is the most fundamental and drives ``build_dag``'s raised
        ``code``.
        """
        problems: list[dict[str, Any]] = []

        if not isinstance(definition, dict):
            problems.append(
                _problem(
                    "invalid_definition",
                    f"Workflow_Definition must be an object, got "
                    f"{type(definition).__name__}.",
                    {},
                )
            )
            return problems, {}, ()

        raw_steps = definition.get("steps")
        if raw_steps is None:
            raw_steps = []
        if not isinstance(raw_steps, list):
            problems.append(
                _problem(
                    "invalid_steps",
                    f"Workflow_Definition 'steps' must be a list, got "
                    f"{type(raw_steps).__name__}.",
                    {},
                )
            )
            return problems, {}, ()

        # -- structural parsing into nodes --------------------------------
        nodes: dict[str, DagNode] = {}
        seen_ids: set[str] = set()
        for index, step in enumerate(raw_steps):
            if not isinstance(step, dict):
                problems.append(
                    _problem(
                        "invalid_step",
                        f"Workflow_Step at index {index} must be an object, got "
                        f"{type(step).__name__}.",
                        {"index": index},
                    )
                )
                continue

            step_id = step.get("id")
            if not isinstance(step_id, str) or not step_id:
                problems.append(
                    _problem(
                        "invalid_step",
                        f"Workflow_Step at index {index} is missing a non-empty "
                        f"string 'id'.",
                        {"index": index},
                    )
                )
                continue

            step_type = step.get("type")
            if not isinstance(step_type, str) or not step_type:
                problems.append(
                    _problem(
                        "invalid_step",
                        f"Workflow_Step '{step_id}' is missing a non-empty string "
                        f"'type'.",
                        {"step": step_id},
                    )
                )
                continue

            if step_id in seen_ids:
                problems.append(
                    _problem(
                        "duplicate_step_id",
                        f"Duplicate Workflow_Step id '{step_id}'.",
                        {"step": step_id},
                    )
                )
                continue
            seen_ids.add(step_id)

            config = step.get("config")
            if not isinstance(config, dict):
                config = {}
            depends_on = _string_tuple(step.get("dependsOn"))

            nodes[step_id] = DagNode(
                step_id=step_id,
                step_type=step_type,
                config=config,
                depends_on=depends_on,
            )

        # If no well-formed nodes survived, there is nothing further to check.
        if not nodes:
            return problems, {}, ()

        declared_inputs = definition.get("inputs")
        if not isinstance(declared_inputs, dict):
            declared_inputs = {}

        # -- dependency + reference checks (ordered by step) --------------
        for step_id in sorted(nodes):
            node = nodes[step_id]

            for dep in node.depends_on:
                if dep not in nodes:
                    problems.append(
                        _problem(
                            "missing_dependency",
                            f"Workflow_Step '{step_id}' depends on unknown step "
                            f"'{dep}'.",
                            {"step": step_id, "reference": dep},
                        )
                    )

            if node.step_type == "agent":
                agent_ref = _first_ref(node.config, _AGENT_REF_KEYS)
                if agent_ref is not None and not self._registry.agent_exists(agent_ref):
                    problems.append(
                        _problem(
                            "missing_agent",
                            f"Workflow_Step '{step_id}' references unknown agent "
                            f"'{agent_ref}'.",
                            {"step": step_id, "reference": agent_ref},
                        )
                    )
            elif node.step_type == "tool":
                tool_ref = _first_ref(node.config, _TOOL_REF_KEYS)
                if tool_ref is not None and not self._registry.tool_exists(tool_ref):
                    problems.append(
                        _problem(
                            "missing_tool",
                            f"Workflow_Step '{step_id}' references unknown tool "
                            f"'{tool_ref}'.",
                            {"step": step_id, "reference": tool_ref},
                        )
                    )

            for input_ref in _string_tuple(node.config.get("inputs")):
                if not ReferenceResolver.input_exists(input_ref, declared_inputs):
                    problems.append(
                        _problem(
                            "missing_input",
                            f"Workflow_Step '{step_id}' references unknown input "
                            f"'{input_ref}'.",
                            {"step": step_id, "reference": input_ref},
                        )
                    )

        # -- edges + cycle detection --------------------------------------
        edges = tuple(
            (dep, step_id)
            for step_id in sorted(nodes)
            for dep in nodes[step_id].depends_on
            if dep in nodes
        )
        dag = Dag(nodes=nodes, edges=edges)
        cycle = dag.detect_cycle()
        if cycle is not None:
            problems.append(
                _problem(
                    "cycle",
                    f"Workflow_Definition contains a dependency cycle: "
                    f"{' -> '.join(cycle)}.",
                    {"steps": cycle},
                )
            )

        return problems, nodes, edges


# -- module-level helpers --------------------------------------------------


def _problem(code: str, message: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def _first_ref(config: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first present, non-empty string reference among ``keys``."""
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a value into a tuple of its string members (others dropped)."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)
