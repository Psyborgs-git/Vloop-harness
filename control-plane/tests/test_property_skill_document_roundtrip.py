# Feature: orchestration-engine-completion, Property 27: Skill document round-trip
"""Property-based test for the Skill document round-trip property.

Property 27 states that *for any* skill document conforming to the
agentskills.io standard, parsing then formatting then parsing produces an
equivalent parsed skill.

Because :func:`format_skill_document` is the canonical inverse of
:func:`parse_skill_document` for well-formed documents, this is exercised here
by generating well-formed :class:`Skill` objects directly (the
``skill_documents()`` strategy) and asserting two things:

* ``parse(format(skill)) == skill`` -- formatting a well-formed Skill and
  parsing it back reproduces the original Skill (the parsed result is also
  flagged ``parsed_cleanly``); and
* ``parse(format(parse(doc))) == parse(doc)`` -- the design's stated
  parse->format->parse round-trip is stable for the formatted document.

**Validates: Requirements 10.4**
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from core.skill_manager import (
    Skill,
    format_skill_document,
    parse_skill_document,
)

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# ``name`` and ``short_description`` are emitted into the frontmatter as a
# single ``key: value`` line, and the parser strips surrounding whitespace from
# each value. So for a well-formed document these fields must be single-line
# and free of leading/trailing whitespace; otherwise the round-trip would
# legitimately differ. We draw from a rich inline alphabet (including ``:`` to
# exercise the parser's first-colon split) and strip the result.
_INLINE_ALPHABET = string.ascii_letters + string.digits + " :-_./@#"


def _inline_text(*, min_size: int) -> st.SearchStrategy[str]:
    """Single-line text with no leading/trailing whitespace.

    Maps an arbitrary inline string through ``str.strip`` so the generated
    value matches what the parser would recover, and filters to honor the
    requested minimum length after stripping.
    """
    return (
        st.text(alphabet=_INLINE_ALPHABET, max_size=40)
        .map(str.strip)
        .filter(lambda s: len(s) >= min_size)
    )


# Bodies are free-form knowledge content emitted verbatim after the closing
# fence, so they may contain newlines and arbitrary text (including empty).
# The split/join used by the parser preserves these exactly.
_bodies = st.text(max_size=80)


@st.composite
def skill_documents(draw: st.DrawFn) -> Skill:
    """Generate a well-formed agentskills.io Skill.

    A well-formed Skill carries a non-empty single-line ``name``, a
    (possibly empty) single-line ``short_description``, and a free-form
    ``body``. These constraints mirror exactly what a conforming
    agentskills.io document can represent, so formatting then parsing is a
    lossless round-trip.
    """
    return Skill(
        name=draw(_inline_text(min_size=1)),
        short_description=draw(_inline_text(min_size=0)),
        body=draw(_bodies),
    )


# ---------------------------------------------------------------------------
# Property 27: Skill document round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(skill=skill_documents())
def test_skill_document_round_trip(skill: Skill) -> None:
    """parse(format(skill)) reproduces an equivalent, cleanly-parsed Skill."""
    document = format_skill_document(skill)
    parsed = parse_skill_document(document)

    # Formatting a well-formed Skill and parsing it back yields the original.
    assert parsed == skill
    # A well-formed document must parse cleanly.
    assert parsed.parsed_cleanly

    # The design's stated parse -> format -> parse round-trip is stable.
    reparsed = parse_skill_document(format_skill_document(parsed))
    assert reparsed == parsed
