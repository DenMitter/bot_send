from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.tl.types import (
    Channel,
    Chat,
    MessageEntityMentionName,
    User,
    ChannelParticipantsAdmins,
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
    UserStatusEmpty,
)

from app.client.telethon_manager import TelethonManager
from app.db.models import Account, ParsedChat, ParsedUser, ParseFilter


class ParserService:
    def __init__(self, session: AsyncSession, manager: TelethonManager) -> None:
        self._session = session
        self._manager = manager

    @staticmethod
    def _default_filters() -> "ParseFilterSettings":
        return ParseFilterSettings(status="all", gender="any", language="any", activity="any")

    async def _get_filters(self, owner_id: int) -> "ParseFilterSettings":
        result = await self._session.execute(select(ParseFilter).where(ParseFilter.owner_id == owner_id))
        row = result.scalars().first()
        if not row:
            return self._default_filters()
        return ParseFilterSettings(
            status=row.status or "all",
            gender=row.gender or "any",
            language=row.language or "any",
            activity=row.activity or "any",
        )

    async def _get_admin_ids(self, client, chat: str) -> set[int]:
        try:
            admins = await client.get_participants(chat, filter=ChannelParticipantsAdmins)
        except Exception:
            return set()
        return {admin.id for admin in admins if isinstance(admin, User)}

    @staticmethod
    def _infer_gender(first_name: Optional[str]) -> str:
        name = (first_name or "").strip()
        if not name:
            return "unknown"
        lowered = name.lower()
        if lowered.endswith(("a", "я", "а", "i", "і")):
            return "female"
        if lowered.endswith(("й", "ь")):
            return "male"
        return "male"

    @staticmethod
    def _infer_language(first_name: Optional[str], last_name: Optional[str]) -> str:
        text = f"{first_name or ''} {last_name or ''}".strip()
        if not text:
            return "other"
        has_cyr = any("а" <= ch.lower() <= "я" or ch.lower() in ("ё", "є", "і", "ї", "ґ") for ch in text)
        has_lat = any("a" <= ch.lower() <= "z" for ch in text)
        if has_cyr and not has_lat:
            return "ru"
        if has_lat and not has_cyr:
            return "en"
        if has_cyr and has_lat:
            return "other"
        return "other"

    @staticmethod
    def _activity_bucket(status) -> str:
        if isinstance(status, UserStatusOnline):
            return "online"
        if isinstance(status, UserStatusRecently):
            return "recent"
        if isinstance(status, UserStatusLastWeek):
            return "week"
        if isinstance(status, UserStatusLastMonth):
            return "month"
        if isinstance(status, UserStatusOffline) and status.was_online:
            now = datetime.now(timezone.utc)
            was_online = status.was_online
            if was_online.tzinfo is None:
                was_online = was_online.replace(tzinfo=timezone.utc)
            delta_days = (now - was_online).days
            if delta_days <= 1:
                return "recent"
            if delta_days <= 7:
                return "week"
            if delta_days <= 30:
                return "month"
            return "long"
        if isinstance(status, UserStatusEmpty):
            return "long"
        return "unknown"

    def _passes_activity(self, activity_filter: str, bucket: str) -> bool:
        if activity_filter == "any":
            return True
        order = {
            "online": 0,
            "recent": 1,
            "week": 2,
            "month": 3,
            "long": 4,
            "unknown": 5,
        }
        if activity_filter == "long":
            return bucket == "long"
        return order.get(bucket, 5) <= order.get(activity_filter, 5)

    def _passes_filters(self, user: User, filters: "ParseFilterSettings", admin_ids: set[int]) -> bool:
        status_filter = filters.status
        if status_filter == "bots" and not user.bot:
            return False
        if status_filter == "admins" and user.id not in admin_ids:
            return False
        if status_filter == "users":
            if user.bot or user.id in admin_ids:
                return False

        if filters.gender != "any":
            inferred_gender = self._infer_gender(user.first_name)
            if inferred_gender != filters.gender:
                return False

        if filters.language != "any":
            inferred_language = self._infer_language(user.first_name, user.last_name)
            if inferred_language != filters.language:
                return False

        if filters.activity != "any":
            bucket = self._activity_bucket(getattr(user, "status", None))
            if not self._passes_activity(filters.activity, bucket):
                return False

        return True

    async def parse_chat(
        self,
        account: Account,
        owner_id: int,
        chat: str,
        limit: int = 0,
        max_users: Optional[int] = None,
    ) -> int:
        client = await self._manager.get_client(account)
        filters = await self._get_filters(owner_id)
        admin_ids: set[int] = set()
        if filters.status in ("admins", "users"):
            admin_ids = await self._get_admin_ids(client, chat)
        added = 0
        async for user in client.iter_participants(chat, limit=limit or None, aggressive=True):
            if not self._passes_filters(user, filters, admin_ids):
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
                access_hash=getattr(user, "access_hash", None),
                source=chat,
            )
            self._session.add(parsed)
            added += 1
            if max_users and added >= max_users:
                break
        await self._session.commit()
        return added

    async def parse_chat_history(
        self,
        account: Account,
        owner_id: int,
        chat: str,
        limit_messages: int = 0,
        include_mentions: bool = True,
        include_replies: bool = True,
        max_users: Optional[int] = None,
    ) -> int:
        client = await self._manager.get_client(account)
        filters = await self._get_filters(owner_id)
        admin_ids: set[int] = set()
        if filters.status in ("admins", "users"):
            admin_ids = await self._get_admin_ids(client, chat)
        user_ids = set()
        reply_cache = {}

        async for message in client.iter_messages(chat, limit=limit_messages or None):
            if message.sender_id:
                user_ids.add(message.sender_id)

            if include_mentions and message.entities:
                for entity in message.entities:
                    if isinstance(entity, MessageEntityMentionName):
                        user_ids.add(entity.user_id)

            if include_replies and message.reply_to and message.reply_to.reply_to_msg_id:
                reply_id = message.reply_to.reply_to_msg_id
                if reply_id not in reply_cache:
                    try:
                        replied = await client.get_messages(chat, ids=reply_id)
                    except Exception:
                        replied = None
                    reply_cache[reply_id] = replied.sender_id if replied and replied.sender_id else None
                if reply_cache[reply_id]:
                    user_ids.add(reply_cache[reply_id])

        if not user_ids:
            return 0

        existing_ids = set()
        for chunk in _chunked(list(user_ids), 1000):
            result = await self._session.execute(
                select(ParsedUser.user_id).where(ParsedUser.owner_id == owner_id, ParsedUser.user_id.in_(chunk))
            )
            existing_ids.update(row[0] for row in result.all())

        new_ids = [uid for uid in user_ids if uid not in existing_ids]
        if max_users is not None:
            new_ids = new_ids[: max(0, max_users)]
        if not new_ids:
            return 0

        added = 0
        for chunk in _chunked(new_ids, 200):
            try:
                entities = await client.get_entities(chunk)
                if not isinstance(entities, list):
                    entities = [entities]
            except Exception:
                entities = []
                for uid in chunk:
                    try:
                        entities.append(await client.get_entity(uid))
                    except Exception:
                        continue

            for entity in entities:
                if not isinstance(entity, User):
                    continue
                if not self._passes_filters(entity, filters, admin_ids):
                    continue
                parsed = ParsedUser(
                    owner_id=owner_id,
                    user_id=entity.id,
                    username=entity.username,
                    first_name=entity.first_name,
                    last_name=entity.last_name,
                    access_hash=getattr(entity, "access_hash", None),
                    source=chat,
                )
                self._session.add(parsed)
                added += 1

        await self._session.commit()
        return added

    async def parse_groups(self, account: Account, owner_id: int, max_chats: Optional[int] = None) -> int:
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
                access_hash=getattr(entity, "access_hash", None),
            )
            self._session.add(parsed)
            added += 1
            if max_chats and added >= max_chats:
                break
        await self._session.commit()
        return added


def _chunked(values, size: int):
    for i in range(0, len(values), size):
        yield values[i : i + size]


@dataclass(frozen=True)
class ParseFilterSettings:
    status: str
    gender: str
    language: str
    activity: str
