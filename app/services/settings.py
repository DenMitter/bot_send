from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting


SUPPORT_CONTACT_KEY = "support_contact"


async def get_setting(session: AsyncSession, keys: Iterable[str], user_id: Optional[int] = None) -> dict[str, str]:
    keys = list(keys)
    if not keys:
        return {}

    # If user_id is None, use 0 for global settings
    if user_id is None:
        user_id = 0

    query = select(AppSetting.key, AppSetting.value).where(
        AppSetting.key.in_(keys),
        AppSetting.user_id == user_id
    )

    result = await session.execute(query)
    return dict(result.all())


async def set_setting(session: AsyncSession, key: str, value: str, user_id: Optional[int] = None) -> None:
    # If user_id is None, use 0 for global settings
    if user_id is None:
        user_id = 0

    query = select(AppSetting).where(
        AppSetting.key == key,
        AppSetting.user_id == user_id
    )

    row = (await session.execute(query)).scalars().first()
    if row:
        row.value = value
    else:
        session.add(AppSetting(user_id=user_id, key=key, value=value))
    await session.commit()
