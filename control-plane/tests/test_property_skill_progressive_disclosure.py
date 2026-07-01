"""Property-based test for Skill_Manager progressive disclosure.

# Feature: orchestration-engine-completion, Property 26: Skill progressive disclosure

Property 26 states that *for any* skill catalog, building agent context always
includes the name and short description of every catalogued skill, and for any
skill determined relevant its full body is additionally loaded while its name
and short description are retained.

This test generates random skill catalogs together with a random relevant
subset (the ``skill_catalogs()`` strategy), builds context via
:meth:`SkillManager.build_context`, and asserts the two halves of the property:

* every catalogued skill always contributes its name + short_description into
  context, regardless of relevance (Requirement 10.2); and
* a skill's full body is loaded into context (``entry.body == skill.body`` and
  ``entry.is_loaded``) ONLY when the skill is relevant; otherwise ``entry.body``
  is ``None`` while name + short_description are still retained
  (Requirement 10.3).

**Validates: Requirements 10.2, 10.3**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.skill_manager import Skill, SkillManager

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Skill names key the catalog, so within a single catalog they must be unique.
# Keep them short and from a constrained alphabet so the generator can cheaply
# build distinct sets while still exercising a range of values.
_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
    min_size=1,
    max_size=12,
)
# Bodies may be empty; an empty body is a meaningful case because an unloaded
# entry's body must be ``None`` (not "") so callers can distinguish
# "catalogued but not loaded" from "loaded with an empty body".
_bodies = st.text(max_size=40)
_descriptions = st.text(max_size=30)


@st.composite
def skill_catalogs(draw: st.DrawFn) -> tuple[list[Skill], set[str]]:
    """Generate a random skill set plus a random relevant subset of names.

    Returns ``(skills, relevant_names)`` where ``skills`` is a list of
    name-unique :class:`Skill` objects and ``relevant_names`` is an arbitrary
    subset of those names (possibly empty, possibly all).
    """
    names = draw(
        st.lists(_names, min_size=0, max_size=8, unique=True)
    )
    skills = [
        Skill(
            name=name,
            short_description=draw(_descriptions),
            body=draw(_bodies),
        )
        for name in names
    ]
    # Choose an arbitrary subset of the catalogued names as "relevant".
    relevant_names = set(
        draw(st.lists(st.sampled_from(names), unique=True)) if names else []
    )
    return skills, relevant_names


# ---------------------------------------------------------------------------
# Property 26: Skill progressive disclosure
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(catalog=skill_catalogs())
def test_skill_progressive_disclosure(catalog: tuple[list[Skill], set[str]]) -> None:
    """Names/descriptions always surface; bodies surface only when relevant."""
    skills, relevant_names = catalog
    manager = SkillManager(skills)

    entries = manager.build_context(relevant_names)

    # Context must cover exactly the catalogued skills (one entry per skill).
    skills_by_name = {skill.name: skill for skill in skills}
    entries_by_name = {entry.name: entry for entry in entries}
    assert set(entries_by_name) == set(skills_by_name)
    assert len(entries) == len(skills_by_name)

    for name, skill in skills_by_name.items():
        entry = entries_by_name[name]

        # Req 10.2: name + short_description always present, regardless of
        # relevance.
        assert entry.name == skill.name
        assert entry.short_description == skill.short_description

        if name in relevant_names:
            # Req 10.3: relevant skills load their full body, while name and
            # short_description are retained (asserted above).
            assert entry.is_loaded
            assert entry.body == skill.body
        else:
            # Req 10.3 (converse): non-relevant skills do NOT load their body;
            # body is None while name + short_description are still retained.
            assert not entry.is_loaded
            assert entry.body is None
