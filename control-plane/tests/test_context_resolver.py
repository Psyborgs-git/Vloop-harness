"""Unit tests for core.context_resolver reference resolution and placeholders.

These cover the core resolution behavior of task 23.1: resolving file / folder /
git-diff / URL references into injected content (Req 12.1, 12.2), descriptive
placeholders with continued processing on failure (Req 12.3), and basic project
context auto-discovery (Req 12.4).
"""

from __future__ import annotations

from core.context_resolver import (
    KIND_FILE,
    KIND_FOLDER,
    KIND_GIT_DIFF,
    KIND_URL,
    ContextResolver,
)


class FakeKernelFilesystem:
    """In-memory stand-in for the kernel-managed filesystem access interface."""

    def __init__(
        self,
        *,
        files: dict[str, str] | None = None,
        folders: dict[str, str] | None = None,
        diffs: dict[str, str] | None = None,
        urls: dict[str, str] | None = None,
    ) -> None:
        self.files = files or {}
        self.folders = folders or {}
        self.diffs = diffs or {}
        self.urls = urls or {}

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"no such file: {path}")
        return self.files[path]

    def read_folder(self, path: str) -> str:
        if path not in self.folders:
            raise FileNotFoundError(f"no such folder: {path}")
        return self.folders[path]

    def read_git_diff(self, target: str) -> str:
        return self.diffs.get(target, "")

    def read_url(self, url: str) -> str:
        if url not in self.urls:
            raise ConnectionError(f"unreachable: {url}")
        return self.urls[url]

    def path_exists(self, path: str) -> bool:
        return path in self.files or path in self.folders


def test_resolves_file_reference_injects_actual_content():
    fs = FakeKernelFilesystem(files={"src/app.py": "print('hi')"})
    resolver = ContextResolver(fs)

    result = resolver.resolve_text("look at @src/app.py please")

    assert "print('hi')" in result.text
    assert "@src/app.py" not in result.text
    assert len(result.references) == 1
    ref = result.references[0]
    assert ref.kind == KIND_FILE
    assert ref.resolved is True
    assert ref.content == "print('hi')"
    assert result.has_unresolved is False


def test_unresolvable_reference_injects_placeholder_and_continues():
    fs = FakeKernelFilesystem(files={"good.txt": "GOOD"})
    resolver = ContextResolver(fs)

    result = resolver.resolve_text("@missing.txt then @good.txt")

    # Missing reference becomes a descriptive placeholder...
    assert "[unresolved context reference @missing.txt" in result.text
    # ...and processing continues for the rest (Req 12.3).
    assert "GOOD" in result.text
    assert result.has_unresolved is True
    assert [r.resolved for r in result.references] == [False, True]
    assert result.references[0].error is not None


def test_folder_reference_classified_and_resolved():
    fs = FakeKernelFilesystem(folders={"docs": "a.md\nb.md"})
    resolver = ContextResolver(fs)

    result = resolver.resolve_text("@docs/")

    assert result.references[0].kind == KIND_FOLDER
    assert result.references[0].resolved is True
    assert "a.md" in result.text


def test_url_reference_classified_and_resolved():
    fs = FakeKernelFilesystem(urls={"https://example.com": "PAGE"})
    resolver = ContextResolver(fs)

    result = resolver.resolve_text("see @https://example.com")

    assert result.references[0].kind == KIND_URL
    assert "PAGE" in result.text


def test_git_diff_reference_classified_and_resolved():
    fs = FakeKernelFilesystem(diffs={"": "diff --git a b", "HEAD~1": "old diff"})
    resolver = ContextResolver(fs)

    whole = resolver.resolve_text("@git-diff")
    scoped = resolver.resolve_text("@git-diff:HEAD~1")

    assert whole.references[0].kind == KIND_GIT_DIFF
    assert "diff --git a b" in whole.text
    assert "old diff" in scoped.text


def test_empty_content_is_treated_as_unresolved():
    fs = FakeKernelFilesystem(files={"empty.txt": ""})
    resolver = ContextResolver(fs)

    result = resolver.resolve_text("@empty.txt")

    assert result.references[0].resolved is False
    assert "[unresolved context reference @empty.txt" in result.text


def test_text_without_references_is_returned_unchanged():
    resolver = ContextResolver(FakeKernelFilesystem())
    result = resolver.resolve_text("no references here, email user@host stays")
    # ``user@host`` is mid-word (not whitespace/start anchored) -> not a ref.
    assert result.text == "no references here, email user@host stays"
    assert result.references == []


def test_discover_project_context_finds_designated_files():
    fs = FakeKernelFilesystem(files={"/proj/AGENTS.md": "agent rules"})
    resolver = ContextResolver(fs, context_filenames=("AGENTS.md", "CONTEXT.md"))

    discovered = resolver.discover_project_context("/proj")

    assert len(discovered) == 1
    assert discovered[0].target == "/proj/AGENTS.md"
    assert discovered[0].content == "agent rules"
    assert discovered[0].resolved is True


def test_discover_project_context_skips_absent_files():
    resolver = ContextResolver(FakeKernelFilesystem())
    assert resolver.discover_project_context("/empty") == []


def test_requires_filesystem():
    try:
        ContextResolver(None)  # type: ignore[arg-type]
    except ValueError:
        return
    raise AssertionError("expected ValueError when filesystem is missing")
