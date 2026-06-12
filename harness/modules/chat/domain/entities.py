"""
Pure Domain Entities and Value Objects for Chat Module.
These have absolutely zero external dependencies on databases, frameworks, or libraries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DomainEvent:
    occurred_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MessageSentEvent(DomainEvent):
    message: Message = field(default=None)


@dataclass
class User:
    id: str
    username: str
    role: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Channel:
    id: str
    name: str
    description: str = ""
    is_private: bool = False
    created_by: str = ""  # User ID
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ChannelMember:
    id: str
    channel_id: str
    user_id: str
    role: str = "member"  # owner, admin, member
    joined_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Message:
    id: str
    channel_id: str
    sender_id: str
    sender_name: str
    sender_type: str  # human, ai, telegram, whatsapp
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)
