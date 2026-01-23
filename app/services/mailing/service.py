from __future__ import annotations

import os
from datetime import datetime
<<<<<<< HEAD
from typing import Dict, List, Optional
=======
from typing import Optional
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotSubscriber,
    Mailing,
    MailingRecipient,
    MailingStatus,
    MessageType,
    RecipientStatus,
    ParsedChat,
    ParsedUser,
    TargetSource,
)


class MailingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_mailing(
        self,
        owner_id: int,
        account_id: Optional[int],
        chat_id: Optional[int],
<<<<<<< HEAD
        target_ids: Optional[List[int]],
=======
        target_ids: Optional[list[int]],
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344
        target_source: TargetSource,
        message_type: MessageType,
        text: Optional[str],
        media_path: Optional[str],
        media_file_id: Optional[str],
        sticker_set_name: Optional[str],
        sticker_set_index: Optional[int],
        mention: bool,
        delay_seconds: float,
        limit_count: int,
    ) -> Mailing:
        mailing = Mailing(
            owner_id=owner_id,
            account_id=account_id,
            chat_id=chat_id,
            status=MailingStatus.running,
            message_type=message_type,
            text=text,
            media_path=media_path,
            media_file_id=media_file_id,
            sticker_set_name=sticker_set_name,
            sticker_set_index=sticker_set_index,
            mention=mention,
            target_source=target_source,
            delay_seconds=delay_seconds,
            limit_count=limit_count,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._session.add(mailing)
        await self._session.commit()
        await self._session.refresh(mailing)
        if target_ids:
            mailing._target_ids = target_ids
        await self._enqueue_recipients(mailing)
        return mailing

    async def pause(self, owner_id: int, mailing_id: int) -> bool:
        mailing = await self._get_mailing(owner_id, mailing_id)
        if not mailing:
            return False
        mailing.status = MailingStatus.paused
        mailing.updated_at = datetime.utcnow()
        await self._session.commit()
        return True

    async def resume(self, owner_id: int, mailing_id: int) -> bool:
        mailing = await self._get_mailing(owner_id, mailing_id)
        if not mailing:
            return False
        mailing.status = MailingStatus.running
        mailing.updated_at = datetime.utcnow()
        await self._session.commit()
        return True

    async def get_status(self, owner_id: int, mailing_id: int) -> Optional[MailingStatus]:
        mailing = await self._get_mailing(owner_id, mailing_id)
        return mailing.status if mailing else None

    async def get_mailing(self, owner_id: int, mailing_id: int) -> Optional[Mailing]:
        return await self._get_mailing(owner_id, mailing_id)

    async def get_stats(self, owner_id: int, mailing_id: int) -> Dict[str, int]:
        result = await self._session.execute(
            select(func.count(MailingRecipient.id)).where(MailingRecipient.mailing_id == mailing_id)
        )
        total = int(result.scalar() or 0)
        result = await self._session.execute(
            select(func.count(MailingRecipient.id)).where(
                MailingRecipient.mailing_id == mailing_id,
                MailingRecipient.status == RecipientStatus.sent,
            )
        )
        sent = int(result.scalar() or 0)
        result = await self._session.execute(
            select(func.count(MailingRecipient.id)).where(
                MailingRecipient.mailing_id == mailing_id,
                MailingRecipient.status == RecipientStatus.failed,
            )
        )
        failed = int(result.scalar() or 0)
        pending = max(total - sent - failed, 0)
        return {"total": total, "sent": sent, "failed": failed, "pending": pending}

    async def repeat(self, owner_id: int, mailing_id: int) -> Optional[Mailing]:
        mailing = await self._get_mailing(owner_id, mailing_id)
        if not mailing:
            return None
        clone = Mailing(
            owner_id=owner_id,
            account_id=mailing.account_id,
            chat_id=mailing.chat_id,
            status=MailingStatus.running,
            message_type=mailing.message_type,
            text=mailing.text,
            media_path=mailing.media_path,
            media_file_id=mailing.media_file_id,
            sticker_set_name=mailing.sticker_set_name,
            sticker_set_index=mailing.sticker_set_index,
            mention=mailing.mention,
            target_source=mailing.target_source,
            delay_seconds=mailing.delay_seconds,
            limit_count=mailing.limit_count,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._session.add(clone)
        await self._session.commit()
        await self._session.refresh(clone)

        result = await self._session.execute(
            select(MailingRecipient).where(MailingRecipient.mailing_id == mailing_id)
        )
        recipients = result.scalars().all()
        for rec in recipients:
            self._session.add(
                MailingRecipient(
                    mailing_id=clone.id,
                    user_id=rec.user_id,
                    username=rec.username,
                    access_hash=rec.access_hash,
                    status=RecipientStatus.pending,
                )
            )
        await self._session.commit()
        return clone

    async def update_content(
        self,
        owner_id: int,
        mailing_id: int,
        message_type: MessageType,
        text: Optional[str],
        media_path: Optional[str],
        media_file_id: Optional[str],
        sticker_set_name: Optional[str],
        sticker_set_index: Optional[int],
    ) -> Optional[Mailing]:
        mailing = await self._get_mailing(owner_id, mailing_id)
        if not mailing:
            return None
        mailing.message_type = message_type
        mailing.text = text
        mailing.media_path = media_path
        mailing.media_file_id = media_file_id
        mailing.sticker_set_name = sticker_set_name
        mailing.sticker_set_index = sticker_set_index
        mailing.updated_at = datetime.utcnow()
        await self._session.commit()
        await self._session.refresh(mailing)
        return mailing

    async def delete(self, owner_id: int, mailing_id: int) -> bool:
        mailing = await self._get_mailing(owner_id, mailing_id)
        if not mailing:
            return False
        media_path = mailing.media_path
        await self._session.execute(
            delete(MailingRecipient).where(MailingRecipient.mailing_id == mailing_id)
        )
        await self._session.delete(mailing)
        await self._session.commit()
        if media_path and os.path.isfile(media_path):
            try:
                os.remove(media_path)
            except OSError:
                pass
        return True

    async def _get_mailing(self, owner_id: int, mailing_id: int) -> Optional[Mailing]:
        result = await self._session.execute(
            select(Mailing).where(Mailing.id == mailing_id, Mailing.owner_id == owner_id)
        )
        return result.scalars().first()

    async def _enqueue_recipients(self, mailing: Mailing) -> None:
        limit = mailing.limit_count or 0
        count = 0

        if hasattr(mailing, "_target_ids") and mailing._target_ids:
            for target_id in mailing._target_ids:
                if limit and count >= limit:
                    break
                recipient = MailingRecipient(
                    mailing_id=mailing.id,
                    user_id=target_id,
                    username=None,
                    access_hash=None,
                )
                self._session.add(recipient)
                count += 1
            await self._session.commit()
            return

        if mailing.target_source == TargetSource.subscribers:
            result = await self._session.execute(select(BotSubscriber))
            recipients = result.scalars().all()
        elif mailing.target_source == TargetSource.parsed:
            result = await self._session.execute(select(ParsedUser).where(ParsedUser.owner_id == mailing.owner_id))
            recipients = result.scalars().all()
        else:
            chat_query = select(ParsedChat).where(ParsedChat.owner_id == mailing.owner_id)
            if mailing.chat_id:
                chat_query = chat_query.where(ParsedChat.chat_id == mailing.chat_id)
            result = await self._session.execute(chat_query)
            recipients = result.scalars().all()

        for user in recipients:
            if limit and count >= limit:
                break
            target_id = getattr(user, "user_id", None)
            if target_id is None:
                target_id = getattr(user, "chat_id", None)
            recipient = MailingRecipient(
                mailing_id=mailing.id,
                user_id=target_id,
                username=getattr(user, "username", None),
                access_hash=getattr(user, "access_hash", None),
            )
            self._session.add(recipient)
            count += 1

        await self._session.commit()
