"""ConversationMemory — sliding window + summarization for long conversations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in a conversation."""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
        }


class ConversationMemory:
    """Manages conversation history with automatic summarization.

    When messages exceed ``max_messages``, the oldest messages are
    summarized into a rolling summary that is prepended to the context.
    """

    def __init__(
        self,
        max_messages: int = 20,
        summary_threshold: int = 10,
        summarizer: Any | None = None,
    ) -> None:
        self.max_messages = max_messages
        self.summary_threshold = summary_threshold
        self._messages: list[Message] = []
        self._summary: str = ""
        self._summarizer = summarizer  # DSPy module or callable

    # ── Core API ────────────────────────────────────────────────────────────────

    def add(self, role: str, content: str, **meta: Any) -> None:
        self._messages.append(Message(role=role, content=content, metadata=meta))
        self._prune()

    def add_user(self, content: str, **meta: Any) -> None:
        self.add("user", content, **meta)

    def add_assistant(self, content: str, **meta: Any) -> None:
        self.add("assistant", content, **meta)

    def add_system(self, content: str, **meta: Any) -> None:
        self.add("system", content, **meta)

    def get_context(self, include_summary: bool = True) -> str:
        """Return the conversation as a formatted string."""
        parts: list[str] = []
        if include_summary and self._summary:
            parts.append(f"[Summary of earlier conversation]\n{self._summary}\n")
        for msg in self._messages:
            parts.append(f"{msg.role}: {msg.content}")
        return "\n\n".join(parts)

    def get_messages(self) -> list[dict[str, Any]]:
        """Return raw message dicts (for chat APIs)."""
        messages = []
        if self._summary:
            messages.append({
                "role": "system",
                "content": f"Earlier conversation summary: {self._summary}",
            })
        for msg in self._messages:
            messages.append(msg.to_dict())
        return messages

    def clear(self) -> None:
        self._messages.clear()
        self._summary = ""

    def to_json(self) -> str:
        return json.dumps({
            "summary": self._summary,
            "messages": [m.to_dict() for m in self._messages],
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> ConversationMemory:
        data = json.loads(raw)
        mem = cls()
        mem._summary = data.get("summary", "")
        for m in data.get("messages", []):
            mem.add(m["role"], m["content"], **m.get("metadata", {}))
        return mem

    # ── Pruning / summarization ─────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._messages) <= self.max_messages:
            return

        # Summarize oldest messages
        to_summarize = self._messages[: self.summary_threshold]
        self._messages = self._messages[self.summary_threshold :]
        self._update_summary(to_summarize)

    def _update_summary(self, messages: list[Message]) -> None:
        text = "\n".join(f"{m.role}: {m.content}" for m in messages)
        if self._summarizer is not None:
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                try:
                    if hasattr(self._summarizer, "summarise"):
                        result = loop.run_until_complete(
                            self._summarizer.summarise(text=text, max_words=100)
                        )
                        new_summary = getattr(result, "summary", str(result))
                    else:
                        fn = self._summarizer
                        result = loop.run_until_complete(
                            asyncio.get_event_loop().run_in_executor(None, fn, text)
                        )
                        new_summary = str(result)
                finally:
                    loop.close()
            except Exception:
                new_summary = self._fallback_summary(text)
        else:
            new_summary = self._fallback_summary(text)

        if self._summary:
            self._summary = f"{self._summary}\n{new_summary}"
        else:
            self._summary = new_summary

    @staticmethod
    def _fallback_summary(text: str) -> str:
        """Very simple fallback summarizer."""
        sentences = text.split("\n")
        if len(sentences) > 3:
            return "; ".join(sentences[:3]) + " ..."
        return "; ".join(sentences)
