from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import is_admin, resolve_locale
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.bot.keyboards import admin_menu_keyboard, back_to_menu_keyboard, parse_account_keyboard
from app.services.auth import AccountService
from app.services.parser import ParserService
from app.client.telethon_manager import TelethonManager


router = Router()
_manager = TelethonManager()


class ParseStates(StatesGroup):
    account = State()
    chat = State()


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    await message.answer(t("menu", locale), reply_markup=admin_menu_keyboard(locale))


@router.message(Command("parse"))
async def parse_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(t("parse_prompt", locale))
        return

    chat = parts[1].strip()
    session_factory = get_session_factory()
    async with session_factory() as session:
        account = await AccountService(session).get_active_account(message.from_user.id)
        if not account:
            await message.answer(t("no_account", locale))
            return
        parser = ParserService(session, _manager)
        count = await parser.parse_chat(account, message.from_user.id, chat)
        await message.answer(t("parse_done", locale).format(count=count))


@router.message(Command("parse_chats"))
async def parse_chats_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        account = await AccountService(session).get_active_account(message.from_user.id)
        if not account:
            await message.answer(t("no_account", locale))
            return
        parser = ParserService(session, _manager)
        count = await parser.parse_groups(account, message.from_user.id)
        await message.answer(t("parse_chats_done", locale).format(count=count))


@router.message(ParseStates.chat)
async def parse_chat_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    chat = (message.text or "").strip()
    if not chat:
        await message.answer(t("parse_prompt", locale))
        return
    data = await state.get_data()
    account_id = data.get("account_id")
    session_factory = get_session_factory()
    async with session_factory() as session:
        if account_id is None:
            account = await AccountService(session).get_active_account(message.from_user.id)
        else:
            accounts = await AccountService(session).list_accounts(message.from_user.id)
            account = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            await message.answer(t("no_account", locale))
            await state.clear()
            return
        parser = ParserService(session, _manager)
        count = await parser.parse_chat(account, message.from_user.id, chat)
        await message.answer(t("parse_done", locale).format(count=count))
    await state.clear()


@router.callback_query(F.data == "parse:start")
async def parse_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
    if not accounts:
        await callback.message.edit_text(t("no_account", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await callback.message.edit_text(
        t("parse_account", locale),
        reply_markup=parse_account_keyboard(accounts, locale, "users"),
    )
    await state.set_state(ParseStates.account)
    await state.update_data(parse_mode="users")
    await callback.answer()


@router.callback_query(F.data == "parse:chats")
async def parse_chats_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
    if not accounts:
        await callback.message.edit_text(t("no_account", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await callback.message.edit_text(
        t("parse_account", locale),
        reply_markup=parse_account_keyboard(accounts, locale, "chats"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("parse:users:account:"))
async def parse_account_users_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    value = callback.data.split(":")[-1]
    account_id = None
    if value != "active":
        try:
            account_id = int(value)
        except ValueError:
            await callback.answer()
            return
    await state.update_data(account_id=account_id)
    await callback.message.edit_text(t("parse_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(ParseStates.chat)
    await callback.answer()


@router.callback_query(F.data.startswith("parse:chats:account:"))
async def parse_account_chats_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    value = callback.data.split(":")[-1]
    account_id = None
    if value != "active":
        try:
            account_id = int(value)
        except ValueError:
            await callback.answer()
            return
    session_factory = get_session_factory()
    async with session_factory() as session:
        if account_id is None:
            account = await AccountService(session).get_active_account(callback.from_user.id)
        else:
            accounts = await AccountService(session).list_accounts(callback.from_user.id)
            account = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            await callback.message.edit_text(t("no_account", locale))
            await callback.answer()
            return
        parser = ParserService(session, _manager)
        count = await parser.parse_groups(account, callback.from_user.id)
        await callback.message.edit_text(t("parse_chats_done", locale).format(count=count), reply_markup=back_to_menu_keyboard(locale))
    await callback.answer()
