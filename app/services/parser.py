from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.tl.types import Channel, ChannelParticipantsSearch, Chat

from app.client.telethon_manager import TelethonManager
from app.db.models import Account, ParsedChat, ParsedUser


class ParserService:
    def __init__(self, session: AsyncSession, manager: TelethonManager) -> None:
        self._session = session
        self._manager = manager

    async def parse_chat(self, account: Account, owner_id: int, chat: str, limit: int = 0) -> int:
        client = await self._manager.get_client(account)
        added = 0
        async for user in client.iter_participants(chat, filter=ChannelParticipantsSearch(""), limit=limit or None):
            if user.bot:
                continue
            exists = await self._session.execute(
                select(ParsedUser).where(ParsedUser.owner_id == owner_id, ParsedUser.user_id == user.id)
            )
            if exists.scalars().first():
                continue
            parsed = ParsedUser(
                owner_id=owner_id,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                source=chat,
            )
            self._session.add(parsed)
            added += 1
        await self._session.commit()
        return added

    async def parse_groups(self, account: Account, owner_id: int) -> int:
        client = await self._manager.get_client(account)
        added = 0
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            chat_id = None
            username = getattr(entity, "username", None)
            title = getattr(entity, "title", None)
            chat_type = None

            if isinstance(entity, Channel) and getattr(entity, "megagroup", False):
                chat_id = entity.id
                chat_type = "megagroup"
            elif isinstance(entity, Chat):
                chat_id = entity.id
                chat_type = "chat"
            else:
                continue

            exists = await self._session.execute(
                select(ParsedChat).where(ParsedChat.owner_id == owner_id, ParsedChat.chat_id == chat_id)
            )
            if exists.scalars().first():
                continue

            parsed = ParsedChat(
                owner_id=owner_id,
                chat_id=chat_id,
                title=title,
                username=username,
                chat_type=chat_type,
            )
            self._session.add(parsed)
            added += 1
        await self._session.commit()
        return added
