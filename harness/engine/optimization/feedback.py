"""FeedbackCollector — collect, store, and integrate user feedback for improvement."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class FeedbackEntry:
    """A single feedback record."""

    id: str
    component_id: str
    component_name: str
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    rating: int = 0  # -1 = thumbs down, 0 = neutral, 1 = thumbs up
    comment: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "component_id": self.component_id,
            "component_name": self.component_name,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "rating": self.rating,
            "comment": self.comment,
            "tags": self.tags,
            "created_at": self.created_at,
        }


class FeedbackCollector:
    """Collects and manages user feedback on AI outputs.

    Stores feedback in JSONL files under `.vloop/feedback/`.
    """

    def __init__(self, storage_dir: Path | str = ".vloop/feedback") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ── Collection ────────────────────────────────────────────────────────────

    def record(
        self,
        component_id: str,
        component_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        rating: int = 0,
        comment: str = "",
        tags: list[str] | None = None,
    ) -> FeedbackEntry:
        """Record a feedback entry."""
        entry = FeedbackEntry(
            id=f"fb_{uuid.uuid4().hex[:12]}",
            component_id=component_id,
            component_name=component_name,
            input_data=input_data,
            output_data=output_data,
            rating=rating,
            comment=comment,
            tags=tags or [],
        )
        self._append(entry)
        return entry

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def list_for_component(self, component_id: str) -> list[FeedbackEntry]:
        return [e for e in self._load_all() if e.component_id == component_id]

    def list_all(self) -> list[FeedbackEntry]:
        return self._load_all()

    def summary_for_component(self, component_id: str) -> dict[str, Any]:
        entries = self.list_for_component(component_id)
        if not entries:
            return {"count": 0, "avg_rating": 0.0, "common_tags": []}
        ratings = [e.rating for e in entries]
        from collections import Counter
        tag_counts = Counter(tag for e in entries for tag in e.tags)
        return {
            "count": len(entries),
            "avg_rating": sum(ratings) / len(ratings),
            "positive": sum(1 for r in ratings if r > 0),
            "negative": sum(1 for r in ratings if r < 0),
            "common_tags": [t for t, _ in tag_counts.most_common(10)],
        }

    # ── Conversion to training examples ───────────────────────────────────────

    def to_examples(self, component_id: str) -> list[dict[str, Any]]:
        """Convert positive feedback entries to training example dicts."""
        entries = [e for e in self.list_for_component(component_id) if e.rating > 0]
        return [
            {
                "inputs": e.input_data,
                "outputs": e.output_data,
                "tags": e.tags,
            }
            for e in entries
        ]

    # ── Persistence ───────────────────────────────────────────────────────────

    def _append(self, entry: FeedbackEntry) -> None:
        file_path = self.storage_dir / f"{entry.component_id}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _load_all(self) -> list[FeedbackEntry]:
        entries: list[FeedbackEntry] = []
        for file_path in self.storage_dir.glob("*.jsonl"):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(FeedbackEntry(**data))
                    except Exception:
                        continue
        return entries
