from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import select

from app.db.models import BotSubscriber
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.bot.handlers.common import is_admin, normalize_locale, resolve_locale
from app.bot.keyboards import language_keyboard, user_menu_keyboard


router = Router()


async def _show_menu(message: Message, locale: str, edit: bool) -> None:
    if edit:
        await message.edit_text(t("start", locale), reply_markup=user_menu_keyboard(locale, is_admin(message)))
        return
    await message.answer(t("start", locale), reply_markup=user_menu_keyboard(locale, is_admin(message)))


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(BotSubscriber).where(BotSubscriber.user_id == message.from_user.id))
        subscriber = result.scalars().first()
        if not subscriber:
            subscriber = BotSubscriber(
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language=None,
            )
            session.add(subscriber)
            await session.commit()

    if not subscriber.language:
        await message.answer(t("choose_language", locale), reply_markup=language_keyboard())
        return

    await message.answer(t("user_menu", locale), reply_markup=ReplyKeyboardRemove())
    await _show_menu(message, normalize_locale(subscriber.language), edit=False)


@router.message(Command("menu"))
async def menu_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await _show_menu(message, locale, edit=False)


@router.callback_query(F.data.in_(["lang:uk", "lang:ru"]))
async def language_select(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    selected = "uk" if callback.data == "lang:uk" else "ru"
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(BotSubscriber).where(BotSubscriber.user_id == callback.from_user.id))
        subscriber = result.scalars().first()
        if not subscriber:
            subscriber = BotSubscriber(user_id=callback.from_user.id, language=selected)
            session.add(subscriber)
        else:
            subscriber.language = selected
        await session.commit()
    await callback.message.edit_text(
        t("start", selected),
        reply_markup=user_menu_keyboard(selected, is_admin(callback.message)),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:start")
async def start_button(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await _show_menu(callback.message, locale, edit=True)
    await callback.answer()
