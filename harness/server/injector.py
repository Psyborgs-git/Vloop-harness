"""HTML injector — inserts window.__HARNESS__ script block into Vite-served HTML."""

from __future__ import annotations

import json
import re
from typing import Any


_HEAD_RE = re.compile(r"(<head[^>]*>)", re.IGNORECASE)


def inject_harness_vars(
    html: str,
    component_id: str,
    api_base: str,
    ws_base: str,
    initial_state: dict[str, Any],
    permissions: list[str],
) -> str:
    """
    Inject ``window.__HARNESS__`` into the <head> of an HTML document.

    If no <head> tag exists the script is prepended to the document.
    """
    payload = {
        "COMPONENT_ID": component_id,
        "API_URL": f"{api_base}/api/{component_id}",
        "WS_URL": f"{ws_base}/ws/{component_id}",
        "INITIAL_STATE": initial_state,
        "PERMISSIONS": permissions,
    }
    script = (
        "<script>\n"
        f"  window.__HARNESS__ = {json.dumps(payload, indent=2)};\n"
        "</script>\n"
    )

    match = _HEAD_RE.search(html)
    if match:
        insert_pos = match.end()
        return html[:insert_pos] + "\n" + script + html[insert_pos:]
    return script + html
