"""HTML injector — inserts window.__HARNESS__ script block into Vite-served HTML."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

_HEAD_RE = re.compile(r"(<head[^>]*>)", re.IGNORECASE)


class HarnessConfigInjector(BaseModel):
    component_id: str
    api_base: str
    ws_base: str
    initial_state: dict[str, Any]
    permissions: list[str]


def inject_harness_vars(
    html: str,
    config: HarnessConfigInjector,
) -> str:
    """
    Inject ``window.__HARNESS__`` into the <head> of an HTML document.

    If no <head> tag exists the script is prepended to the document.
    """
    payload = {
        "COMPONENT_ID": config.component_id,
        "API_URL": f"{config.api_base}/api/{config.component_id}",
        "WS_URL": f"{config.ws_base}/ws/{config.component_id}",
        "INITIAL_STATE": config.initial_state,
        "PERMISSIONS": config.permissions,
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
