"""Example-based unit tests for the Tool_Registry tool/toolset catalog.

These tests verify the catalog-maintenance and grouping behavior of
:class:`core.tool_registry.ToolRegistry` (Requirement 9.1): the registry
maintains a catalog of available Tools and the Toolsets that group them.

Validates: Requirements 9.1
"""

from __future__ import annotations

from core.orchestration_types import ToolSpec, ToolsetSpec
from core.tool_registry import ToolRegistry


def _tool(name: str, toolset: str, *, mutating: bool = False) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"{name} tool",
        toolset=toolset,
        mutating=mutating,
    )


def test_registered_tools_appear_in_catalog():
    registry = ToolRegistry()
    web_search = _tool("web_search", "web")
    read_file = _tool("read_file", "fs")

    registry.register_tool(web_search)
    registry.register_tool(read_file)

    catalog = registry.list_tools()
    assert len(catalog) == 2
    assert web_search in catalog
    assert read_file in catalog
    assert {t.name for t in catalog} == {"web_search", "read_file"}
    # Individual lookup returns the catalogued spec.
    assert registry.get_tool("web_search") is web_search
    assert registry.get_tool("read_file") is read_file


def test_registered_toolsets_appear_in_catalog():
    registry = ToolRegistry()
    web_set = ToolsetSpec(id="web", name="Web", tools=["web_search"])
    fs_set = ToolsetSpec(id="fs", name="Filesystem", tools=["read_file", "write_file"])

    registry.register_toolset(web_set)
    registry.register_toolset(fs_set)

    toolsets = registry.list_toolsets()
    assert len(toolsets) == 2
    assert web_set in toolsets
    assert fs_set in toolsets
    assert {ts.id for ts in toolsets} == {"web", "fs"}


def test_tools_in_toolset_groups_by_toolset():
    registry = ToolRegistry()
    registry.register_tool(_tool("web_search", "web"))
    registry.register_tool(_tool("read_file", "fs"))
    registry.register_tool(_tool("write_file", "fs", mutating=True))

    fs_tools = registry.tools_in_toolset("fs")
    assert {t.name for t in fs_tools} == {"read_file", "write_file"}

    web_tools = registry.tools_in_toolset("web")
    assert {t.name for t in web_tools} == {"web_search"}


def test_tools_in_toolset_works_when_tool_registered_before_toolset():
    # Grouping derives from each tool's ``toolset`` field, so it stays accurate
    # even when a tool is registered before its toolset grouping is declared.
    registry = ToolRegistry()
    registry.register_tool(_tool("read_file", "fs"))
    registry.register_toolset(ToolsetSpec(id="fs", name="Filesystem", tools=["read_file"]))

    fs_tools = registry.tools_in_toolset("fs")
    assert {t.name for t in fs_tools} == {"read_file"}


def test_re_registering_a_tool_replaces_the_prior_entry():
    registry = ToolRegistry()
    original = _tool("run_command", "exec")
    registry.register_tool(original)

    updated = ToolSpec(
        name="run_command",
        description="Run a shell command (updated)",
        toolset="exec",
        mutating=True,
    )
    registry.register_tool(updated)

    # No duplicate entry; the catalog holds exactly the replacement.
    catalog = registry.list_tools()
    assert len(catalog) == 1
    assert registry.get_tool("run_command") is updated
    assert registry.get_tool("run_command").mutating is True


def test_re_registering_a_toolset_replaces_the_prior_entry():
    registry = ToolRegistry()
    registry.register_toolset(ToolsetSpec(id="fs", name="Filesystem", tools=["read_file"]))
    registry.register_toolset(
        ToolsetSpec(id="fs", name="Filesystem (v2)", tools=["read_file", "write_file"])
    )

    toolsets = registry.list_toolsets()
    assert len(toolsets) == 1
    assert toolsets[0].name == "Filesystem (v2)"
    assert toolsets[0].tools == ["read_file", "write_file"]


def test_unknown_tool_lookup_returns_none():
    registry = ToolRegistry()
    registry.register_tool(_tool("web_search", "web"))
    assert registry.get_tool("does_not_exist") is None


def test_unknown_toolset_grouping_returns_empty_list():
    registry = ToolRegistry()
    registry.register_tool(_tool("web_search", "web"))
    assert registry.tools_in_toolset("nonexistent") == []


def test_empty_registry_has_empty_catalog():
    registry = ToolRegistry()
    assert registry.list_tools() == []
    assert registry.list_toolsets() == []
    assert registry.get_tool("anything") is None
    assert registry.tools_in_toolset("anything") == []
