from typing import Optional

from aiogram.types import Message
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import BotSubscriber
from app.db.session import get_session_factory
from app.i18n.translator import LANG_MAP, t
from app.services.settings import get_setting


def is_admin(message: Message) -> bool:
    settings = get_settings()
    return message.from_user and message.from_user.id in settings.admin_id_set()


def is_admin_user_id(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    return user_id in get_settings().admin_id_set()


def get_locale(message: Message) -> str:
    settings = get_settings()
    if message.from_user and message.from_user.language_code in ("uk", "ru"):
        return message.from_user.language_code
    return settings.default_locale


def normalize_locale(value: Optional[str]) -> str:
    if not value:
        return get_settings().default_locale
    value = value.lower()
    if value in LANG_MAP:
        return value
    return get_settings().default_locale


async def resolve_locale(user_id: int, fallback: Optional[str] = None) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(BotSubscriber).where(BotSubscriber.user_id == user_id))
        subscriber = result.scalars().first()
        if subscriber and subscriber.language:
            return normalize_locale(subscriber.language)
    return normalize_locale(fallback)


async def build_mailing_intro(locale: str) -> str:
    defaults = {
        "mailing_tariff_base": "0.016",
        "mailing_tariff_mention": "0.02",
        "mailing_tariff_bulk_low": "0.008",
        "mailing_tariff_bulk_high": "0.01",
    }
    values = defaults.copy()
    session_factory = get_session_factory()
    async with session_factory() as session:
        for key in defaults:
            raw = await get_setting(session, key)
            if raw:
                values[key] = raw
    return t("mailing_intro", locale).format(
        base=values["mailing_tariff_base"],
        mention=values["mailing_tariff_mention"],
        bulk_low=values["mailing_tariff_bulk_low"],
        bulk_high=values["mailing_tariff_bulk_high"],
    )
