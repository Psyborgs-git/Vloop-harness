# Feature: orchestration-engine-completion, Property 31: Context references resolve, inject actual content, and degrade gracefully
"""Property-based test for Context_Reference resolution and graceful degradation.

Property 31 states that *for any* agent input containing Context_References,
each resolvable reference's concrete content (kernel-provided text for
file/folder references) is injected into the agent context, while each
unresolvable reference injects a descriptive placeholder identifying the
reference and the remaining references are still processed.

The ``context_reference_sets()`` strategy builds an agent input string by
interleaving plain words with a mix of resolvable and unresolvable
``@``-references drawn against a mock kernel filesystem with known and unknown
targets. Each generated example carries the input ``text`` together with the
ground-truth expectations (which references should resolve, to what content)
so the test can assert both the injected content and the resolved/unresolved
counts.

**Validates: Requirements 12.1, 12.2, 12.3**
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field

from hypothesis import given, settings
from hypothesis import strategies as st

from core.context_resolver import ContextResolver


class FakeKernelFilesystem:
    """In-memory stand-in for the kernel-managed filesystem access interface.

    Mirrors the fake used in ``test_context_resolver.py``: ``read_file`` raises
    for unknown paths so unresolvable references degrade gracefully (Req 12.3),
    and returns the stored content for known paths so resolvable references
    inject actual content (Req 12.1, 12.2).
    """

    def __init__(self, *, files: dict[str, str] | None = None) -> None:
        self.files = files or {}

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"no such file: {path}")
        return self.files[path]

    def read_folder(self, path: str) -> str:
        raise FileNotFoundError(f"no such folder: {path}")

    def read_git_diff(self, target: str) -> str:
        return ""

    def read_url(self, url: str) -> str:
        raise ConnectionError(f"unreachable: {url}")

    def path_exists(self, path: str) -> bool:
        return path in self.files


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Target path segments are restricted to characters that survive the resolver's
# tokenization unchanged: no whitespace (which would terminate the token) and
# no trailing-punctuation characters (which the resolver trims). This keeps the
# raw ``@target`` round-trip exact so expectations stay precise.
_SAFE_TARGET_CHARS = string.ascii_letters + string.digits + "_-/"

_safe_segment = st.text(alphabet=_SAFE_TARGET_CHARS, min_size=1, max_size=12).filter(
    # A target ending in "/" is classified as a folder, not a file; keep file
    # targets unambiguous by disallowing a trailing slash here.
    lambda s: not s.endswith("/")
)

# Plain filler words that contain no ``@`` so they are never seen as references.
_plain_word = st.text(
    alphabet=string.ascii_letters + string.digits + ".,;:!?", min_size=1, max_size=8
).filter(lambda s: "@" not in s)

# File content that the resolver will treat as resolvable (must be non-empty;
# the resolver treats empty content as unresolved per Req 12.3).
_file_content = st.text(min_size=1, max_size=30)


@dataclass(slots=True)
class ReferenceCase:
    """A generated agent input plus ground-truth resolution expectations."""

    text: str
    files: dict[str, str]
    # target -> expected injected content, for every reference that should
    # resolve to actual content (Req 12.1, 12.2).
    expected_resolved: dict[str, str] = field(default_factory=dict)
    # targets of references that must fall back to a placeholder (Req 12.3).
    expected_unresolved: list[str] = field(default_factory=list)
    # total references expected to appear in the resolved output, in order.
    total_references: int = 0


@st.composite
def context_reference_sets(draw: st.DrawFn) -> ReferenceCase:
    """Generate agent input text mixing resolvable and unresolvable refs.

    Builds a known mock filesystem and an input string by interleaving plain
    words with ``@``-references. Some references target files present in the
    mock filesystem (resolvable -> actual content injected) and some target
    paths that are deliberately absent (unresolvable -> placeholder injected).
    Returns the input text alongside the exact expectations.
    """
    # Draw a set of resolvable file targets (unique paths) with their content.
    num_resolvable = draw(st.integers(min_value=0, max_value=4))
    resolvable_targets: dict[str, str] = {}
    for _ in range(num_resolvable):
        target = draw(_safe_segment)
        if target in resolvable_targets:
            continue
        resolvable_targets[target] = draw(_file_content)

    # Draw a set of unresolvable targets guaranteed absent from the filesystem.
    num_unresolvable = draw(st.integers(min_value=0, max_value=4))
    unresolvable_targets: list[str] = []
    for _ in range(num_unresolvable):
        target = draw(_safe_segment.filter(lambda s: s not in resolvable_targets))
        if target in unresolvable_targets:
            continue
        unresolvable_targets.append(target)

    # Ensure at least one reference exists so the property is non-trivial.
    if not resolvable_targets and not unresolvable_targets:
        target = draw(_safe_segment)
        resolvable_targets[target] = draw(_file_content)

    # Build an ordered token stream: each reference token, optionally separated
    # by plain filler words. Reference order is randomized across resolvable and
    # unresolvable targets.
    ref_tokens = [(t, True) for t in resolvable_targets] + [
        (t, False) for t in unresolvable_targets
    ]
    ref_tokens = draw(st.permutations(ref_tokens))

    parts: list[str] = []
    for target, _is_resolvable in ref_tokens:
        # Optional leading filler word (kept whitespace-separated so the ``@``
        # remains anchored on a whitespace boundary as the resolver requires).
        if draw(st.booleans()):
            parts.append(draw(_plain_word))
        parts.append(f"@{target}")
    # Optional trailing filler word.
    if draw(st.booleans()):
        parts.append(draw(_plain_word))

    text = " ".join(parts)

    return ReferenceCase(
        text=text,
        files=dict(resolvable_targets),
        expected_resolved=dict(resolvable_targets),
        expected_unresolved=list(unresolvable_targets),
        total_references=len(ref_tokens),
    )


# ---------------------------------------------------------------------------
# Property 31: Context references resolve, inject actual content, and degrade
#              gracefully
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(case=context_reference_sets())
def test_context_references_resolve_and_degrade_gracefully(case: ReferenceCase) -> None:
    """Resolvable refs inject content; unresolvable refs degrade gracefully."""
    fs = FakeKernelFilesystem(files=case.files)
    resolver = ContextResolver(fs)

    result = resolver.resolve_text(case.text)

    # The resolver discovered exactly the references we planted (Req 12.1).
    assert len(result.references) == case.total_references

    resolved_refs = [r for r in result.references if r.resolved]
    unresolved_refs = [r for r in result.references if not r.resolved]

    # The resolved/unresolved counts match expectations.
    assert len(resolved_refs) == len(case.expected_resolved)
    assert len(unresolved_refs) == len(case.expected_unresolved)

    # Every resolvable reference injected the actual kernel-provided content
    # (Req 12.1, 12.2), both on the ResolvedReference and in the output text.
    for ref in resolved_refs:
        expected_content = case.expected_resolved[ref.target]
        assert ref.content == expected_content
        assert expected_content in result.text

    # Every unresolvable reference injected a descriptive placeholder that
    # identifies the unresolved reference, and processing continued (Req 12.3).
    for ref in unresolved_refs:
        assert ref.target in case.expected_unresolved
        placeholder = f"[unresolved context reference @{ref.target}"
        assert ref.content.startswith(placeholder)
        assert ref.error is not None
        # The raw ``@target`` token was replaced by the placeholder, not left
        # verbatim in the output.
        assert placeholder in result.text

    # has_unresolved reflects whether any reference degraded gracefully.
    assert result.has_unresolved == (len(unresolved_refs) > 0)
