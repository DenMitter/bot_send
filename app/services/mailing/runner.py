from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import (
    DocumentAttributeImageSize,
    DocumentAttributeSticker,
    InputStickerSetEmpty,
    InputStickerSetShortName,
)

from app.client.telethon_manager import TelethonManager
from app.core.config import get_settings
from app.db.models import (
    Account,
    Mailing,
    MailingRecipient,
    MailingStatus,
    MessageType,
    RecipientStatus,
)
from app.services.mailing.logs import append_recipient_log
from app.services.auth import AccountService


class MailingRunner:
    def __init__(self, session: AsyncSession, manager: TelethonManager) -> None:
        self._session = session
        self._manager = manager
        self._running = False
        self._base_dir = Path(__file__).resolve().parents[3]
        self._logger = logging.getLogger(__name__)

    async def run_forever(self) -> None:
        self._running = True
        settings = get_settings()
        while self._running:
            await self._process_all(settings.mailing_batch_size)
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False

    async def _process_all(self, batch_size: int) -> None:
        try:
            result = await self._session.execute(select(Mailing).where(Mailing.status == MailingStatus.running))
            mailings = result.scalars().all()
            if not mailings:
                return

            for mailing in mailings:
                await self._process_mailing(mailing, batch_size)
        finally:
            await self._session.rollback()

    async def _process_mailing(self, mailing: Mailing, batch_size: int) -> None:
        account = await self._resolve_account(mailing)
        if not account:
            mailing.status = MailingStatus.failed
            mailing.updated_at = datetime.utcnow()
            await self._session.commit()
            return

        client = await self._manager.get_client(account)
        pending = await self._session.execute(
            select(MailingRecipient)
            .where(
                MailingRecipient.mailing_id == mailing.id,
                MailingRecipient.status == RecipientStatus.pending,
            )
        )
        recipients = pending.scalars().all()
        if not recipients:
            mailing.status = MailingStatus.done
            mailing.updated_at = datetime.utcnow()
            await self._session.commit()
            return

        for recipient in recipients[:batch_size]:
            refreshed = await self._session.execute(select(Mailing).where(Mailing.id == mailing.id))
            current = refreshed.scalars().first()
            if not current or current.status != MailingStatus.running:
                break

            try:
                await self._send_to_recipient(client, mailing, recipient)
                recipient.status = RecipientStatus.sent
                recipient.sent_at = datetime.utcnow()
                recipient.error = None
            except Exception as exc:
                self._logger.exception(
                    "Mailing send failed mailing_id=%s recipient=%s username=%s type=%s media_path=%s media_file_id=%s set=%s index=%s",
                    mailing.id,
                    recipient.user_id,
                    recipient.username,
                    mailing.message_type.value,
                    mailing.media_path,
                    mailing.media_file_id,
                    mailing.sticker_set_name,
                    mailing.sticker_set_index,
                )
                recipient.status = RecipientStatus.failed
                recipient.error = str(exc)
                append_recipient_log(mailing.id, recipient.user_id, recipient.username, str(exc))
            await self._session.commit()
            await asyncio.sleep(mailing.delay_seconds)

    async def _send_to_recipient(self, client, mailing: Mailing, recipient: MailingRecipient) -> None:
        base_text = mailing.text or ""
        if mailing.mention and recipient.username:
            base_text = f"{base_text}\n@{recipient.username}" if base_text else f"@{recipient.username}"

        target = recipient.user_id
        if recipient.username:
            target = f"@{recipient.username}"

        if mailing.message_type == MessageType.text:
            await client.send_message(target, base_text)
            return

        if not mailing.media_path and not mailing.media_file_id:
            await client.send_message(target, base_text)
            return
        if mailing.message_type == MessageType.sticker and mailing.sticker_set_name is not None:
            if mailing.sticker_set_index is not None:
                result = await client(
                    GetStickerSetRequest(InputStickerSetShortName(mailing.sticker_set_name), hash=0)
                )
                if 0 <= mailing.sticker_set_index < len(result.documents):
                    await client.send_file(target, result.documents[mailing.sticker_set_index], force_document=False)
                    return
            if mailing.media_file_id:
                await client.send_file(target, mailing.media_file_id, force_document=False)
                return
        if mailing.message_type == MessageType.sticker and mailing.sticker_set_name is None:
            if mailing.media_path:
                media_path = self._resolve_media_path(mailing.media_path)
                await client.send_file(target, media_path, force_document=False)
                return
            if mailing.media_file_id:
                await client.send_file(target, mailing.media_file_id, force_document=False)
                return

        if not mailing.media_path:
            await client.send_message(target, base_text)
            return
        media_path = self._resolve_media_path(mailing.media_path)

        if mailing.message_type == MessageType.sticker:
            attributes = [DocumentAttributeSticker(alt="🙂", stickerset=InputStickerSetEmpty())]
            ext = Path(media_path).suffix.lower()
            try:
                if ext == ".webp":
                    with Image.open(media_path) as image:
                        width, height = image.size
                    attributes.insert(0, DocumentAttributeImageSize(w=width, h=height))
            except Exception:
                pass
            await client.send_file(
                target,
                media_path,
                attributes=attributes,
                force_document=ext in (".tgs", ".webm"),
            )
            return

        if mailing.message_type == MessageType.voice:
            await client.send_file(target, media_path)
            return

        await client.send_file(target, media_path, caption=base_text or None)

    def _resolve_media_path(self, media_path: str) -> str:
        if os.path.isabs(media_path):
            return media_path
        return str((self._base_dir / media_path).resolve())

    async def _resolve_account(self, mailing: Mailing) -> Account | None:
        if mailing.account_id:
            result = await self._session.execute(
                select(Account).where(Account.id == mailing.account_id, Account.owner_id == mailing.owner_id)
            )
            account = result.scalars().first()
            if account:
                return account
        return await AccountService(self._session).get_active_account(mailing.owner_id)
