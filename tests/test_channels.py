"""
Integration and unit tests for the Hexagonal Chat Channels module.
Tests Core Use Cases, DB Repository Adapter, WebSocket Publisher, and Telegram Adapter.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from harness.data.db import Base
from harness.modules.chat.domain.entities import Message
from harness.modules.chat.ports.inbound import CreateChannelUseCase, JoinChannelUseCase, SendMessageUseCase
from harness.modules.chat.adapters.db_repository import SQLAlchemyChatRepository
from harness.modules.chat.adapters.websocket_publisher import WebSocketChatPublisher
from harness.modules.chat.adapters.telegram_adapter import TelegramAdapter


@pytest.fixture
def mock_mp() -> MagicMock:
    mp = MagicMock()
    mp.ai.is_ready = False
    return mp


# we are using pytest-asyncio auto mode
@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        # Create all tables including our new user, channels, members, messages tables
        await conn.run_sync(Base.metadata.create_all)
        
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_channel_creation_and_membership(async_db):
    repo = SQLAlchemyChatRepository(async_db)
    create_use_case = CreateChannelUseCase(repo)
    
    # 1. Create Channel
    chan = await create_use_case.execute(
        name="test-channel",
        description="A great public channel",
        is_private=False,
        created_by="user_123",
    )
    
    assert chan.id is not None
    assert chan.name == "test-channel"
    assert chan.description == "A great public channel"
    assert chan.is_private is False
    assert chan.created_by == "user_123"
    
    # Verify owner member was automatically created
    member = await repo.get_member(chan.id, "user_123")
    assert member is not None
    assert member.role == "owner"


@pytest.mark.asyncio
async def test_private_channel_permissions(async_db, mock_mp):
    repo = SQLAlchemyChatRepository(async_db)
    create_use_case = CreateChannelUseCase(repo)
    join_use_case = JoinChannelUseCase(repo)
    
    # Create private channel
    chan = await create_use_case.execute(
        name="secret-room",
        description="Private room",
        is_private=True,
        created_by="admin_user",
    )
    
    publisher = WebSocketChatPublisher()
    ai_participant = AsyncMock()
    send_use_case = SendMessageUseCase(repo, publisher, ai_participant)
    
    # Send message as admin should succeed
    msg1 = await send_use_case.execute(
        channel_id=chan.id,
        sender_id="admin_user",
        sender_name="Admin",
        sender_type="human",
        content="Welcome to the secret room",
    )
    assert msg1.id is not None
    
    # Send message as unauthorized user should fail
    with pytest.raises(PermissionError):
        await send_use_case.execute(
            channel_id=chan.id,
            sender_id="intruder_user",
            sender_name="Intruder",
            sender_type="human",
            content="Can I talk here?",
        )
        
    # After joining, intruder should be able to send message
    await join_use_case.execute(channel_id=chan.id, user_id="intruder_user")
    msg2 = await send_use_case.execute(
        channel_id=chan.id,
        sender_id="intruder_user",
        sender_name="Intruder",
        sender_type="human",
        content="Now I can speak!",
    )
    assert msg2.content == "Now I can speak!"


@pytest.mark.asyncio
async def test_websocket_publisher_broadcast():
    publisher = WebSocketChatPublisher()
    
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    
    # Connect
    await publisher.connect("chan_999", ws1)
    await publisher.connect("chan_999", ws2)
    
    # Prepare message event
    msg = Message(
        id="msg_111",
        channel_id="chan_999",
        sender_id="user_abc",
        sender_name="Alice",
        sender_type="human",
        content="Hi all!",
    )
    from harness.modules.chat.domain.entities import MessageSentEvent
    event = MessageSentEvent(message=msg)
    
    await publisher.publish_message_sent(event)
    
    # Verify JSON was sent to both sockets
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()
    
    payload = ws1.send_json.call_args[0][0]
    assert payload["type"] == "message_created"
    assert payload["data"]["content"] == "Hi all!"


@pytest.mark.asyncio
async def test_telegram_adapter_bidirectional(async_db, mock_mp):
    repo = SQLAlchemyChatRepository(async_db)
    publisher = WebSocketChatPublisher()
    ai_participant = AsyncMock()
    
    create_chan = CreateChannelUseCase(repo)
    join_chan = JoinChannelUseCase(repo)
    send_msg = SendMessageUseCase(repo, publisher, ai_participant)
    
    # Instantiate Telegram Adapter
    tg_adapter = TelegramAdapter(repo, send_msg, create_chan, join_chan, bot_token="fake_token")
    
    # Register forwarder
    publisher.register_forwarder(tg_adapter.forward_to_telegram)
    
    # Mock Telegram Bot API sendMessage call
    tg_adapter.forward_to_telegram = AsyncMock()
    
    # Simulate incoming Telegram update
    # Ref: https://core.telegram.org/bots/api#update
    payload = {
        "update_id": 99999,
        "message": {
          "message_id": 12,
          "from": {
            "id": 55555,
            "first_name": "Bob",
            "username": "bob99"
          },
          "chat": {
            "id": -77777,
            "title": "Telegram Dev Channel",
            "type": "group"
          },
          "text": "Hello from Telegram!"
        }
    }
    
    await tg_adapter.handle_webhook(payload)
    
    # 1. Verify channel was created automatically
    chan = await repo.get_channel_by_name("telegram_-77777")
    assert chan is not None
    assert chan.description == "Bridged Telegram Channel: Telegram Dev Channel"
    
    # 2. Verify member was created automatically
    member = await repo.get_member(chan.id, "telegram_55555")
    assert member is not None
    
    # 3. Verify message was saved automatically
    messages = await repo.get_messages(chan.id)
    assert len(messages) == 1
    assert messages[0].content == "Hello from Telegram!"
    assert messages[0].sender_id == "telegram_55555"
    assert messages[0].sender_name == "Bob (@bob99)"
    assert messages[0].sender_type == "telegram"
