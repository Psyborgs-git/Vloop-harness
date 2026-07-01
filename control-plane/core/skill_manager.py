"""Skill catalog with progressive disclosure.

Provides :class:`SkillManager`, which catalogs Skills and decides how much of
each Skill to surface into agent context. Following the progressive-disclosure
model, every catalogued Skill always contributes its name and short
description to context (Requirement 10.2); a Skill's full body is loaded only
when it is determined relevant to the current task, while its name and short
description are retained (Requirement 10.3).

Skill documents follow the `agentskills.io` open standard: a Markdown document
that opens with a ``---``-delimited YAML-ish frontmatter block carrying at
least ``name`` and ``description`` keys, followed by the free-form body of
knowledge content (Requirement 10.4). The parser here is deliberately
*tolerant*: when a document cannot be parsed cleanly because of corruption or
encoding issues, the Skill is still loaded rather than dropped, with the raw
content preserved as its body (Requirement 10.5).

The :func:`parse_skill_document` / :func:`format_skill_document` pair is
canonical so that, for any well-formed document, parsing then formatting then
parsing yields an equivalent :class:`Skill` (the round-trip property required
by the design's Property 27).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

# Frontmatter fence used by the agentskills.io document format.
_FENCE = "---"
# Frontmatter keys recognized by the parser.
_NAME_KEY = "name"
_DESCRIPTION_KEY = "description"


@dataclass(slots=True)
class Skill:
    """A single on-demand knowledge document.

    Carries the three pieces every catalogued Skill needs: a ``name`` and a
    ``short_description`` (always contributed to context) and a ``body`` of
    knowledge content (loaded only when relevant). ``parsed_cleanly`` records
    whether the source document parsed as well-formed agentskills.io content;
    it is ``False`` when the body was loaded from a corrupt or
    encoding-damaged document (Requirement 10.5).
    """

    name: str
    short_description: str
    body: str = ""
    parsed_cleanly: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SkillContextEntry:
    """One Skill's contribution to agent context.

    ``name`` and ``short_description`` are always present. ``body`` is set only
    when the Skill was determined relevant; otherwise it is ``None`` so callers
    can tell "catalogued but not loaded" apart from "loaded with empty body".
    """

    name: str
    short_description: str
    body: str | None = None

    @property
    def is_loaded(self) -> bool:
        """True when the full body has been disclosed into context."""
        return self.body is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_skill_document(document: str | bytes) -> Skill:
    """Parse an agentskills.io Skill document into a :class:`Skill`.

    Accepts either text or raw bytes. The parser tolerates malformed input:
    rather than raising, it falls back to loading the raw content as the body
    so a Skill is never dropped because of corruption or encoding issues
    (Requirement 10.5). ``parsed_cleanly`` reflects whether a well-formed
    frontmatter block was recognized.
    """
    text, decoded_cleanly = _coerce_text(document)

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        # No recognizable frontmatter: keep the whole document as the body so
        # the Skill is still usable, but flag it as not cleanly parsed.
        return Skill(
            name="",
            short_description="",
            body=text,
            parsed_cleanly=False,
        )

    fields, fields_ok = _parse_frontmatter(frontmatter)
    parsed_cleanly = decoded_cleanly and fields_ok and _NAME_KEY in fields
    return Skill(
        name=fields.get(_NAME_KEY, ""),
        short_description=fields.get(_DESCRIPTION_KEY, ""),
        body=body,
        parsed_cleanly=parsed_cleanly,
    )


def format_skill_document(skill: Skill) -> str:
    """Render a :class:`Skill` back into a canonical agentskills.io document.

    The output is the inverse of :func:`parse_skill_document` for well-formed
    Skills, guaranteeing the parse/format/parse round-trip property.
    """
    lines = [
        _FENCE,
        f"{_NAME_KEY}: {skill.name}",
        f"{_DESCRIPTION_KEY}: {skill.short_description}",
        _FENCE,
    ]
    document = "\n".join(lines)
    if skill.body:
        document = f"{document}\n{skill.body}"
    return document


def _coerce_text(document: str | bytes) -> tuple[str, bool]:
    """Return ``(text, decoded_cleanly)`` for a str or bytes document.

    Bytes are decoded as UTF-8; on failure we decode with replacement so the
    content is preserved and report that decoding was not clean
    (Requirement 10.5).
    """
    if isinstance(document, str):
        return document, True
    try:
        return document.decode("utf-8"), True
    except UnicodeDecodeError:
        return document.decode("utf-8", errors="replace"), False


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a document into ``(frontmatter, body)``.

    Recognizes a leading ``---`` fence, a frontmatter block, and a closing
    ``---`` fence. Returns ``(None, text)`` when no closed frontmatter block is
    present so the caller can fall back to raw loading.
    """
    stripped = text.lstrip("\n")
    lines = stripped.split("\n")
    if not lines or lines[0].strip() != _FENCE:
        return None, text

    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body

    # Opening fence with no closing fence: treat as unparseable.
    return None, text


def _parse_frontmatter(frontmatter: str) -> tuple[dict[str, str], bool]:
    """Parse ``key: value`` frontmatter lines into a dict.

    Returns ``(fields, ok)`` where ``ok`` is ``False`` if any non-blank line
    did not look like a ``key: value`` pair, signaling a corrupt block.
    """
    fields: dict[str, str] = {}
    ok = True
    for line in frontmatter.split("\n"):
        if line.strip() == "":
            continue
        key, sep, value = line.partition(":")
        if not sep or key.strip() == "":
            ok = False
            continue
        fields[key.strip()] = value.strip()
    return fields, ok


class SkillManager:
    """Catalogs Skills and builds progressive-disclosure agent context."""

    def __init__(self, skills: Iterable[Skill] | None = None) -> None:
        # Keyed by name to keep the catalog deduplicated and look-up fast.
        self._catalog: dict[str, Skill] = {}
        for skill in skills or ():
            self.register(skill)

    def register(self, skill: Skill) -> None:
        """Add or replace a Skill in the catalog, keyed by its name."""
        self._catalog[skill.name] = skill

    def register_document(self, document: str | bytes) -> Skill:
        """Parse a Skill document and register the resulting Skill."""
        skill = parse_skill_document(document)
        self.register(skill)
        return skill

    def get(self, name: str) -> Skill | None:
        """Return the catalogued Skill with ``name`` or ``None``."""
        return self._catalog.get(name)

    @property
    def skills(self) -> list[Skill]:
        """All catalogued Skills, in registration order."""
        return list(self._catalog.values())

    def build_context(
        self,
        relevant_skills: Iterable[str] | None = None,
        *,
        is_relevant: Callable[[Skill], bool] | None = None,
    ) -> list[SkillContextEntry]:
        """Build the Skill contribution to agent context.

        Every catalogued Skill always contributes its name and short
        description (Requirement 10.2). A Skill's full body is additionally
        loaded only when it is determined relevant, while its name and short
        description are retained (Requirement 10.3).

        Relevance can be supplied as an explicit set of Skill names
        (``relevant_skills``) and/or a predicate over Skills (``is_relevant``).
        A Skill is loaded if either source marks it relevant. When neither is
        given, no bodies are loaded.
        """
        relevant_names = set(relevant_skills or ())
        entries: list[SkillContextEntry] = []
        for skill in self._catalog.values():
            loaded = skill.name in relevant_names or (
                is_relevant is not None and is_relevant(skill)
            )
            entries.append(
                SkillContextEntry(
                    name=skill.name,
                    short_description=skill.short_description,
                    body=skill.body if loaded else None,
                )
            )
        return entries
