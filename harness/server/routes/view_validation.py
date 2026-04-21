"""Shared validation and code-generation helpers for view stubs.

These utilities are used by both ``views_routes.py`` and ``chat_routes.py``
to avoid duplication when generating and validating AI-produced React stubs.
"""

from __future__ import annotations

import re


# ── Component name validation ─────────────────────────────────────────────────

_COMPONENT_NAME_RE = re.compile(r"^[A-Z][a-zA-Z0-9]{1,63}$")

# Patterns that must not appear in generated React code (security baseline)
_BANNED_PATTERNS = [
    r"require\s*\(\s*['\"]child_process",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"process\.env",
    r"__dirname",
    r"__filename",
    r"require\s*\(\s*['\"]fs['\"]",
    r"require\s*\(\s*['\"]path['\"]",
]


def validate_component_name(name: str) -> str:
    """Return the cleaned name or raise ``ValueError`` if unsafe.

    Must be PascalCase: starts with an uppercase letter, contains only
    letters/digits, and is between 2 and 64 characters.
    """
    clean = name.strip()
    if not _COMPONENT_NAME_RE.match(clean):
        raise ValueError(
            f"component_name must be PascalCase [A-Z][a-zA-Z0-9]{{1,63}}, got {clean!r}"
        )
    return clean


def validate_react_code(code: str) -> None:
    """Raise ``ValueError`` if ``code`` contains any disallowed patterns."""
    for pattern in _BANNED_PATTERNS:
        if re.search(pattern, code):
            raise ValueError(
                f"Generated code contains a disallowed pattern: {pattern!r}"
            )


# ── File writing helper ───────────────────────────────────────────────────────

def write_view_stub(react_root: "Any", component_name: str, react_code: str) -> str | None:  # noqa: F821
    """Write ``App.tsx`` (and a ``main.tsx`` entry) under ``react_root/{component_name}/``.

    Returns the absolute path of the written ``App.tsx``, or ``None`` if writing
    fails (failure is intentionally non-fatal).

    ``react_root`` should be a :class:`pathlib.Path` pointing at
    ``react/src/components/generated/``.
    """
    from pathlib import Path

    try:
        comp_dir = Path(react_root) / component_name
        comp_dir.mkdir(parents=True, exist_ok=True)
        app_tsx = comp_dir / "App.tsx"
        app_tsx.write_text(react_code, encoding="utf-8")
        main_tsx = comp_dir / "main.tsx"
        if not main_tsx.exists():
            main_tsx.write_text(
                f'import React from "react";\n'
                f'import ReactDOM from "react-dom/client";\n'
                f'import {component_name} from "./App";\n\n'
                f'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
                f'  <React.StrictMode>\n'
                f'    <{component_name} />\n'
                f'  </React.StrictMode>\n'
                f');\n',
                encoding="utf-8",
            )
        return str(app_tsx)
    except Exception:
        return None
