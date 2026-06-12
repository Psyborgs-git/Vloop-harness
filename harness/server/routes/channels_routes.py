"""
FastAPI routing controllers for multi-user Chat Channels.
Exposes REST APIs, WebSockets, and External Webhooks (Telegram).
"""

from __future__ import annotations

from typing import Any, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.server.routes.auth_routes import get_current_user
from harness.core.auth import User as AuthUser

# Hexagonal Core Domain & Ports
from harness.modules.chat.domain.entities import Channel, Message, ChannelMember
from harness.modules.chat.ports.outbound import ChatRepositoryPort
from harness.modules.chat.ports.inbound import CreateChannelUseCase, JoinChannelUseCase, SendMessageUseCase

# Hexagonal Adapters
from harness.modules.chat.adapters.db_repository import SQLAlchemyChatRepository
from harness.modules.chat.adapters.ai_adapter import AIEngineAdapter
from harness.modules.chat.adapters.websocket_publisher import get_chat_ws_publisher
from harness.modules.chat.adapters.telegram_adapter import TelegramAdapter

router = APIRouter(prefix="/api/channels", tags=["channels"])


# ── Request / Response schemas ────────────────────────────────────────────────


class ChannelCreateRequest(BaseModel):
    name: str
    description: str = ""
    is_private: bool = False


class ChannelJoinResponse(BaseModel):
    id: str
    channel_id: str
    user_id: str
    role: str


class ChannelMessageCreateRequest(BaseModel):
    content: str


# ── Hexagonal Dependency Resolvers ────────────────────────────────────────────


async def get_chat_repo(db: AsyncSession = Depends(get_session)) -> SQLAlchemyChatRepository:
    return SQLAlchemyChatRepository(db)


async def get_create_channel_use_case(
    repo: ChatRepositoryPort = Depends(get_chat_repo),
) -> CreateChannelUseCase:
    return CreateChannelUseCase(repo)


async def get_join_channel_use_case(
    repo: ChatRepositoryPort = Depends(get_chat_repo),
) -> JoinChannelUseCase:
    return JoinChannelUseCase(repo)


async def get_send_message_use_case(
    request: Request,
    repo: ChatRepositoryPort = Depends(get_chat_repo),
) -> SendMessageUseCase:
    publisher = get_chat_ws_publisher()
    main_process = request.app.state.main_process
    ai_participant = AIEngineAdapter(main_process)
    return SendMessageUseCase(repo, publisher, ai_participant)


async def get_telegram_adapter(
    repo: ChatRepositoryPort = Depends(get_chat_repo),
    send_msg: SendMessageUseCase = Depends(get_send_message_use_case),
    create_chan: CreateChannelUseCase = Depends(get_create_channel_use_case),
    join_chan: JoinChannelUseCase = Depends(get_join_channel_use_case),
) -> TelegramAdapter:
    adapter = TelegramAdapter(repo, send_msg, create_chan, join_chan)
    publisher = get_chat_ws_publisher()
    
    # Wire up the outbound Telegram forwarding listener once
    if not hasattr(publisher, "_telegram_registered"):
        publisher.register_forwarder(adapter.forward_to_telegram)
        publisher._telegram_registered = True
        
    return adapter


# ── REST Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=List[Any])
async def list_channels(
    current_user: AuthUser = Depends(get_current_user),
    repo: ChatRepositoryPort = Depends(get_chat_repo),
):
    """List all channels accessible to the current user."""
    channels = await repo.list_channels(current_user.id)
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "is_private": c.is_private,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat(),
        }
        for c in channels
    ]


@router.post("", status_code=201)
async def create_channel(
    body: ChannelCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    use_case: CreateChannelUseCase = Depends(get_create_channel_use_case),
):
    """Create a new channel and automatically join as the owner."""
    try:
        channel = await use_case.execute(
            name=body.name,
            description=body.description,
            is_private=body.is_private,
            created_by=current_user.id,
        )
        return {
            "id": channel.id,
            "name": channel.name,
            "description": channel.description,
            "is_private": channel.is_private,
            "created_by": channel.created_by,
            "created_at": channel.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{channel_id}/join", response_model=ChannelJoinResponse)
async def join_channel(
    channel_id: str,
    current_user: AuthUser = Depends(get_current_user),
    use_case: JoinChannelUseCase = Depends(get_join_channel_use_case),
):
    """Join a specific channel."""
    try:
        member = await use_case.execute(channel_id=channel_id, user_id=current_user.id)
        return {
            "id": member.id,
            "channel_id": member.channel_id,
            "user_id": member.user_id,
            "role": member.role,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{channel_id}/messages", response_model=List[Any])
async def list_channel_messages(
    channel_id: str,
    limit: int = 100,
    current_user: AuthUser = Depends(get_current_user),
    repo: ChatRepositoryPort = Depends(get_chat_repo),
):
    """Retrieve history of messages for a channel."""
    # Ensure authorized access to private channels
    channel = await repo.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    if channel.is_private:
        member = await repo.get_member(channel_id, current_user.id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this private channel",
            )

    messages = await repo.get_messages(channel_id, limit=limit)
    return [
        {
            "id": m.id,
            "channel_id": m.channel_id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "sender_type": m.sender_type,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.post("/{channel_id}/messages", status_code=201)
async def send_channel_message(
    channel_id: str,
    body: ChannelMessageCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    use_case: SendMessageUseCase = Depends(get_send_message_use_case),
):
    """Post a message to a channel."""
    try:
        message = await use_case.execute(
            channel_id=channel_id,
            sender_id=current_user.id,
            sender_name=current_user.username,
            sender_type="human",
            content=body.content,
        )
        return {
            "id": message.id,
            "channel_id": message.channel_id,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "sender_type": message.sender_type,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── Webhook Endpoints ─────────────────────────────────────────────────────────


@router.post("/telegram/webhook", status_code=200)
async def telegram_webhook(
    payload: dict,
    adapter: TelegramAdapter = Depends(get_telegram_adapter),
):
    """Official webhook receiver for Telegram Bot Updates."""
    await adapter.handle_webhook(payload)
    return {"status": "ok"}


# ── WebSockets Endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws/{channel_id}")
async def ws_channel_subscription(
    websocket: WebSocket,
    channel_id: str,
    token: str | None = None,
    repo: ChatRepositoryPort = Depends(get_chat_repo),
):
    """Real-time bi-directional connection to stream messages for a specific channel."""
    # Verify token
    from harness.core.auth import get_auth_manager
    auth_manager = get_auth_manager()
    
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token is missing")
        return
        
    token_data = auth_manager.verify_token(token)
    if not token_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth token")
        return

    # Check channel and membership if private
    channel = await repo.get_channel(channel_id)
    if not channel:
        await websocket.close(code=4004, reason="Channel not found")
        return

    if channel.is_private:
        member = await repo.get_member(channel_id, token_data.user_id)
        if not member:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access denied")
            return

    publisher = get_chat_ws_publisher()
    await publisher.connect(channel_id, websocket)

    try:
        while True:
            # Drain client messages, currently WS is write-only from server to client
            # Clients use REST POST to send messages for clean integration
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        publisher.disconnect(channel_id, websocket)
