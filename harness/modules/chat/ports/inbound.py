"""
Inbound Ports (Driving Ports / Use Cases) for Chat Module.
These define the core application services and orchestrate business operations.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Sequence
from datetime import datetime

from harness.modules.chat.domain.entities import Channel, ChannelMember, Message, User, MessageSentEvent
from harness.modules.chat.ports.outbound import ChatRepositoryPort, EventPublisherPort, AIParticipantPort


class CreateChannelUseCase:
    def __init__(self, repo: ChatRepositoryPort) -> None:
        self.repo = repo

    async def execute(self, name: str, description: str, is_private: bool, created_by: str) -> Channel:
        existing = await self.repo.get_channel_by_name(name)
        if existing:
            raise ValueError(f"Channel with name '{name}' already exists")

        channel_id = str(uuid.uuid4())
        channel = Channel(
            id=channel_id,
            name=name,
            description=description,
            is_private=is_private,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        
        await self.repo.save_channel(channel)
        
        # Auto-join the creator as owner
        member = ChannelMember(
            id=str(uuid.uuid4()),
            channel_id=channel_id,
            user_id=created_by,
            role="owner",
            joined_at=datetime.utcnow(),
        )
        await self.repo.save_member(member)
        
        return channel


class JoinChannelUseCase:
    def __init__(self, repo: ChatRepositoryPort) -> None:
        self.repo = repo

    async def execute(self, channel_id: str, user_id: str, role: str = "member") -> ChannelMember:
        channel = await self.repo.get_channel(channel_id)
        if not channel:
            raise ValueError("Channel not found")

        # Check if already a member
        existing = await self.repo.get_member(channel_id, user_id)
        if existing:
            return existing

        member = ChannelMember(
            id=str(uuid.uuid4()),
            channel_id=channel_id,
            user_id=user_id,
            role=role,
            joined_at=datetime.utcnow(),
        )
        return await self.repo.save_member(member)


class SendMessageUseCase:
    def __init__(
        self,
        repo: ChatRepositoryPort,
        publisher: EventPublisherPort,
        ai_participant: AIParticipantPort,
    ) -> None:
        self.repo = repo
        self.publisher = publisher
        self.ai_participant = ai_participant

    async def execute(
        self,
        channel_id: str,
        sender_id: str,
        sender_name: str,
        sender_type: str,
        content: str,
    ) -> Message:
        channel = await self.repo.get_channel(channel_id)
        if not channel:
            raise ValueError("Channel not found")

        # Enforce membership for private channels
        if channel.is_private:
            member = await self.repo.get_member(channel_id, sender_id)
            if not member and sender_type == "human":
                raise PermissionError("Access denied: You are not a member of this private channel")

        msg_id = str(uuid.uuid4())
        message = Message(
            id=msg_id,
            channel_id=channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_type=sender_type,
            content=content,
            created_at=datetime.utcnow(),
        )

        # Save message in repository
        saved_msg = await self.repo.save_message(message)

        # Publish the event to WebSockets
        event = MessageSentEvent(message=saved_msg)
        await self.publisher.publish_message_sent(event)

        # If this message was sent by a human or external adapter and not the AI,
        # check if it should trigger AI participation
        if sender_type != "ai":
            # Fire-and-forget background task to trigger the AI response
            asyncio.create_task(self._handle_ai_trigger(channel, saved_msg))

        return saved_msg

    async def _handle_ai_trigger(self, channel: Channel, message: Message) -> None:
        try:
            # Check if AI should participate.
            # Conditions: channel is public OR direct DM OR bot is mentioned (e.g. '@ai' or '/ai')
            # Let's say: if content starts with "@ai" or contains "/ai" or starts with "/ai" or the channel is named "ai-chat"
            content_lower = message.content.strip().lower()
            is_ai_channel = "ai" in channel.name.lower() or channel.description.lower().startswith("ai")
            bot_mentioned = "@ai" in content_lower or "/ai" in content_lower or "ai bot" in content_lower

            # Force participation on public AI channels or when mentioned anywhere
            if is_ai_channel or bot_mentioned or not channel.is_private:
                # Retrieve recent message history for context
                history = await self.repo.get_messages(channel.id, limit=20)
                
                # Call AI Participant Port to generate response
                ai_reply = await self.ai_participant.generate_response(channel, message, history)
                
                if ai_reply and ai_reply.strip():
                    # Post AI reply by executing this use case
                    await self.execute(
                        channel_id=channel.id,
                        sender_id="ai",
                        sender_name="VLoop AI",
                        sender_type="ai",
                        content=ai_reply,
                    )
        except Exception as e:
            # Prevent background thread crash, log the error
            print(f"Error in SendMessageUseCase background AI trigger: {e}")
            import traceback
            traceback.print_exc()
