from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from typing import Optional, Sequence

from app.bot.history import (
    clear_history,
    edit_with_history,
    get_welcome_page,
    pop_state,
    push_state,
    register_message,
    set_welcome_page,
)
from app.db.models import BotSubscriber, Mailing
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.bot.handlers.common import is_admin, normalize_locale, resolve_locale
from app.bot.keyboards import (
    BUTTON_ICONS,
    language_keyboard,
    manual_inline_keyboard,
    welcome_entry_keyboard,
    welcome_keyboard,
    WELCOME_PAGE_COUNT,
    mailing_list_keyboard,
)
from app.bot.handlers.mailing import mailing_new
from app.bot.handlers.admin import _parse_chat_for_user, send_parsed_users_file
from app.bot.handlers.accounts import account_list
from app.bot.manuals import clear_manual_media, load_manual_page, render_manual_message


router = Router()


def _first_media_path(media_paths: Sequence[str] | None) -> Optional[str]:
    if not media_paths:
        return None
    return next((path for path in media_paths if path), None)


def _strip_button_icon(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    stripped = text.strip()
    for icon in BUTTON_ICONS.values():
        if stripped.startswith(icon):
            stripped = stripped[len(icon) :].strip()
            break
    return stripped


def _matches_button(key: str, text: Optional[str]) -> bool:
    normalized = _strip_button_icon(text)
    if not normalized:
        return False
    return normalized in _button_texts(key)


def _looks_like_chat(text: Optional[str]) -> bool:
    content = (text or "").strip()
    if not content or content.startswith("/"):
        return False
    lowered = content.lower()
    return lowered.startswith("t.me/") or "t.me/" in lowered or content.startswith("@")

async def _send_welcome_menu(message: Message, locale: str) -> None:
    caption = t("welcome_caption", locale)
    set_welcome_page(message.chat.id, 1)
    await clear_manual_media(message.bot, message.chat.id)
    await message.answer(t("menu", locale), reply_markup=welcome_keyboard(locale))
    sent = await message.answer(caption, reply_markup=welcome_entry_keyboard(locale))
    register_message(sent)


def _button_texts(key: str) -> set[str]:
    return {t(key, "uk"), t(key, "ru")}


async def _show_manual_page(message: Message, locale: str, page: int) -> None:
    try:
        text, media_paths = load_manual_page(locale, page)
    except FileNotFoundError:
        await message.answer(t("manuals_info", locale))
        return
    set_welcome_page(message.chat.id, page)
    media_path = _first_media_path(media_paths)
    options = {"parse_mode": "Markdown"}
    push_state(message, options, media_paths)
    edited = await render_manual_message(
        bot=message.bot,
        current_message_id=message.message_id,
        chat_id=message.chat.id,
        text=text,
        media_path=media_path,
        reply_markup=manual_inline_keyboard(locale, page),
        parse_mode=options["parse_mode"],
    )
    register_message(edited, options, media_paths)


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

    clear_history(message.chat.id)
    await _send_welcome_menu(message, normalize_locale(subscriber.language))

@router.message(Command("manuals"))
async def manuals_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("manuals_info", locale))


@router.message(Command("tasks"))
async def tasks_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("tasks_info", locale))


@router.message(Command("franchise"))
async def franchise_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("franchise_info", locale))


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
    await edit_with_history(callback.message, t("language_selected", selected))
    await _send_welcome_menu(callback.message, selected)
    await callback.answer()


@router.callback_query(F.data == "welcome:manual")
async def welcome_manual(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await _show_manual_page(callback.message, locale, 1)
    await callback.answer()


@router.callback_query(F.data == "welcome:action:start")
async def welcome_start(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    clear_history(callback.message.chat.id)
    set_welcome_page(callback.message.chat.id, 1)
    try:
        edited = await callback.message.edit_text(
            t("welcome_caption", locale),
            reply_markup=welcome_entry_keyboard(locale),
        )
        register_message(edited)
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "welcome:action:support")
async def welcome_support(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("support_info", locale))
    await callback.answer()


@router.callback_query(F.data.in_(["welcome:page:prev", "welcome:page:next"]))
async def welcome_page_navigation(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    action = callback.data.split(":")[-1]
    page = get_welcome_page(callback.message.chat.id)
    if action == "prev":
        new_page = max(1, page - 1)
    else:
        new_page = min(WELCOME_PAGE_COUNT, page + 1)
    if new_page == page:
        await callback.answer()
        return
    await _show_manual_page(callback.message, locale, new_page)
    await callback.answer()


@router.callback_query(F.data == "welcome:page:info")
async def welcome_page_info(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "back:prev")
async def back_prev(callback: CallbackQuery) -> None:
    snapshot = pop_state(callback.message.chat.id)
    if not snapshot:
        await callback.answer()
        return
    media_path = _first_media_path(snapshot.media_paths)
    parse_mode = snapshot.options.get("parse_mode", "Markdown")
    body_text = snapshot.text
    try:
        edited = await render_manual_message(
            bot=callback.message.bot,
            current_message_id=callback.message.message_id,
            chat_id=callback.message.chat.id,
            text=body_text,
            media_path=media_path,
            reply_markup=snapshot.reply_markup,
            parse_mode=parse_mode,
        )
        register_message(edited, snapshot.options, snapshot.media_paths)
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(lambda message: _matches_button("btn_welcome_mailing", message.text))
async def welcome_mailing(message: Message, state: FSMContext) -> None:
    await mailing_new(message, state)


@router.message(lambda message: _matches_button("btn_welcome_parsing", message.text))
async def welcome_parsing(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("parse_prompt", locale))


@router.message(lambda message: _matches_button("btn_parsed_users_db", message.text))
async def welcome_parsed_users(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await send_parsed_users_file(message, locale)


@router.message(lambda message: _matches_button("btn_welcome_profile", message.text))
async def welcome_profile(message: Message) -> None:
    await account_list(message)


@router.message(lambda message: _matches_button("btn_welcome_accounts", message.text))
async def welcome_accounts(message: Message) -> None:
    await account_list(message)


@router.message(lambda message: _matches_button("btn_welcome_manuals", message.text))
async def welcome_manuals(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("manuals_info", locale))


@router.message(lambda message: _matches_button("btn_welcome_tasks", message.text))
async def welcome_tasks(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Mailing).where(Mailing.owner_id == message.from_user.id))
        mailings = result.scalars().all()
    if not mailings:
        await message.answer(t("mailing_none", locale))
        return
    await message.answer(
        t("mailing_choose", locale),
        reply_markup=mailing_list_keyboard(mailings, locale, back_callback="mailing:back:menu"),
    )


@router.message(lambda message: _matches_button("btn_welcome_franchise", message.text))
async def welcome_franchise(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("franchise_info", locale))


@router.message(lambda message: _looks_like_chat(message.text))
async def parse_link_message(message: Message) -> None:
    chat = (message.text or "").strip()
    if not chat:
        return
    await _parse_chat_for_user(message, chat)
