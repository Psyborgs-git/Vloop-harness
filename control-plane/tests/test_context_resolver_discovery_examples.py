"""Example-based unit tests for project-file auto-discovery (task 23.3).

When the Control_Plane begins working in a project directory, the
Context_Resolver auto-discovers a configured set of designated project context
files (for example ``AGENTS.md`` / ``CONTEXT.md``) in that directory, reading
each through the injected Kernel-managed filesystem (Requirement 12.4).

These examples verify, concretely, that:
* designated context files that exist are discovered and their content resolved;
* absent designated files are skipped (not surfaced as unresolved placeholders);
* discovery honors the *configured* set of filenames and their configured order.

Validates: Requirements 12.4
"""

from __future__ import annotations

from core.context_resolver import (
    DEFAULT_CONTEXT_FILENAMES,
    KIND_FILE,
    ContextResolver,
)


class RecordingKernelFilesystem:
    """In-memory kernel filesystem stand-in that records probe/read order.

    Only the methods exercised by auto-discovery are meaningful here:
    :meth:`path_exists` (the discovery probe) and :meth:`read_file` (content
    resolution). The recorders let the examples assert the order in which the
    resolver visits configured filenames.
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = files or {}
        self.exists_calls: list[str] = []
        self.read_calls: list[str] = []

    def read_file(self, path: str) -> str:
        self.read_calls.append(path)
        if path not in self.files:
            raise FileNotFoundError(f"no such file: {path}")
        return self.files[path]

    def read_folder(self, path: str) -> str:  # pragma: no cover - not used here
        raise FileNotFoundError(f"no such folder: {path}")

    def read_git_diff(self, target: str) -> str:  # pragma: no cover - not used here
        return ""

    def read_url(self, url: str) -> str:  # pragma: no cover - not used here
        raise ConnectionError(f"unreachable: {url}")

    def path_exists(self, path: str) -> bool:
        self.exists_calls.append(path)
        return path in self.files


def test_discovers_existing_designated_file_and_resolves_content():
    """An existing designated file is discovered and its content injected."""
    fs = RecordingKernelFilesystem(files={"/proj/AGENTS.md": "# agent rules\nbe nice"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    discovered = resolver.discover_project_context("/proj")

    assert len(discovered) == 1
    ref = discovered[0]
    assert ref.target == "/proj/AGENTS.md"
    assert ref.kind == KIND_FILE
    assert ref.resolved is True
    assert ref.content == "# agent rules\nbe nice"
    assert ref.error is None


def test_discovers_all_designated_files_that_exist():
    """Every configured file that exists is discovered and resolved."""
    fs = RecordingKernelFilesystem(
        files={
            "/proj/AGENTS.md": "agents",
            "/proj/CONTEXT.md": "context",
        }
    )
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    discovered = resolver.discover_project_context("/proj")

    assert [r.target for r in discovered] == ["/proj/AGENTS.md", "/proj/CONTEXT.md"]
    assert all(r.resolved for r in discovered)
    assert [r.content for r in discovered] == ["agents", "context"]


def test_absent_designated_files_are_skipped_not_placeholdered():
    """Absent files are silently skipped, never surfaced as placeholders."""
    fs = RecordingKernelFilesystem(files={"/proj/CONTEXT.md": "ctx only"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    discovered = resolver.discover_project_context("/proj")

    # Only the file that exists is discovered; the absent AGENTS.md produces no
    # entry at all (unlike an unresolvable inline reference, which placeholders).
    assert len(discovered) == 1
    assert discovered[0].target == "/proj/CONTEXT.md"
    assert all(r.resolved for r in discovered)
    # The missing file was probed but never read.
    assert "/proj/AGENTS.md" in fs.exists_calls
    assert "/proj/AGENTS.md" not in fs.read_calls


def test_discovery_returns_empty_when_no_designated_files_present():
    """A project directory with none of the designated files yields nothing."""
    fs = RecordingKernelFilesystem(files={"/proj/README.md": "not a context file"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    assert resolver.discover_project_context("/proj") == []


def test_discovery_respects_configured_filenames():
    """Only files in the configured set are discovered, even if others exist.

    ``README.md`` exists but is not a configured designated context file, so it
    must not be discovered; ``CONTEXT.md`` is not in this resolver's configured
    set either and is likewise ignored.
    """
    fs = RecordingKernelFilesystem(
        files={
            "/proj/AGENTS.md": "agents",
            "/proj/README.md": "readme",
            "/proj/CONTEXT.md": "context",
        }
    )
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md",))

    discovered = resolver.discover_project_context("/proj")

    assert [r.target for r in discovered] == ["/proj/AGENTS.md"]
    # Non-configured files are never probed.
    assert fs.exists_calls == ["/proj/AGENTS.md"]


def test_discovery_visits_filenames_in_configured_order():
    """Discovery order follows the configured filename order, not disk order."""
    fs = RecordingKernelFilesystem(
        files={
            "/proj/AGENTS.md": "agents",
            "/proj/CONTEXT.md": "context",
            "/proj/VLOOP.md": "vloop",
        }
    )
    # Deliberately reverse the natural/alphabetical order.
    resolver = ContextResolver(
        fs, context_filenames=("VLOOP.md", "CONTEXT.md", "AGENTS.md")
    )

    discovered = resolver.discover_project_context("/proj")

    assert [r.target for r in discovered] == [
        "/proj/VLOOP.md",
        "/proj/CONTEXT.md",
        "/proj/AGENTS.md",
    ]
    # Probes happen in the configured order too.
    assert fs.exists_calls == [
        "/proj/VLOOP.md",
        "/proj/CONTEXT.md",
        "/proj/AGENTS.md",
    ]


def test_discovery_handles_nested_designated_filename():
    """A configured nested path (e.g. ``.vloop/context.md``) is joined correctly."""
    fs = RecordingKernelFilesystem(files={"/proj/.vloop/context.md": "nested ctx"})
    resolver = ContextResolver(fs, context_filenames=(".vloop/context.md",))

    discovered = resolver.discover_project_context("/proj")

    assert len(discovered) == 1
    assert discovered[0].target == "/proj/.vloop/context.md"
    assert discovered[0].content == "nested ctx"


def test_discovery_trims_trailing_slash_on_project_dir():
    """A trailing slash on the project directory does not double the separator."""
    fs = RecordingKernelFilesystem(files={"/proj/AGENTS.md": "agents"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md",))

    discovered = resolver.discover_project_context("/proj/")

    assert [r.target for r in discovered] == ["/proj/AGENTS.md"]


def test_discovery_with_empty_project_dir_uses_bare_filenames():
    """An empty project dir resolves designated files by bare name."""
    fs = RecordingKernelFilesystem(files={"AGENTS.md": "agents"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    discovered = resolver.discover_project_context("")

    assert [r.target for r in discovered] == ["AGENTS.md"]


def test_default_context_filenames_are_used_when_unconfigured():
    """Without explicit configuration, the default designated set is honored."""
    # Pick a couple of the documented defaults to confirm they are active.
    assert "AGENTS.md" in DEFAULT_CONTEXT_FILENAMES
    assert "CONTEXT.md" in DEFAULT_CONTEXT_FILENAMES

    fs = RecordingKernelFilesystem(
        files={f"/proj/{name}": name for name in DEFAULT_CONTEXT_FILENAMES}
    )
    resolver = ContextResolver(fs)  # no context_filenames override

    discovered = resolver.discover_project_context("/proj")

    assert [r.target for r in discovered] == [
        f"/proj/{name}" for name in DEFAULT_CONTEXT_FILENAMES
    ]
    assert all(r.resolved for r in discovered)
