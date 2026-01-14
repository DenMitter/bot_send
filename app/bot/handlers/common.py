from aiogram.types import Message
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import BotSubscriber
from app.db.session import get_session_factory
from app.i18n.translator import LANG_MAP


def is_admin(message: Message) -> bool:
    settings = get_settings()
    return message.from_user and message.from_user.id in settings.admin_id_set()


def get_locale(message: Message) -> str:
    settings = get_settings()
    if message.from_user and message.from_user.language_code in ("uk", "ru"):
        return message.from_user.language_code
    return settings.default_locale


def normalize_locale(value: str | None) -> str:
    if not value:
        return get_settings().default_locale
    value = value.lower()
    if value in LANG_MAP:
        return value
    return get_settings().default_locale


async def resolve_locale(user_id: int, fallback: str | None = None) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(BotSubscriber).where(BotSubscriber.user_id == user_id))
        subscriber = result.scalars().first()
        if subscriber and subscriber.language:
            return normalize_locale(subscriber.language)
    return normalize_locale(fallback)
