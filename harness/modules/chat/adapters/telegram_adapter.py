"""
Telegram Webhook and Bot API adapter for Chat Module.
Handles inbound webhooks from Telegram and outbound message forwarding to Telegram chats.
"""

from __future__ import annotations

import os
from typing import Any
import httpx

from harness.modules.chat.domain.entities import Channel, Message
from harness.modules.chat.ports.inbound import SendMessageUseCase, CreateChannelUseCase, JoinChannelUseCase
from harness.modules.chat.ports.outbound import ChatRepositoryPort


class TelegramAdapter:
    def __init__(
        self,
        repo: ChatRepositoryPort,
        send_msg_use_case: SendMessageUseCase,
        create_chan_use_case: CreateChannelUseCase,
        join_chan_use_case: JoinChannelUseCase,
        bot_token: str | None = None,
    ) -> None:
        self.repo = repo
        self.send_msg_use_case = send_msg_use_case
        self.create_chan_use_case = create_chan_use_case
        self.join_chan_use_case = join_chan_use_case
        
        # Load from environment if not passed explicitly
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """
        Processes an incoming Telegram Update webhook.
        Documentation Reference: https://core.telegram.org/bots/api#update
        """
        if not payload or "message" not in payload:
            return

        message_data = payload["message"]
        chat_data = message_data.get("chat")
        from_data = message_data.get("from")
        text = message_data.get("text")

        if not chat_data or not from_data or not text:
            return

        telegram_chat_id = str(chat_data["id"])
        telegram_user_id = str(from_data["id"])
        
        # Create user display name
        sender_name = from_data.get("first_name", "")
        last_name = from_data.get("last_name", "")
        if last_name:
            sender_name += f" {last_name}"
        username = from_data.get("username")
        if username:
            sender_name += f" (@{username})"

        # We map Telegram chats to VLoop Channels.
        # Channel name will be 'telegram_<chat_id>'
        channel_name = f"telegram_{telegram_chat_id}"
        
        # 1. Resolve or create Channel
        channel = await self.repo.get_channel_by_name(channel_name)
        if not channel:
            # Let's create a public or private channel based on Telegram chat type
            is_private = chat_data.get("type") == "private"
            chat_title = chat_data.get("title", f"Telegram Chat {telegram_chat_id}")
            
            # Use 'system' or creator ID to create
            channel = await self.create_chan_use_case.execute(
                name=channel_name,
                description=f"Bridged Telegram Channel: {chat_title}",
                is_private=is_private,
                created_by="system",
            )

        # 2. Add Telegram user as a member of this channel in VLoop DB
        await self.join_chan_use_case.execute(
            channel_id=channel.id,
            user_id=f"telegram_{telegram_user_id}",
            role="member",
        )

        # 3. Route the incoming Telegram message through the core SendMessageUseCase
        # We specify sender_type='telegram' to prevent forwarding loops back to Telegram
        await self.send_msg_use_case.execute(
            channel_id=channel.id,
            sender_id=f"telegram_{telegram_user_id}",
            sender_name=sender_name,
            sender_type="telegram",
            content=text,
        )

    async def forward_to_telegram(self, channel_id: str, message: Message) -> None:
        """
        Sends an outbound message to a Telegram Chat.
        Uses HTTP POST request to Telegram's sendMessage endpoint.
        Documentation Reference: https://core.telegram.org/bots/api#sendmessage
        """
        if not self.bot_token or not self.api_url:
            return

        # Check if the channel is a Telegram-linked channel
        channel = await self.repo.get_channel(channel_id)
        if not channel or not channel.name.startswith("telegram_"):
            return

        # Extract Telegram Chat ID from channel name 'telegram_<chat_id>'
        telegram_chat_id = channel.name.replace("telegram_", "")

        # Format text to include sender name (e.g. VLoop AI or human name) if it's not a Telegram sender
        if message.sender_type == "ai":
            formatted_text = f"🤖 {message.content}"
        else:
            formatted_text = f"👤 {message.sender_name}: {message.content}"

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": formatted_text,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
        except Exception as e:
            print(f"Error forwarding message to Telegram Bot API: {e}")
