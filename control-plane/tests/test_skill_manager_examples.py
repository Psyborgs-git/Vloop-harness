"""Example-based unit tests for the Skill_Manager (`core/skill_manager.py`).

Covers task 21.4 with concrete examples:

* Req 10.1 - the catalog maintains each Skill's ``name``, ``short_description``,
  and ``body``; ``SkillManager`` round-trips those fields through registration
  and lookup, and ``build_context`` surfaces name + short_description for every
  catalogued Skill.
* Req 10.5 - a corrupt/garbled agentskills.io document still loads, with its
  raw content preserved as the Skill ``body`` and ``parsed_cleanly`` flagged
  ``False``. Covers bad frontmatter, undecodable bytes, and a missing closing
  fence.
"""

from __future__ import annotations

from core.skill_manager import (
    Skill,
    SkillManager,
    parse_skill_document,
)


# ---------------------------------------------------------------------------
# Req 10.1: catalog shape - name + short_description + body maintained
# ---------------------------------------------------------------------------


def test_catalog_maintains_name_description_and_body():
    """Each catalogued Skill keeps its name, short_description, and body."""
    skill = Skill(
        name="git-basics",
        short_description="How to use common git commands.",
        body="# Git Basics\n\nUse `git status` to inspect the working tree.",
    )
    manager = SkillManager([skill])

    stored = manager.get("git-basics")
    assert stored is not None
    assert stored.name == "git-basics"
    assert stored.short_description == "How to use common git commands."
    assert stored.body == "# Git Basics\n\nUse `git status` to inspect the working tree."


def test_catalog_holds_multiple_skills_with_intact_fields():
    """A multi-skill catalog preserves every skill's three fields verbatim."""
    skills = [
        Skill(name="alpha", short_description="first skill", body="alpha body"),
        Skill(name="beta", short_description="second skill", body="beta body"),
        Skill(name="gamma", short_description="third skill", body=""),
    ]
    manager = SkillManager(skills)

    by_name = {s.name: s for s in manager.skills}
    assert set(by_name) == {"alpha", "beta", "gamma"}
    assert by_name["alpha"].short_description == "first skill"
    assert by_name["alpha"].body == "alpha body"
    assert by_name["beta"].short_description == "second skill"
    assert by_name["beta"].body == "beta body"
    # An empty body is a valid, distinct value and must be preserved as-is.
    assert by_name["gamma"].short_description == "third skill"
    assert by_name["gamma"].body == ""


def test_build_context_surfaces_name_and_description_for_every_skill():
    """The catalog contributes name + short_description for all skills (Req 10.1/10.2)."""
    skills = [
        Skill(name="a", short_description="desc a", body="body a"),
        Skill(name="b", short_description="desc b", body="body b"),
    ]
    manager = SkillManager(skills)

    entries = {e.name: e for e in manager.build_context()}
    assert set(entries) == {"a", "b"}
    assert entries["a"].short_description == "desc a"
    assert entries["b"].short_description == "desc b"


def test_parsed_document_populates_catalog_fields():
    """A well-formed agentskills.io document yields a fully-populated catalog entry."""
    document = (
        "---\n"
        "name: deploy-guide\n"
        "description: Steps to deploy the service.\n"
        "---\n"
        "Run the deploy script and watch the logs."
    )
    manager = SkillManager()
    skill = manager.register_document(document)

    assert skill.parsed_cleanly is True
    stored = manager.get("deploy-guide")
    assert stored is not None
    assert stored.name == "deploy-guide"
    assert stored.short_description == "Steps to deploy the service."
    assert stored.body == "Run the deploy script and watch the logs."


# ---------------------------------------------------------------------------
# Req 10.5: corrupt agentskills.io documents still load with raw body
# ---------------------------------------------------------------------------


def test_missing_closing_fence_still_loads_with_raw_body():
    """A document whose frontmatter fence is never closed still loads."""
    document = (
        "---\n"
        "name: broken\n"
        "description: never closes the fence\n"
        "the body bleeds into the frontmatter region"
    )
    skill = parse_skill_document(document)

    # The skill is not dropped: the raw content is preserved as the body.
    assert skill.parsed_cleanly is False
    assert skill.body == document


def test_bad_frontmatter_still_loads_and_is_flagged():
    """Frontmatter with non ``key: value`` lines parses tolerantly, not cleanly."""
    document = (
        "---\n"
        "this line has no colon separator\n"
        "%%% garbage %%%\n"
        "---\n"
        "real body content"
    )
    skill = parse_skill_document(document)

    # Corruption is detected (no clean parse) but the body is still loaded.
    assert skill.parsed_cleanly is False
    assert skill.body == "real body content"


def test_no_frontmatter_at_all_keeps_whole_document_as_body():
    """A plain document with no frontmatter fence is loaded as raw body."""
    document = "Just some free-form notes with no frontmatter block at all."
    skill = parse_skill_document(document)

    assert skill.parsed_cleanly is False
    assert skill.body == document


def test_undecodable_bytes_still_load_with_replacement():
    """Undecodable bytes are preserved (with replacement) rather than dropped."""
    # 0xFF is not valid UTF-8; the parser must not raise and must keep content.
    raw = b"---\nname: bytes-skill\ndescription: has bad bytes \xff\xfe\n---\nbody text"
    skill = parse_skill_document(raw)

    # Decoding was not clean, so the skill is flagged even though a frontmatter
    # block was structurally present.
    assert skill.parsed_cleanly is False
    # The body content survives decoding.
    assert "body text" in skill.body


def test_corrupt_skill_is_registered_in_catalog():
    """A corrupt document still ends up catalogued via register_document (Req 10.5)."""
    manager = SkillManager()
    skill = manager.register_document("---\nname: half\nno closing fence here")

    # Even with corruption, the skill is registered and retains its raw body.
    assert skill.parsed_cleanly is False
    stored = manager.get(skill.name)
    assert stored is not None
    assert stored.body == "---\nname: half\nno closing fence here"
