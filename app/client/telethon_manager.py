from __future__ import annotations

from typing import Dict

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.config import get_settings
from app.db.models import Account


class TelethonManager:
    def __init__(self) -> None:
        self._clients: Dict[int, TelegramClient] = {}

    async def get_client(self, account: Account) -> TelegramClient:
        if account.id in self._clients:
            client = self._clients[account.id]
            if not client.is_connected():
                await client.connect()
            return client

        settings = get_settings()
        client = TelegramClient(StringSession(account.session_string), settings.api_id, settings.api_hash)
        await client.connect()
        self._clients[account.id] = client
        return client

    async def close_all(self) -> None:
        for client in self._clients.values():
            if client.is_connected():
                await client.disconnect()
        self._clients.clear()
