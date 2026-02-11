from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting


SUPPORT_CONTACT_KEY = "support_contact"


async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalars().first()
    if not row:
        return None
    return row.value


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalars().first()
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=key, value=value))
    await session.commit()
