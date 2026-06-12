"""
SQLAlchemy database repository adapter for Chat Module.
Implements ChatRepositoryPort interface.
"""

from __future__ import annotations

from typing import Sequence
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.models import UserDB, ChannelDB, ChannelMemberDB, ChannelMessageDB
from harness.modules.chat.domain.entities import Channel, ChannelMember, Message, User
from harness.modules.chat.ports.outbound import ChatRepositoryPort


def _to_domain_user(db_user: UserDB) -> User:
    return User(
        id=db_user.id,
        username=db_user.username,
        role=db_user.role,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
    )


def _to_domain_channel(db_chan: ChannelDB) -> Channel:
    return Channel(
        id=db_chan.id,
        name=db_chan.name,
        description=db_chan.description,
        is_private=db_chan.is_private,
        created_by=db_chan.created_by,
        created_at=db_chan.created_at,
    )


def _to_domain_member(db_mem: ChannelMemberDB) -> ChannelMember:
    return ChannelMember(
        id=db_mem.id,
        channel_id=db_mem.channel_id,
        user_id=db_mem.user_id,
        role=db_mem.role,
        joined_at=db_mem.joined_at,
    )


def _to_domain_message(db_msg: ChannelMessageDB) -> Message:
    return Message(
        id=db_msg.id,
        channel_id=db_msg.channel_id,
        sender_id=db_msg.sender_id,
        sender_name=db_msg.sender_name,
        sender_type=db_msg.sender_type,
        content=db_msg.content,
        created_at=db_msg.created_at,
    )


class SQLAlchemyChatRepository(ChatRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_user(self, user: User) -> User:
        db_user = UserDB(
            id=user.id,
            username=user.username,
            password_hash="external_auth_no_hash",
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )
        self.session.add(db_user)
        await self.session.commit()
        return user

    async def get_user(self, user_id: str) -> User | None:
        db_user = await self.session.get(UserDB, user_id)
        if db_user:
            return _to_domain_user(db_user)
        return None

    async def save_channel(self, channel: Channel) -> Channel:
        db_chan = ChannelDB(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            is_private=channel.is_private,
            created_by=channel.created_by,
            created_at=channel.created_at,
        )
        self.session.add(db_chan)
        await self.session.commit()
        return channel

    async def get_channel(self, channel_id: str) -> Channel | None:
        db_chan = await self.session.get(ChannelDB, channel_id)
        if db_chan:
            return _to_domain_channel(db_chan)
        return None

    async def get_channel_by_name(self, name: str) -> Channel | None:
        stmt = select(ChannelDB).where(ChannelDB.name == name)
        res = await self.session.execute(stmt)
        db_chan = res.scalar_one_or_none()
        if db_chan:
            return _to_domain_channel(db_chan)
        return None

    async def list_channels(self, user_id: str) -> Sequence[Channel]:
        # Return all channels where:
        # 1. is_private is False (public channels)
        # 2. OR user is a member of the private channel
        stmt = (
            select(ChannelDB)
            .outerjoin(ChannelMemberDB, ChannelMemberDB.channel_id == ChannelDB.id)
            .where(
                or_(
                    ChannelDB.is_private == False,  # noqa: E712
                    ChannelMemberDB.user_id == user_id,
                )
            )
            .distinct()
            .order_by(ChannelDB.name)
        )
        res = await self.session.execute(stmt)
        return [_to_domain_channel(c) for c in res.scalars().all()]

    async def save_member(self, member: ChannelMember) -> ChannelMember:
        db_mem = ChannelMemberDB(
            id=member.id,
            channel_id=member.channel_id,
            user_id=member.user_id,
            role=member.role,
            joined_at=member.joined_at,
        )
        self.session.add(db_mem)
        await self.session.commit()
        return member

    async def get_member(self, channel_id: str, user_id: str) -> ChannelMember | None:
        stmt = select(ChannelMemberDB).where(
            ChannelMemberDB.channel_id == channel_id, ChannelMemberDB.user_id == user_id
        )
        res = await self.session.execute(stmt)
        db_mem = res.scalar_one_or_none()
        if db_mem:
            return _to_domain_member(db_mem)
        return None

    async def remove_member(self, channel_id: str, user_id: str) -> None:
        stmt = delete(ChannelMemberDB).where(
            ChannelMemberDB.channel_id == channel_id, ChannelMemberDB.user_id == user_id
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def list_members(self, channel_id: str) -> Sequence[ChannelMember]:
        stmt = select(ChannelMemberDB).where(ChannelMemberDB.channel_id == channel_id)
        res = await self.session.execute(stmt)
        return [_to_domain_member(m) for m in res.scalars().all()]

    async def save_message(self, message: Message) -> Message:
        db_msg = ChannelMessageDB(
            id=message.id,
            channel_id=message.channel_id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            sender_type=message.sender_type,
            content=message.content,
            created_at=message.created_at,
        )
        self.session.add(db_msg)
        await self.session.commit()
        return message

    async def get_messages(self, channel_id: str, limit: int = 100) -> Sequence[Message]:
        stmt = (
            select(ChannelMessageDB)
            .where(ChannelMessageDB.channel_id == channel_id)
            .order_by(ChannelMessageDB.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        # Reverse to get chronological order (oldest to newest)
        msgs = list(res.scalars().all())
        msgs.reverse()
        return [_to_domain_message(m) for m in msgs]
