"""
Outbound Ports (Driven Ports) for Chat Module.
These are abstract interfaces defining the capabilities required from secondary adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from harness.modules.chat.domain.entities import Channel, ChannelMember, Message, User, DomainEvent


class ChatRepositoryPort(ABC):
    @abstractmethod
    async def save_user(self, user: User) -> User:
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> User | None:
        pass

    @abstractmethod
    async def save_channel(self, channel: Channel) -> Channel:
        pass

    @abstractmethod
    async def get_channel(self, channel_id: str) -> Channel | None:
        pass

    @abstractmethod
    async def get_channel_by_name(self, name: str) -> Channel | None:
        pass

    @abstractmethod
    async def list_channels(self, user_id: str) -> Sequence[Channel]:
        """List all public channels and private channels the user has joined."""
        pass

    @abstractmethod
    async def save_member(self, member: ChannelMember) -> ChannelMember:
        pass

    @abstractmethod
    async def get_member(self, channel_id: str, user_id: str) -> ChannelMember | None:
        pass

    @abstractmethod
    async def remove_member(self, channel_id: str, user_id: str) -> None:
        pass

    @abstractmethod
    async def list_members(self, channel_id: str) -> Sequence[ChannelMember]:
        pass

    @abstractmethod
    async def save_message(self, message: Message) -> Message:
        pass

    @abstractmethod
    async def get_messages(self, channel_id: str, limit: int = 100) -> Sequence[Message]:
        pass


class EventPublisherPort(ABC):
    @abstractmethod
    async def publish_message_sent(self, event: MessageSentEvent) -> None:
        """Broadcast real-time message events to connected WebSocket clients."""
        pass


class AIParticipantPort(ABC):
    @abstractmethod
    async def generate_response(self, channel: Channel, message: Message, history: Sequence[Message]) -> str | None:
        """Call the AI engine to generate a reply given the channel, triggering message, and chat history."""
        pass
