"""Context_Resolver — resolve inline ``@``-references into agent context.

A :class:`Context_Reference` is an inline ``@``-prefixed token in an agent input
that points at a file, folder, git diff, or URL whose concrete text should be
injected into the agent's context (Requirement 12.1). This module finds those
references, resolves each one, and substitutes the resolved text in place.

Resolution rules
----------------
* **file / folder** references are read through Kernel-managed filesystem access
  and the actual content is injected when access succeeds (Requirement 12.2).
* **git diff** and **URL** references are likewise resolved through the same
  injected, Kernel-managed access surface so no host I/O is performed here.
* A reference that cannot be resolved (missing file, access error, empty
  content) does not abort the pass: a descriptive placeholder identifying the
  unresolved reference is injected and the remaining references continue to be
  processed (Requirement 12.3).
* When the Control_Plane begins working in a project directory, the resolver can
  auto-discover a configured set of designated project context files in that
  directory (Requirement 12.4).

Security / boundary
-------------------
The resolver performs **no host filesystem, git, or network I/O directly**. All
access goes through an injected :class:`KernelFilesystem` interface so the real
implementation routes through the Kernel and tests can supply a mock
(Requirement 12.2; mirrors the "Control_Plane decides WHAT, Kernel decides
HOW/WHERE" boundary).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

# Reference kinds.
KIND_FILE = "file"
KIND_FOLDER = "folder"
KIND_GIT_DIFF = "git-diff"
KIND_URL = "url"

# Designated project context files discovered on entering a project directory
# (Requirement 12.4). Configurable via the ``ContextResolver`` constructor.
DEFAULT_CONTEXT_FILENAMES: tuple[str, ...] = (
    "AGENTS.md",
    "CONTEXT.md",
    "VLOOP.md",
    ".vloop/context.md",
)

# A reference token is an ``@`` at the start of the string or following
# whitespace, then a run of non-whitespace characters. Anchoring on a preceding
# boundary avoids matching email-like ``user@host`` fragments mid-word.
_REFERENCE_RE = re.compile(r"(?:(?<=\s)|^)@(\S+)")

# Trailing punctuation that is almost certainly sentence punctuation rather than
# part of the reference target, trimmed from the matched token.
_TRAILING_PUNCTUATION = ".,;:!?)]}\"'"

_URL_PREFIXES = ("http://", "https://")
_GIT_DIFF_PREFIXES = ("git-diff", "git:")


@runtime_checkable
class KernelFilesystem(Protocol):
    """Kernel-managed access surface used to resolve Context_References.

    The real implementation is backed by the Kernel; tests inject a mock. Each
    method raises on failure (for example a missing path or unreachable URL);
    the resolver converts any raised exception into a descriptive placeholder
    (Requirement 12.3).
    """

    def read_file(self, path: str) -> str:
        """Return the text content of the file at ``path``."""
        ...

    def read_folder(self, path: str) -> str:
        """Return a text rendering (listing and/or contents) of ``path``."""
        ...

    def read_git_diff(self, target: str) -> str:
        """Return the git diff for ``target`` (empty target = whole worktree)."""
        ...

    def read_url(self, url: str) -> str:
        """Return the text content fetched from ``url``."""
        ...

    def path_exists(self, path: str) -> bool:
        """Return whether ``path`` exists (used for auto-discovery)."""
        ...


@dataclass(slots=True)
class ResolvedReference:
    """The outcome of resolving a single Context_Reference."""

    raw: str  # the matched token including the leading ``@`` (e.g. "@foo.py")
    target: str  # the reference target without the ``@`` (e.g. "foo.py")
    kind: str  # one of KIND_FILE / KIND_FOLDER / KIND_GIT_DIFF / KIND_URL
    resolved: bool  # True when actual content was injected (Req 12.2)
    content: str  # injected actual content, or the placeholder (Req 12.3)
    error: str | None = None  # reason the reference could not be resolved

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResolvedContext:
    """The result of resolving every reference found in an agent input."""

    text: str  # original text with each reference replaced by its content
    references: list[ResolvedReference] = field(default_factory=list)

    @property
    def has_unresolved(self) -> bool:
        """True when at least one reference fell back to a placeholder."""
        return any(not ref.resolved for ref in self.references)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "references": [ref.to_dict() for ref in self.references],
        }


class ContextResolver:
    """Resolves ``@``-prefixed Context_References into concrete text.

    All access is performed through the injected :class:`KernelFilesystem`; the
    resolver never touches the host filesystem, git, or network directly.
    """

    def __init__(
        self,
        filesystem: KernelFilesystem,
        *,
        context_filenames: Sequence[str] = DEFAULT_CONTEXT_FILENAMES,
    ) -> None:
        if filesystem is None:
            raise ValueError("a kernel-managed filesystem access interface is required")
        self._fs = filesystem
        self._context_filenames = tuple(context_filenames)

    # -- public API ----------------------------------------------------------

    def resolve_text(self, text: str) -> ResolvedContext:
        """Resolve every Context_Reference in ``text``.

        Each reference is replaced in place by its resolved content, or by a
        descriptive placeholder when it cannot be resolved. Resolution of one
        reference never prevents the others from being processed
        (Requirements 12.1, 12.2, 12.3).
        """
        if not text:
            return ResolvedContext(text=text or "", references=[])

        references: list[ResolvedReference] = []

        def _substitute(match: re.Match[str]) -> str:
            raw_token = match.group(0)
            target = self._trim_target(match.group(1))
            if not target:
                # A lone ``@`` or one that trims to nothing is not a reference;
                # leave the original text untouched.
                return raw_token
            ref = self.resolve_reference(target, raw=f"@{target}")
            references.append(ref)
            return ref.content

        resolved_text = _REFERENCE_RE.sub(_substitute, text)
        return ResolvedContext(text=resolved_text, references=references)

    def resolve_reference(self, target: str, *, raw: str | None = None) -> ResolvedReference:
        """Resolve a single reference ``target`` (with or without a leading ``@``).

        Returns a :class:`ResolvedReference` carrying the actual content on
        success (Req 12.2) or a descriptive placeholder on failure (Req 12.3).
        """
        target = target[1:] if target.startswith("@") else target
        raw = raw if raw is not None else f"@{target}"
        kind = self._classify(target)

        try:
            content = self._read(kind, target)
        except Exception as exc:  # noqa: BLE001 - any access error degrades gracefully
            return self._unresolved(raw, target, kind, reason=self._describe_error(exc))

        if content is None or content == "":
            return self._unresolved(
                raw, target, kind, reason="reference resolved to empty content"
            )

        return ResolvedReference(
            raw=raw,
            target=target,
            kind=kind,
            resolved=True,
            content=content,
        )

    def discover_project_context(self, project_dir: str) -> list[ResolvedReference]:
        """Auto-discover designated project context files in ``project_dir``.

        Checks each configured designated filename relative to the project
        directory and resolves the ones that exist, in configured order
        (Requirement 12.4). Files that are absent are simply skipped.
        """
        discovered: list[ResolvedReference] = []
        base = (project_dir or "").rstrip("/")
        for name in self._context_filenames:
            path = f"{base}/{name}" if base else name
            try:
                exists = self._fs.path_exists(path)
            except Exception:  # noqa: BLE001 - treat probe failure as "not present"
                exists = False
            if not exists:
                continue
            discovered.append(self.resolve_reference(path, raw=f"@{path}"))
        return discovered

    # -- internals -----------------------------------------------------------

    def _read(self, kind: str, target: str) -> str | None:
        """Dispatch a single reference to the kernel-managed access surface."""
        if kind == KIND_URL:
            return self._fs.read_url(target)
        if kind == KIND_GIT_DIFF:
            return self._fs.read_git_diff(self._git_diff_target(target))
        if kind == KIND_FOLDER:
            return self._fs.read_folder(target.rstrip("/"))
        return self._fs.read_file(target)

    @staticmethod
    def _classify(target: str) -> str:
        """Classify a reference target into a resolution kind."""
        lowered = target.lower()
        if lowered.startswith(_URL_PREFIXES):
            return KIND_URL
        if any(lowered == p or lowered.startswith(p) for p in _GIT_DIFF_PREFIXES):
            return KIND_GIT_DIFF
        if target.endswith("/"):
            return KIND_FOLDER
        return KIND_FILE

    @staticmethod
    def _git_diff_target(target: str) -> str:
        """Extract the diff target after a ``git-diff:``/``git:`` prefix, if any."""
        for prefix in _GIT_DIFF_PREFIXES:
            if target.lower().startswith(prefix):
                remainder = target[len(prefix):]
                return remainder.lstrip(":").strip()
        return ""

    @staticmethod
    def _trim_target(token: str) -> str:
        """Strip trailing sentence punctuation from a matched reference token."""
        return token.rstrip(_TRAILING_PUNCTUATION)

    @staticmethod
    def _describe_error(exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return f"{type(exc).__name__}: {message}"
        return type(exc).__name__

    @staticmethod
    def _unresolved(
        raw: str, target: str, kind: str, *, reason: str
    ) -> ResolvedReference:
        """Build a placeholder result for a reference that could not resolve."""
        placeholder = f"[unresolved context reference {raw} ({kind}): {reason}]"
        return ResolvedReference(
            raw=raw,
            target=target,
            kind=kind,
            resolved=False,
            content=placeholder,
            error=reason,
        )
