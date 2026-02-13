from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from typing import Optional
from io import StringIO

from sqlalchemy import select

from app.bot.history import edit_with_history
from app.bot.handlers.common import is_admin, is_admin_user_id, resolve_locale
from app.db.models import ParsedUser, ParseFilter, BotSubscriber, ReferralReward
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.bot.keyboards import (
    add_account_keyboard,
    admin_menu_keyboard,
    admin_panel_keyboard,
    back_to_menu_keyboard,
    account_auth_method_keyboard,
    parse_account_keyboard,
    parse_filters_keyboard,
    parse_history_scope_keyboard,
    parse_mode_keyboard,
    price_keys_keyboard,
    mailing_tariff_keys_keyboard,
    step_back_keyboard,
)
from app.services.auth import AccountService
from app.bot.handlers.accounts import AccountStates
from app.services.billing import BillingService
from app.services.parser import ParserService
from app.services.settings import get_setting, set_setting, SUPPORT_CONTACT_KEY
from app.client.telethon_manager import TelethonManager
from telethon import errors as telethon_errors
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError


router = Router()
_manager = TelethonManager()

PARSE_FILTER_DEFAULTS = {
    "status": "all",
    "gender": "any",
    "language": "any",
    "activity": "any",
}


async def _get_or_create_parse_filters(session, owner_id: int) -> ParseFilter:
    result = await session.execute(select(ParseFilter).where(ParseFilter.owner_id == owner_id))
    filters = result.scalars().first()
    if filters:
        return filters
    filters = ParseFilter(owner_id=owner_id, **PARSE_FILTER_DEFAULTS)
    session.add(filters)
    await session.commit()
    return filters


def _filters_to_dict(filters: ParseFilter) -> dict:
    return {
        "status": filters.status or "all",
        "gender": filters.gender or "any",
        "language": filters.language or "any",
        "activity": filters.activity or "any",
    }


def _cycle_filter(value: str, options: list[str]) -> str:
    if value not in options:
        return options[0]
    idx = options.index(value)
    return options[(idx + 1) % len(options)]


class ParseStates(StatesGroup):
    account = State()
    mode = State()
    history_scope = State()
    history_limit = State()
    chat = State()


class AdminPanelStates(StatesGroup):
    price_set = State()
    price_set_value = State()
    mailing_tariff_set = State()
    mailing_tariff_set_value = State()
    balance_add = State()
    support_set = State()


async def _apply_referral_reward(session, user_id: int, amount: float, source_tx_id: int) -> None:
    if amount <= 0:
        return
    result = await session.execute(select(BotSubscriber).where(BotSubscriber.user_id == user_id))
    subscriber = result.scalars().first()
    if not subscriber or not subscriber.referrer_id:
        return
    existing = await session.execute(
        select(ReferralReward).where(ReferralReward.source_tx_id == source_tx_id)
    )
    if existing.scalars().first():
        return
    settings = await get_setting(session, ["referral_percent"])
    percent_raw = settings.get("referral_percent")
    try:
        percent = float(percent_raw) if percent_raw is not None else 20.0
    except (ValueError, TypeError):
        percent = 20.0
    reward = round(amount * (percent / 100.0), 4)
    if reward <= 0:
        return
    session.add(
        ReferralReward(
            referrer_id=subscriber.referrer_id,
            referral_id=user_id,
            amount=reward,
            source_tx_id=source_tx_id,
        )
    )
    await session.commit()


def _format_parsed_field(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.replace("\t", " ").replace("\n", " ")


async def send_parsed_users_file(message: Message, locale: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(ParsedUser).where(ParsedUser.owner_id == message.from_user.id))
        parsed_users = result.scalars().all()

    if not parsed_users:
        await message.answer(t("parsed_users_empty", locale))
        return

    buffer = StringIO()
    buffer.write("user_id\tusername\tfirst_name\tlast_name\tsource\n")
    for user in parsed_users:
        buffer.write(
            "\t".join(
                [
                    str(user.user_id),
                    _format_parsed_field(user.username),
                    _format_parsed_field(user.first_name),
                    _format_parsed_field(user.last_name),
                    _format_parsed_field(user.source),
                ]
            )
        )
        buffer.write("\n")

    file_content = buffer.getvalue().encode("utf-8")
    filename = f"parsed_users_{message.from_user.id}.txt"
    await message.answer_document(
        BufferedInputFile(file_content, filename=filename),
        caption=t("parsed_users_file_caption", locale),
    )
    await message.answer(t("parsed_users_sent", locale))


async def _render_parse_filters(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        filters = await _get_or_create_parse_filters(session, callback.from_user.id)
        await edit_with_history(
            callback.message,
            t("parse_filters_text", locale),
            reply_markup=parse_filters_keyboard(locale, _filters_to_dict(filters)),
        )
    await callback.answer()


async def _update_parse_filter(callback: CallbackQuery, field: str, options: list[str]) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        filters = await _get_or_create_parse_filters(session, callback.from_user.id)
        current_value = getattr(filters, field, None) or options[0]
        setattr(filters, field, _cycle_filter(current_value, options))
        await session.commit()
    await _render_parse_filters(callback)


@router.callback_query(F.data == "parse:filters")
async def parse_filters_cb(callback: CallbackQuery) -> None:
    await _render_parse_filters(callback)


@router.callback_query(F.data == "parse:filters:status")
async def parse_filters_status_cb(callback: CallbackQuery) -> None:
    await _update_parse_filter(callback, "status", ["all", "admins", "bots", "users"])


@router.callback_query(F.data == "parse:filters:gender")
async def parse_filters_gender_cb(callback: CallbackQuery) -> None:
    await _update_parse_filter(callback, "gender", ["any", "male", "female"])


@router.callback_query(F.data == "parse:filters:language")
async def parse_filters_language_cb(callback: CallbackQuery) -> None:
    await _update_parse_filter(callback, "language", ["any", "ru", "en", "other"])


@router.callback_query(F.data == "parse:filters:activity")
async def parse_filters_activity_cb(callback: CallbackQuery) -> None:
    await _update_parse_filter(callback, "activity", ["any", "online", "recent", "week", "month", "long"])


@router.callback_query(F.data == "parse:filters:reset")
async def parse_filters_reset_cb(callback: CallbackQuery) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        filters = await _get_or_create_parse_filters(session, callback.from_user.id)
        for key, value in PARSE_FILTER_DEFAULTS.items():
            setattr(filters, key, value)
        await session.commit()
    await _render_parse_filters(callback)


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    await message.answer(t("admin_panel_title", locale), reply_markup=admin_panel_keyboard(locale))


@router.callback_query(F.data == "admin:prices")
async def admin_prices_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        prices = await billing.list_prices()
    if not prices:
        await edit_with_history(callback.message, t("price_list_empty", locale), reply_markup=admin_panel_keyboard(locale))
        await callback.answer()
        return
    lines = [t("price_list_title", locale)]
    for row in prices:
        lines.append(f"{row.key}: {row.price}")
    await edit_with_history(callback.message, "\n".join(lines), reply_markup=admin_panel_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "admin:price_set")
async def admin_price_set_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        await callback.answer()
        return
    await edit_with_history(
        callback.message,
        t("admin_price_set_select", locale),
        reply_markup=price_keys_keyboard(locale),
    )
    await state.set_state(AdminPanelStates.price_set)
    await callback.answer()


@router.callback_query(F.data == "admin:mailing_tariffs")
async def admin_mailing_tariffs_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        return
    await edit_with_history(
        callback.message,
        t("admin_mailing_tariff_select", locale),
        reply_markup=mailing_tariff_keys_keyboard(locale),
    )
    await state.set_state(AdminPanelStates.mailing_tariff_set)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:price:key:"))
async def admin_price_key_select_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        await callback.answer()
        return
    key = callback.data.split(":")[-1]
    await state.update_data(price_key=key)
    await edit_with_history(
        callback.message,
        t("admin_price_set_value", locale).format(key=key),
        reply_markup=step_back_keyboard(locale, "back:prev"),
    )
    await state.set_state(AdminPanelStates.price_set_value)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mailing_tariff:key:"))
async def admin_mailing_tariff_key_select_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        return
    key = callback.data.split(":")[-1]
    await state.update_data(mailing_tariff_key=key)
    session_factory = get_session_factory()
    async with session_factory() as session:
        current = await get_setting(session, key)
    await edit_with_history(
        callback.message,
        t("admin_mailing_tariff_value", locale).format(key=key, current=current or "-"),
        reply_markup=back_to_menu_keyboard(locale),
    )
    await state.set_state(AdminPanelStates.mailing_tariff_set_value)
    await callback.answer()


@router.message(AdminPanelStates.price_set_value)
async def admin_price_set_value_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    data = await state.get_data()
    key = data.get("price_key")
    if not key:
        await message.answer(t("admin_price_set_select", locale))
        await state.clear()
        return
    try:
        price = float((message.text or "").strip())
    except ValueError:
        await message.answer(t("admin_price_set_value", locale).format(key=key))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
    value = await billing.set_price(key, price)
    await message.answer(t("price_set_done", locale).format(key=key, price=value))
    await state.clear()


@router.message(AdminPanelStates.mailing_tariff_set_value)
async def admin_mailing_tariff_set_value_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    data = await state.get_data()
    key = data.get("mailing_tariff_key")
    if not key:
        await message.answer(t("admin_mailing_tariff_select", locale))
        return
    try:
        value = float((message.text or "").strip())
    except ValueError:
        await message.answer(t("admin_mailing_tariff_value", locale).format(key=key, current="-"))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, key, str(value))
    await message.answer(t("admin_mailing_tariff_done", locale).format(key=key, value=value))
    await state.clear()

@router.callback_query(F.data == "admin:balance_add")
async def admin_balance_add_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        await callback.answer()
        return
    await edit_with_history(
        callback.message,
        t("admin_balance_add_prompt", locale),
        reply_markup=step_back_keyboard(locale, "back:prev"),
    )
    await state.set_state(AdminPanelStates.balance_add)
    await callback.answer()


@router.callback_query(F.data == "admin:support_set")
async def admin_support_set_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if not is_admin_user_id(callback.from_user.id):
        await callback.message.answer(t("admin_only", locale))
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        current = await get_setting(session, SUPPORT_CONTACT_KEY)
    await edit_with_history(
        callback.message,
        t("admin_support_set_prompt", locale).format(current=current or "-"),
        reply_markup=back_to_menu_keyboard(locale),
    )
    await state.set_state(AdminPanelStates.support_set)
    await callback.answer()


@router.message(AdminPanelStates.balance_add)
async def admin_balance_add_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(t("admin_balance_add_prompt", locale))
        return
    try:
        user_id = int(parts[0])
        amount = float(parts[1])
    except ValueError:
        await message.answer(t("admin_balance_add_prompt", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        balance, tx_id = await billing.add_balance(user_id, amount, reason="admin_topup")
        await _apply_referral_reward(session, user_id, amount, tx_id)
    await message.answer(t("balance_updated", locale).format(user_id=user_id, balance=balance))
    await state.clear()


@router.message(AdminPanelStates.support_set)
async def admin_support_set_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    value = (message.text or "").strip()
    if not value:
        await message.answer(t("admin_support_set_prompt", locale).format(current="-"))
        return
    clear_tokens = {"-", "remove", "clear", "reset", "удалить", "очистить", "скинути", "очистити"}
    if value.lower() in clear_tokens:
        value = ""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, SUPPORT_CONTACT_KEY, value)
    await message.answer(t("admin_support_set_done", locale).format(value=value or "-"))
    await state.clear()


@router.message(Command("balance_add"))
async def balance_add(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(t("balance_add_usage", locale))
        return
    try:
        user_id = int(parts[1])
        amount = float(parts[2])
    except ValueError:
        await message.answer(t("balance_add_usage", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
    balance, tx_id = await billing.add_balance(user_id, amount, reason="admin_topup")
    await _apply_referral_reward(session, user_id, amount, tx_id)
    await message.answer(t("balance_updated", locale).format(user_id=user_id, balance=balance))


@router.message(Command("price_set"))
async def price_set(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(t("price_set_usage", locale))
        return
    key = parts[1].strip()
    try:
        price = float(parts[2])
    except ValueError:
        await message.answer(t("price_set_usage", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        value = await billing.set_price(key, price)
    await message.answer(t("price_set_done", locale).format(key=key, price=value))


@router.message(Command("prices"))
async def prices_list(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        prices = await billing.list_prices()
    if not prices:
        await message.answer(t("price_list_empty", locale))
        return
    lines = [t("price_list_title", locale)]
    for row in prices:
        lines.append(f"{row.key}: {row.price}")
    await message.answer("\n".join(lines))


async def _parse_chat_for_user(message: Message, chat: str) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        account = await service.get_active_account(message.from_user.id)
        if not account:
            await message.answer(t("no_account", locale), reply_markup=add_account_keyboard(locale))
            return
        
        await message.answer(t("parse_starting", locale))

        billing = BillingService(session)
        price = await billing.get_price("parse_participants_user")
        max_users = None
        if price > 0:
            balance = await billing.get_balance(message.from_user.id)
            max_users = int(balance // price)
            if max_users <= 0:
                await message.answer(t("balance_insufficient", locale))
                return
        parser = ParserService(session, _manager)
        try:
            count = await parser.parse_chat(account, message.from_user.id, chat, max_users=max_users)
        except AuthKeyUnregisteredError:
            await service.set_active(message.from_user.id, account.id, False)
            await message.answer(t("account_not_bound", locale).format(phone=account.phone))
            return
        except telethon_errors.RPCError as err:
            if isinstance(err, telethon_errors.UnauthorizedError) or "UNAUTHORIZED" in getattr(err, "message", ""):
                await message.answer(t("parse_unauthorized", locale))
            else:
                await message.answer(t("parse_failed", locale).format(error=getattr(err, "message", "RPC error")))
            return
        if price > 0 and count:
            await billing.charge(message.from_user.id, count * price, reason="parse_participants_user")
        await message.answer(t("parse_done", locale).format(count=count))


@router.message(Command("parse"))
async def parse_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(t("parse_prompt", locale))
        return
    await _parse_chat_for_user(message, parts[1].strip())


@router.message(Command("parse_chats"))
async def parse_chats_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        account = await AccountService(session).get_active_account(message.from_user.id)
        if not account:
            await message.answer(t("no_account", locale), reply_markup=add_account_keyboard(locale))
            return
        billing = BillingService(session)
        price = await billing.get_price("parse_chats_chat")
        max_chats = None
        if price > 0:
            balance = await billing.get_balance(message.from_user.id)
            max_chats = int(balance // price)
            if max_chats <= 0:
                await message.answer(t("balance_insufficient", locale))
                return
        parser = ParserService(session, _manager)
        count = await parser.parse_groups(account, message.from_user.id, max_chats=max_chats)
        if price > 0 and count:
            await billing.charge(message.from_user.id, count * price, reason="parse_chats_chat")
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
    parse_kind = data.get("parse_kind") or "participants"
    history_limit = data.get("history_limit")
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        if account_id is None:
            account = await service.get_active_account(message.from_user.id)
        else:
            accounts = await service.list_accounts(message.from_user.id)
            account = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            await message.answer(t("no_account", locale), reply_markup=add_account_keyboard(locale))
            await state.clear()
            return
        billing = BillingService(session)
        price_key = "parse_history_user" if parse_kind == "history" else "parse_participants_user"
        price = await billing.get_price(price_key)
        max_users = None
        if price > 0:
            balance = await billing.get_balance(message.from_user.id)
            max_users = int(balance // price)
            if max_users <= 0:
                await message.answer(t("balance_insufficient", locale))
                await state.clear()
                return
        parser = ParserService(session, _manager)
        try:
            if parse_kind == "history":
                count = await parser.parse_chat_history(
                    account,
                    message.from_user.id,
                    chat,
                    limit_messages=history_limit or 0,
                    include_mentions=True,
                    include_replies=True,
                    max_users=max_users,
                )
            else:
                count = await parser.parse_chat(account, message.from_user.id, chat, max_users=max_users)
        except AuthKeyUnregisteredError:
            await service.set_active(message.from_user.id, account.id, False)
            await message.answer(t("account_not_bound", locale).format(phone=account.phone))
            await state.clear()
            return
        except telethon_errors.RPCError as err:
            if isinstance(err, telethon_errors.UnauthorizedError) or "UNAUTHORIZED" in getattr(err, "message", ""):
                await message.answer(t("parse_unauthorized", locale))
            else:
                await message.answer(t("parse_failed", locale).format(error=getattr(err, "message", "RPC error")))
            await state.clear()
            return
        if price > 0 and count:
            reason = "parse_history_user" if parse_kind == "history" else "parse_participants_user"
            await billing.charge(message.from_user.id, count * price, reason=reason)
        await message.answer(t("parse_done", locale).format(count=count))
    await state.clear()


@router.callback_query(F.data == "parse:start")
async def parse_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
    if not accounts:
        await edit_with_history(
            callback.message,
            t("no_account", locale),
            reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
        )
        await callback.answer()
        return
    await edit_with_history(callback.message, 
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
        await edit_with_history(
            callback.message,
            t("no_account", locale),
            reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
        )
        await callback.answer()
        return
    await edit_with_history(callback.message, 
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
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        if account_id is None:
            account = await service.get_active_account(callback.from_user.id)
        else:
            accounts = await service.list_accounts(callback.from_user.id)
            account = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            await edit_with_history(
                callback.message,
                t("no_account", locale),
                reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
            )
            await callback.answer()
            return
        if not account.is_active:
            await service.delete_account(callback.from_user.id, account.id)
            await edit_with_history(
                callback.message,
                t("account_not_bound", locale).format(phone=account.phone),
                reply_markup=account_auth_method_keyboard(locale),
            )
            await state.set_state(AccountStates.method)
            await callback.answer()
            return
        try:
            client = await _manager.get_client(account)
            authorized = await client.is_user_authorized()
            if not authorized:
                raise AuthKeyUnregisteredError(request=None)
            await client.get_me()
        except AuthKeyUnregisteredError:
            await service.set_active(callback.from_user.id, account.id, False)
            await service.delete_account(callback.from_user.id, account.id)
            await edit_with_history(
                callback.message,
                t("account_not_bound", locale).format(phone=account.phone),
                reply_markup=account_auth_method_keyboard(locale),
            )
            await state.set_state(AccountStates.method)
            await callback.answer()
            return
        except telethon_errors.RPCError as err:
            if isinstance(err, telethon_errors.UnauthorizedError) or "UNAUTHORIZED" in getattr(err, "message", ""):
                await edit_with_history(callback.message, t("parse_unauthorized", locale), reply_markup=back_to_menu_keyboard(locale))
            else:
                await edit_with_history(
                    callback.message,
                    t("parse_failed", locale).format(error=getattr(err, "message", "RPC error")),
                    reply_markup=back_to_menu_keyboard(locale),
                )
            await callback.answer()
            return

    await state.update_data(account_id=account_id, parse_kind=None, history_limit=None)
    await edit_with_history(
        callback.message,
        t("parse_mode_prompt", locale),
        reply_markup=parse_mode_keyboard(locale, "users"),
    )
    await state.set_state(ParseStates.mode)
    await callback.answer()


@router.callback_query(F.data.in_(["parse:users:mode:participants", "parse:users:mode:history"]))
async def parse_users_mode_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    kind = callback.data.split(":")[-1]
    await state.update_data(parse_kind=kind)
    if kind == "participants":
        await edit_with_history(callback.message, t("parse_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
        await state.set_state(ParseStates.chat)
        await callback.answer()
        return
    await edit_with_history(
        callback.message,
        t("parse_history_scope_prompt", locale),
        reply_markup=parse_history_scope_keyboard(locale, "users"),
    )
    await state.set_state(ParseStates.history_scope)
    await callback.answer()


@router.callback_query(F.data.in_(["parse:users:history:all", "parse:users:history:limit"]))
async def parse_users_history_scope_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    scope = callback.data.split(":")[-1]
    if scope == "all":
        await state.update_data(history_limit=None)
        await edit_with_history(callback.message, t("parse_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
        await state.set_state(ParseStates.chat)
        await callback.answer()
        return
    await edit_with_history(callback.message, t("parse_history_limit_prompt", locale))
    await state.set_state(ParseStates.history_limit)
    await callback.answer()


@router.message(ParseStates.history_limit)
async def parse_users_history_limit_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    raw = (message.text or "").strip()
    try:
        limit = int(raw)
        if limit <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t("parse_history_limit_invalid", locale))
        return
    await state.update_data(history_limit=limit)
    await message.answer(t("parse_prompt", locale))
    await state.set_state(ParseStates.chat)


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
            await edit_with_history(
                callback.message,
                t("no_account", locale),
                reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
            )
            await callback.answer()
            return
        billing = BillingService(session)
        price = await billing.get_price("parse_chats_chat")
        max_chats = None
        if price > 0:
            balance = await billing.get_balance(callback.from_user.id)
            max_chats = int(balance // price)
            if max_chats <= 0:
                await edit_with_history(callback.message, t("balance_insufficient", locale))
                await callback.answer()
                return
        parser = ParserService(session, _manager)
        count = await parser.parse_groups(account, callback.from_user.id, max_chats=max_chats)
        if price > 0 and count:
            await billing.charge(callback.from_user.id, count * price, reason="parse_chats_chat")
        await edit_with_history(callback.message, t("parse_chats_done", locale).format(count=count), reply_markup=back_to_menu_keyboard(locale))
    await callback.answer()
