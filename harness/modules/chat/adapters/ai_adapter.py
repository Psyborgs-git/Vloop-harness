"""
AI participation adapter for Chat Module.
Implements AIParticipantPort and links to VLoop's DSPy AI brain.
"""

from __future__ import annotations

from typing import Any, Sequence

from harness.modules.chat.domain.entities import Channel, Message
from harness.modules.chat.ports.outbound import AIParticipantPort


class AIEngineAdapter(AIParticipantPort):
    def __init__(self, main_process: Any) -> None:
        """Takes the main process instance which hosts the AI engine."""
        self.mp = main_process

    async def generate_response(
        self,
        channel: Channel,
        message: Message,
        history: Sequence[Message],
    ) -> str | None:
        """Call the AI engine to generate a response in context of the channel."""
        if not self.mp or not self.mp.ai.is_ready:
            return (
                "The AI engine is currently unconfigured. "
                "Please configure an AI provider in the Settings page to activate bot responses."
            )

        # Format history: user | assistant style
        history_lines = []
        for m in history:
            # External platforms and humans are treated as User inputs, AI as Assistant
            role = "user" if m.sender_type in ("human", "telegram", "whatsapp") else "assistant"
            history_lines.append(f"{role.capitalize()}: {m.content}")

        # Join everything except the last message which will be passed as the triggering user message
        history_str = "\n".join(history_lines[:-1]) if len(history_lines) > 1 else ""

        try:
            # We can also load existing tools, components and pipelines to give the AI agent standard capabilities
            available_comps = "[]"
            available_pipes = "[]"
            available_tools = "[]"

            try:
                # If repository and registry are active, we can pull them
                # But to keep channel chat fast and robust we default to empty if not fetched
                pass
            except Exception:
                pass

            prediction = await self.mp.ai.chat(
                history=history_str,
                user_message=message.content,
                available_components=available_comps,
                available_pipelines=available_pipes,
                available_tools=available_tools,
            )
            response = getattr(prediction, "response", "") or ""
            return response
        except Exception as e:
            return f"Error communicating with AI engine: {e}"
