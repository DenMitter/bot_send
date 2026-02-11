import os
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, Message
import json
from sqlalchemy import func, select
from telethon import errors as telethon_errors
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError

from app.bot.history import capture_previous_message, clear_history, edit_with_history, register_message, set_welcome_page
from app.bot.handlers.common import is_admin, resolve_locale, build_mailing_intro
from app.bot.keyboards import (
    account_select_keyboard,
    add_account_keyboard,
    back_to_menu_keyboard,
    chats_scope_keyboard,
    chats_select_keyboard,
    account_auth_method_keyboard,
    mailing_mention_keyboard,
    mailing_actions_keyboard,
    mailing_details_keyboard,
    mailing_list_keyboard,
    mailing_recipients_keyboard,
    mailing_source_keyboard,
    step_back_keyboard,
    welcome_entry_keyboard,
    mailing_settings_keyboard,
    mailing_timing_keyboard,
    mailing_mentions_keyboard,
    mailing_accounts_keyboard,
)
from app.client.telethon_manager import TelethonManager
from app.core.config import get_settings
from app.db.models import BotSubscriber, Mailing, MailingRecipient, MessageType, ParsedChat, ParsedUser, TargetSource
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.services.auth import AccountService
from app.services.billing import BillingService
from app.services.mailing.logs import get_mailing_log_path
from app.services.mailing.service import MailingService
from app.services.parser import ParserService
from app.services.settings import get_setting, set_setting
from typing import Optional, Dict
from app.bot.handlers.accounts import AccountStates


router = Router()
_parser_manager = TelethonManager()

RECIPIENTS_PAGE_SIZE = 10


class MailingStates(StatesGroup):
    account = State()
    source = State()
    chats_scope = State()
    chat_select = State()
    mention = State()
    delay = State()
    limit = State()
    repeat_delay = State()
    repeat_count = State()
    content = State()


class MailingControlStates(StatesGroup):
    id_action = State()


class MailingEditStates(StatesGroup):
    content = State()


class MailingSettingsStates(StatesGroup):
    message = State()
    timing_chats = State()
    timing_rounds = State()


async def _load_mailing_template(session) -> Optional[Dict]:
    raw = await get_setting(session, "mailing_template")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


async def _apply_global_settings_to_state(state: FSMContext, session) -> dict:
    mentions_raw = await get_setting(session, "mailing_mentions_enabled")
    timing_chats = await get_setting(session, "mailing_timing_chats")
    timing_rounds = await get_setting(session, "mailing_timing_rounds")
    template = await _load_mailing_template(session)

    if mentions_raw in ("1", "0"):
        await state.update_data(mention=mentions_raw == "1")
    if timing_chats is not None:
        try:
            await state.update_data(delay=max(0.0, float(timing_chats)))
        except ValueError:
            pass
    if timing_rounds is not None:
        try:
            await state.update_data(repeat_delay=max(0.0, float(timing_rounds)))
        except ValueError:
            pass
    if template:
        await state.update_data(template_payload=template)

    return {
        "mentions": mentions_raw in ("1", "0"),
        "timing_chats": timing_chats is not None,
        "timing_rounds": timing_rounds is not None,
        "template": bool(template),
    }


async def _finalize_mailing_with_content(message: Message, state: FSMContext, content: dict) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    data = await state.get_data()
    source_value = data.get("source")
    if source_value == "subscribers":
        source = TargetSource.subscribers
    elif source_value == "chats":
        source = TargetSource.chats
    else:
        source = TargetSource.parsed
    mention = bool(data.get("mention"))
    delay = float(data.get("delay"))
    limit = int(data.get("limit"))
    repeat_delay = float(data.get("repeat_delay") or 0)
    repeat_count = int(data.get("repeat_count") or 1)
    account_id = data.get("account_id")
    chat_id = data.get("chat_id")
    chat_ids = data.get("chat_ids")

    message_type = content["message_type"]
    text = content.get("text")
    media_path = content.get("media_path")
    media_file_id = content.get("media_file_id")
    sticker_set_name = content.get("sticker_set_name")
    sticker_set_index = content.get("sticker_set_index")
    sticker_pack_missing = content.get("sticker_pack_missing")

    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        price_message = await billing.get_price("mailing_message")
        price_mention = await billing.get_price("mailing_message_mention")
        price_per_message = price_message + (price_mention if mention else 0.0)

        if account_id is None:
            account = await AccountService(session).get_active_account(message.from_user.id)
        else:
            accounts = await AccountService(session).list_accounts(message.from_user.id)
            account = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            await message.answer(t("no_account", locale), reply_markup=add_account_keyboard(locale))
            await state.clear()
            return

        mailing = await MailingService(session).create_mailing(
            owner_id=message.from_user.id,
            account_id=account.id,
            chat_id=chat_id,
            target_ids=chat_ids,
            target_source=source,
            message_type=message_type,
            text=text,
            media_path=media_path,
            media_file_id=media_file_id,
            sticker_set_name=sticker_set_name,
            sticker_set_index=sticker_set_index,
            mention=mention,
            delay_seconds=delay,
            limit_count=limit,
            repeat_delay_seconds=repeat_delay,
            repeat_count=repeat_count,
        )
    await message.answer(t("mailing_created", locale).format(id=mailing.id))
    await message.answer(t("mailing_created_hint_tasks", locale))
    await state.clear()


async def _prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    capture_previous_message(message.chat.id)
    sent = await message.answer(text, reply_markup=reply_markup)
    register_message(sent)
    await state.update_data(prompt_id=sent.message_id)


async def _edit_prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    if prompt_id:
        try:
            edited = await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=reply_markup,
            )
            register_message(edited)
            return
        except Exception:
            pass
    await _prompt(message, state, text, reply_markup)


async def _list_accounts(user_id: int):
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(user_id)
    return accounts


async def _extract_mailing_content(message: Message):
    settings = get_settings()
    media_path = None
    media_file_id = None
    sticker_set_name = None
    sticker_set_index = None
    sticker_pack_missing = False
    message_type = MessageType.text
    text = message.text or message.caption or ""

    os.makedirs(settings.media_dir, exist_ok=True)

    if message.photo:
        message_type = MessageType.photo
        file = await message.bot.get_file(message.photo[-1].file_id)
        media_path = os.path.join(settings.media_dir, f"{uuid4().hex}.jpg")
        await message.bot.download_file(file.file_path, media_path)
    elif message.video:
        message_type = MessageType.video
        file = await message.bot.get_file(message.video.file_id)
        media_path = os.path.join(settings.media_dir, f"{uuid4().hex}.mp4")
        await message.bot.download_file(file.file_path, media_path)
    elif message.voice:
        message_type = MessageType.voice
        file = await message.bot.get_file(message.voice.file_id)
        media_path = os.path.join(settings.media_dir, f"{uuid4().hex}.ogg")
        await message.bot.download_file(file.file_path, media_path)
    elif message.audio:
        message_type = MessageType.audio
        file = await message.bot.get_file(message.audio.file_id)
        ext = os.path.splitext(message.audio.file_name or "")[1] or ".mp3"
        media_path = os.path.join(settings.media_dir, f"{uuid4().hex}{ext}")
        await message.bot.download_file(file.file_path, media_path)
    elif message.sticker:
        message_type = MessageType.sticker
        media_file_id = message.sticker.file_id
        sticker_set_name = message.sticker.set_name
        if sticker_set_name:
            try:
                sticker_set = await message.bot.get_sticker_set(sticker_set_name)
                for idx, sticker in enumerate(sticker_set.stickers):
                    if sticker.file_id == media_file_id:
                        sticker_set_index = idx
                        break
            except Exception:
                sticker_set_name = None
                sticker_set_index = None
        if not sticker_set_name:
            sticker_pack_missing = True
            file = await message.bot.get_file(message.sticker.file_id)
            ext = os.path.splitext(file.file_path or "")[1].lower() or ".webp"
            media_path = os.path.join(settings.media_dir, f"{uuid4().hex}{ext}")
            await message.bot.download_file(file.file_path, media_path)
    elif message.document:
        message_type = MessageType.document
        file = await message.bot.get_file(message.document.file_id)
        media_path = os.path.join(settings.media_dir, f"{uuid4().hex}_{message.document.file_name}")
        await message.bot.download_file(file.file_path, media_path)

    if media_path:
        media_path = os.path.abspath(media_path)
    return (
        message_type,
        text,
        media_path,
        media_file_id,
        sticker_set_name,
        sticker_set_index,
        sticker_pack_missing,
    )


@router.message(Command("mailing_new"))
async def mailing_new(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await state.clear()
    accounts = await _list_accounts(message.from_user.id)
    if not accounts:
        await message.answer(t("no_account", locale), reply_markup=add_account_keyboard(locale))
        return
    await _prompt(message, state, t("mailing_account", locale), reply_markup=account_select_keyboard(accounts, locale))
    await state.set_state(MailingStates.account)


@router.callback_query(F.data.startswith("mailing:account:"))
async def mailing_account_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    account_value = callback.data.split(":")[-1]
    account_id = None
    if account_value != "active":
        try:
            account_id = int(account_value)
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
            client = await _parser_manager.get_client(account)
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

    await state.update_data(account_id=account_id)
    await edit_with_history(callback.message, 
        t("mailing_source", locale),
        reply_markup=mailing_source_keyboard(locale, is_admin(callback.message)),
    )
    await state.set_state(MailingStates.source)
    await state.update_data(prompt_id=callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:menu")
async def mailing_back_menu_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    clear_history(callback.message.chat.id)
    set_welcome_page(callback.message.chat.id, 1)
    await edit_with_history(
        callback.message,
        t("welcome_caption", locale),
        reply_markup=welcome_entry_keyboard(locale),
    )
    await callback.answer()


@router.callback_query(F.data.in_(["mailing:source:subscribers", "mailing:source:parsed", "mailing:source:chats"]))
async def mailing_source_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    value = callback.data.split(":")[-1]
    if value == "subscribers" and not is_admin(callback.message):
        await callback.answer(t("admin_only", locale), show_alert=True)
        return
    await state.update_data(source=value)
    if value == "chats":
        await edit_with_history(callback.message, t("mailing_chats_scope", locale), reply_markup=chats_scope_keyboard(locale))
        await state.set_state(MailingStates.chats_scope)
    else:
        await edit_with_history(callback.message, t("mailing_mention", locale), reply_markup=mailing_mention_keyboard(locale))
        await state.set_state(MailingStates.mention)
    await state.update_data(prompt_id=callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:account")
async def mailing_back_account_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    accounts = await _list_accounts(callback.from_user.id)
    if not accounts:
        await edit_with_history(
            callback.message,
            t("no_account", locale),
            reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
        )
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_account", locale),
        reply_markup=account_select_keyboard(accounts, locale),
    )
    await state.set_state(MailingStates.account)
    await callback.answer()


@router.callback_query(F.data.in_(["mailing:chats:all", "mailing:chats:select", "mailing:chats:back"]))
async def mailing_chats_scope_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    action = callback.data.split(":")[-1]
    if action == "back":
        await edit_with_history(callback.message, t("mailing_chats_scope", locale), reply_markup=chats_scope_keyboard(locale))
        await state.set_state(MailingStates.chats_scope)
        await callback.answer()
        return
    if action == "all":
        session_factory = get_session_factory()
        async with session_factory() as session:
            applied = await _apply_global_settings_to_state(state, session)
        await state.update_data(chat_id=None)
        if not applied["mentions"]:
            await edit_with_history(callback.message, t("mailing_mention", locale), reply_markup=mailing_mention_keyboard(locale))
            await state.set_state(MailingStates.mention)
        elif not applied["timing_chats"]:
            await edit_with_history(callback.message, t("mailing_delay", locale))
            await state.set_state(MailingStates.delay)
            await state.update_data(prompt_id=callback.message.message_id)
        else:
            await edit_with_history(
                callback.message,
                t("mailing_limit", locale),
                reply_markup=step_back_keyboard(locale, "mailing:back:delay"),
            )
            await state.set_state(MailingStates.limit)
        await callback.answer()
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        data = await state.get_data()
        account_id = data.get("account_id")
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
        parser = ParserService(session, _parser_manager)
        try:
            client = await _parser_manager.get_client(account)
            authorized = await client.is_user_authorized()
            if not authorized:
                raise AuthKeyUnregisteredError(request=None)
            await parser.parse_groups(account, callback.from_user.id)
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
                await callback.answer(t("parse_unauthorized", locale), show_alert=True)
            else:
                await callback.answer(
                    t("parse_failed", locale).format(error=getattr(err, "message", "RPC error")),
                    show_alert=True,
                )
            return
        result = await session.execute(
            select(ParsedChat).where(ParsedChat.owner_id == callback.from_user.id).limit(20)
        )
        chats = result.scalars().all()
    if not chats:
        await edit_with_history(callback.message, t("mailing_chats_scope", locale), reply_markup=chats_scope_keyboard(locale))
        await state.set_state(MailingStates.chats_scope)
        await callback.answer()
        return
    await state.update_data(selected_chat_ids=[])
    await edit_with_history(callback.message, 
        f"{t('mailing_choose_chat', locale)}\n{t('mailing_choose_chat_hint', locale)}",
        reply_markup=chats_select_keyboard(chats, [], locale),
    )
    await state.set_state(MailingStates.chat_select)
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:chat:"))
async def mailing_chat_select_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        chat_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    selected = set(data.get("selected_chat_ids") or [])
    if chat_id in selected:
        selected.remove(chat_id)
    else:
        selected.add(chat_id)
    await state.update_data(selected_chat_ids=list(selected))

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ParsedChat).where(ParsedChat.owner_id == callback.from_user.id).limit(20)
        )
        chats = result.scalars().all()
    await edit_with_history(callback.message, 
        f"{t('mailing_choose_chat', locale)}\n{t('mailing_choose_chat_hint', locale)}",
        reply_markup=chats_select_keyboard(chats, list(selected), locale),
    )
    await callback.answer()


@router.callback_query(F.data == "mailing:chats:done")
async def mailing_chats_done_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    data = await state.get_data()
    selected = data.get("selected_chat_ids") or []
    if not selected:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(ParsedChat).where(ParsedChat.owner_id == callback.from_user.id).limit(20)
            )
            chats = result.scalars().all()
        await edit_with_history(callback.message, 
            f"{t('mailing_choose_chat', locale)}\n{t('mailing_need_chat', locale)}",
            reply_markup=chats_select_keyboard(chats, [], locale),
        )
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        applied = await _apply_global_settings_to_state(state, session)
    await state.update_data(chat_ids=selected)
    if not applied["mentions"]:
        await edit_with_history(callback.message, t("mailing_mention", locale), reply_markup=mailing_mention_keyboard(locale))
        await state.set_state(MailingStates.mention)
    elif not applied["timing_chats"]:
        await edit_with_history(callback.message, t("mailing_delay", locale))
        await state.set_state(MailingStates.delay)
        await state.update_data(prompt_id=callback.message.message_id)
    else:
        await edit_with_history(
            callback.message,
            t("mailing_limit", locale),
            reply_markup=step_back_keyboard(locale, "mailing:back:delay"),
        )
        await state.set_state(MailingStates.limit)
    await callback.answer()


@router.callback_query(F.data.in_(["mailing:mention:yes", "mailing:mention:no"]))
async def mailing_mention_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    value = callback.data.split(":")[-1]
    await state.update_data(mention=value == "yes")
    await edit_with_history(callback.message, t("mailing_delay", locale))
    await state.set_state(MailingStates.delay)
    await state.update_data(prompt_id=callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:source")
async def mailing_back_source_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, 
        t("mailing_source", locale),
        reply_markup=mailing_source_keyboard(locale, is_admin(callback.message)),
    )
    await state.set_state(MailingStates.source)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:mention")
async def mailing_back_mention_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_mention", locale), reply_markup=mailing_mention_keyboard(locale))
    await state.set_state(MailingStates.mention)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:delay")
async def mailing_back_delay_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_delay", locale), reply_markup=step_back_keyboard(locale, "mailing:back:mention"))
    await state.set_state(MailingStates.delay)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:limit")
async def mailing_back_limit_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_limit", locale), reply_markup=step_back_keyboard(locale, "mailing:back:delay"))
    await state.set_state(MailingStates.limit)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:repeat_delay")
async def mailing_back_repeat_delay_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(
        callback.message,
        t("mailing_repeat_delay", locale),
        reply_markup=step_back_keyboard(locale, "mailing:back:limit"),
    )
    await state.set_state(MailingStates.repeat_delay)
    await callback.answer()


@router.callback_query(F.data == "mailing:back:repeat_count")
async def mailing_back_repeat_count_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(
        callback.message,
        t("mailing_repeat_count", locale),
        reply_markup=step_back_keyboard(locale, "mailing:back:repeat_delay"),
    )
    await state.set_state(MailingStates.repeat_count)
    await callback.answer()


@router.message(MailingStates.delay)
async def mailing_delay(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        delay = float((message.text or "").strip())
    except ValueError:
        await _edit_prompt(message, state, t("mailing_delay", locale), reply_markup=step_back_keyboard(locale, "mailing:back:mention"))
        return
    await state.update_data(delay=delay)
    await _edit_prompt(message, state, t("mailing_limit", locale), reply_markup=step_back_keyboard(locale, "mailing:back:delay"))
    await state.set_state(MailingStates.limit)


@router.message(MailingStates.limit)
async def mailing_limit(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        limit = int((message.text or "").strip())
    except ValueError:
        await _edit_prompt(message, state, t("mailing_limit", locale), reply_markup=step_back_keyboard(locale, "mailing:back:delay"))
        return
    await state.update_data(limit=limit)
    data = await state.get_data()
    if data.get("repeat_delay") is not None:
        await _edit_prompt(
            message,
            state,
            t("mailing_repeat_count", locale),
            reply_markup=step_back_keyboard(locale, "mailing:back:repeat_delay"),
        )
        await state.set_state(MailingStates.repeat_count)
    else:
        await _edit_prompt(
            message,
            state,
            t("mailing_repeat_delay", locale),
            reply_markup=step_back_keyboard(locale, "mailing:back:limit"),
        )
        await state.set_state(MailingStates.repeat_delay)


@router.message(MailingStates.repeat_delay)
async def mailing_repeat_delay(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        delay = float((message.text or "").strip())
        if delay < 0:
            raise ValueError
    except ValueError:
        await _edit_prompt(
            message,
            state,
            t("mailing_repeat_delay", locale),
            reply_markup=step_back_keyboard(locale, "mailing:back:limit"),
        )
        return
    await state.update_data(repeat_delay=delay)
    await _edit_prompt(
        message,
        state,
        t("mailing_repeat_count", locale),
        reply_markup=step_back_keyboard(locale, "mailing:back:repeat_delay"),
    )
    await state.set_state(MailingStates.repeat_count)


@router.message(MailingStates.repeat_count)
async def mailing_repeat_count(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        count = int((message.text or "").strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await _edit_prompt(
            message,
            state,
            t("mailing_repeat_count", locale),
            reply_markup=step_back_keyboard(locale, "mailing:back:repeat_delay"),
        )
        return
    await state.update_data(repeat_count=count)
    data = await state.get_data()
    template_payload = data.get("template_payload")
    if template_payload:
        try:
            message_type = MessageType(template_payload.get("message_type", MessageType.text.value))
        except Exception:
            message_type = MessageType.text
        content = {
            "message_type": message_type,
            "text": template_payload.get("text"),
            "media_path": template_payload.get("media_path"),
            "media_file_id": template_payload.get("media_file_id"),
            "sticker_set_name": template_payload.get("sticker_set_name"),
            "sticker_set_index": template_payload.get("sticker_set_index"),
            "sticker_pack_missing": template_payload.get("sticker_pack_missing"),
        }
        await _finalize_mailing_with_content(message, state, content)
        return
    await _edit_prompt(
        message,
        state,
        t("mailing_content", locale),
        reply_markup=step_back_keyboard(locale, "mailing:back:repeat_count"),
    )
    await state.set_state(MailingStates.content)


@router.message(MailingStates.content)
async def mailing_content(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    (
        message_type,
        text,
        media_path,
        media_file_id,
        sticker_set_name,
        sticker_set_index,
        sticker_pack_missing,
    ) = await _extract_mailing_content(message)

    content = {
        "message_type": message_type,
        "text": text,
        "media_path": media_path,
        "media_file_id": media_file_id,
        "sticker_set_name": sticker_set_name,
        "sticker_set_index": sticker_set_index,
        "sticker_pack_missing": sticker_pack_missing,
    }
    await _finalize_mailing_with_content(message, state, content)


@router.callback_query(F.data.startswith("mailing:edit:"))
async def mailing_edit_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        mailing = await MailingService(session).get_mailing(callback.from_user.id, mailing_id)
    if not mailing:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await state.update_data(mailing_id=mailing_id)
    await edit_with_history(callback.message, 
        t("mailing_edit_content", locale),
        reply_markup=step_back_keyboard(locale, f"mailing:select:{mailing_id}"),
    )
    await state.set_state(MailingEditStates.content)
    await callback.answer()


@router.message(MailingEditStates.content)
async def mailing_edit_content(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    data = await state.get_data()
    mailing_id = data.get("mailing_id")
    if not mailing_id:
        await message.answer(t("mailing_not_found", locale))
        await state.clear()
        return
    (
        message_type,
        text,
        media_path,
        media_file_id,
        sticker_set_name,
        sticker_set_index,
        sticker_pack_missing,
    ) = await _extract_mailing_content(message)
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        mailing = await service.get_mailing(message.from_user.id, mailing_id)
        if not mailing:
            await message.answer(t("mailing_not_found", locale))
            await state.clear()
            return
        old_media_path = mailing.media_path
        updated = await service.update_content(
            message.from_user.id,
            mailing_id,
            message_type=message_type,
            text=text,
            media_path=media_path,
            media_file_id=media_file_id,
            sticker_set_name=sticker_set_name,
            sticker_set_index=sticker_set_index,
        )
    if old_media_path and old_media_path != media_path and os.path.isfile(old_media_path):
        try:
            os.remove(old_media_path)
        except OSError:
            pass
    if not updated:
        await message.answer(t("mailing_not_found", locale))
        await state.clear()
        return
    await message.answer(t("mailing_updated", locale).format(id=mailing_id))
    await state.clear()


@router.message(Command("mailing_pause"))
async def mailing_pause(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    mailing_id = int(parts[1].strip())
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await MailingService(session).pause(message.from_user.id, mailing_id)
    await message.answer(t("mailing_paused", locale) if ok else t("mailing_not_found", locale))


@router.message(Command("mailing_resume"))
async def mailing_resume(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    mailing_id = int(parts[1].strip())
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await MailingService(session).resume(message.from_user.id, mailing_id)
    await message.answer(t("mailing_resumed", locale) if ok else t("mailing_not_found", locale))


@router.message(Command("mailing_status"))
async def mailing_status(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    mailing_id = int(parts[1].strip())
    session_factory = get_session_factory()
    async with session_factory() as session:
        status = await MailingService(session).get_status(message.from_user.id, mailing_id)
    if status:
        await message.answer(t("mailing_status", locale).format(status=status.value))
    else:
        await message.answer(t("mailing_not_found", locale))


@router.message(MailingControlStates.id_action)
async def mailing_id_action(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        mailing_id = int((message.text or "").strip())
    except ValueError:
        await message.answer(t("enter_id", locale))
        return
    data = await state.get_data()
    action = data.get("action")
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        if action == "pause":
            ok = await service.pause(message.from_user.id, mailing_id)
            await message.answer(t("mailing_paused", locale) if ok else t("mailing_not_found", locale))
        elif action == "resume":
            ok = await service.resume(message.from_user.id, mailing_id)
            await message.answer(t("mailing_resumed", locale) if ok else t("mailing_not_found", locale))
        elif action == "status":
            status = await service.get_status(message.from_user.id, mailing_id)
            if status:
                await message.answer(t("mailing_status", locale).format(status=status.value))
            else:
                await message.answer(t("mailing_not_found", locale))
    await state.clear()


@router.callback_query(F.data == "mailing:new")
async def mailing_new_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await state.clear()
    accounts = await _list_accounts(callback.from_user.id)
    if not accounts:
        await edit_with_history(
            callback.message,
            t("no_account", locale),
            reply_markup=add_account_keyboard(locale, back_callback="back:prev"),
        )
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_account", locale),
        reply_markup=account_select_keyboard(accounts, locale),
    )
    await state.set_state(MailingStates.account)
    await state.update_data(prompt_id=callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "mailing:settings")
async def mailing_settings_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await state.clear()
    await edit_with_history(
        callback.message,
        t("mailing_settings_text", locale),
        reply_markup=mailing_settings_keyboard(locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:accounts"))
async def mailing_accounts_cb(callback: CallbackQuery) -> None:
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
    data = callback.data.split(":")
    page = 1
    if len(data) >= 4 and data[2] == "page":
        try:
            page = max(1, int(data[3]))
        except ValueError:
            pass
    await edit_with_history(
        callback.message,
        t("mailing_account", locale),
        reply_markup=mailing_accounts_keyboard(accounts, locale, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:default_account:"))
async def mailing_default_account_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        account_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        ok = await service.set_active(callback.from_user.id, account_id, True)
    if not ok:
        await edit_with_history(callback.message, t("account_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    intro = await build_mailing_intro(locale)
    await edit_with_history(
        callback.message,
        intro,
        reply_markup=mailing_intro_keyboard(locale, show_start=True),
    )
    await callback.answer()


@router.callback_query(F.data == "mailing:start")
async def mailing_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await mailing_new_cb(callback, state)


@router.callback_query(F.data == "mailing:settings:message")
async def mailing_settings_message_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_settings_message_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(MailingSettingsStates.message)
    await callback.answer()


@router.message(MailingSettingsStates.message)
async def mailing_settings_message_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    content = await _extract_mailing_content(message)
    message_type, text, media_path, media_file_id, sticker_set_name, sticker_set_index, sticker_pack_missing = content
    if not text and not media_path and not media_file_id:
        await message.answer(t("mailing_settings_message_prompt", locale))
        return
    payload = {
        "message_type": message_type.value,
        "text": text,
        "media_path": media_path,
        "media_file_id": media_file_id,
        "sticker_set_name": sticker_set_name,
        "sticker_set_index": sticker_set_index,
        "sticker_pack_missing": sticker_pack_missing,
    }
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, "mailing_template", json.dumps(payload, ensure_ascii=False))
    await message.answer(t("mailing_settings_message_saved", locale))
    await state.clear()


@router.callback_query(F.data == "mailing:settings:timing")
async def mailing_settings_timing_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(
        callback.message,
        t("mailing_settings_timing_text", locale),
        reply_markup=mailing_timing_keyboard(locale),
    )
    await callback.answer()


@router.callback_query(F.data == "mailing:settings:timing:chats")
async def mailing_settings_timing_chats_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_settings_timing_chats_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(MailingSettingsStates.timing_chats)
    await callback.answer()


@router.callback_query(F.data == "mailing:settings:timing:rounds")
async def mailing_settings_timing_rounds_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("mailing_settings_timing_rounds_prompt", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(MailingSettingsStates.timing_rounds)
    await callback.answer()


@router.message(MailingSettingsStates.timing_chats)
async def mailing_settings_timing_chats_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        value = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await message.answer(t("mailing_settings_timing_invalid", locale))
        return
    if value < 0:
        await message.answer(t("mailing_settings_timing_invalid", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, "mailing_timing_chats", str(value))
    await message.answer(t("mailing_settings_timing_saved", locale).format(value=value))
    await state.clear()


@router.message(MailingSettingsStates.timing_rounds)
async def mailing_settings_timing_rounds_input(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        value = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await message.answer(t("mailing_settings_timing_invalid", locale))
        return
    if value < 0:
        await message.answer(t("mailing_settings_timing_invalid", locale))
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, "mailing_timing_rounds", str(value))
    await message.answer(t("mailing_settings_timing_saved", locale).format(value=value))
    await state.clear()


@router.callback_query(F.data == "mailing:settings:mentions")
async def mailing_settings_mentions_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(
        callback.message,
        t("mailing_settings_mentions_text", locale),
        reply_markup=mailing_mentions_keyboard(locale),
    )
    await callback.answer()


@router.callback_query(F.data == "mailing:settings:mentions:on")
async def mailing_settings_mentions_on_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, "mailing_mentions_enabled", "1")
    await callback.message.answer(t("mailing_settings_mentions_saved_on", locale))
    await callback.answer()


@router.callback_query(F.data == "mailing:settings:mentions:off")
async def mailing_settings_mentions_off_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        await set_setting(session, "mailing_mentions_enabled", "0")
    await callback.message.answer(t("mailing_settings_mentions_saved_off", locale))
    await callback.answer()


@router.callback_query(F.data == "mailing:list")
async def mailing_list_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Mailing).where(Mailing.owner_id == callback.from_user.id))
        mailings = result.scalars().all()
    if not mailings:
        await edit_with_history(callback.message, t("mailing_none", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_choose", locale),
        reply_markup=mailing_list_keyboard(mailings, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:select:"))
async def mailing_select_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Mailing).where(Mailing.owner_id == callback.from_user.id, Mailing.id == mailing_id)
        )
        mailing = result.scalars().first()
    if not mailing:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_actions", locale).format(id=mailing.id),
        reply_markup=mailing_actions_keyboard(mailing.id, mailing.status.value, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:pause:"))
async def mailing_pause_action_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await MailingService(session).pause(callback.from_user.id, mailing_id)
        result = await session.execute(
            select(Mailing).where(Mailing.owner_id == callback.from_user.id, Mailing.id == mailing_id)
        )
        mailing = result.scalars().first()
    if not ok or not mailing:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_actions", locale).format(id=mailing.id),
        reply_markup=mailing_actions_keyboard(mailing.id, mailing.status.value, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:resume:"))
async def mailing_resume_action_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await MailingService(session).resume(callback.from_user.id, mailing_id)
        result = await session.execute(
            select(Mailing).where(Mailing.owner_id == callback.from_user.id, Mailing.id == mailing_id)
        )
        mailing = result.scalars().first()
    if not ok or not mailing:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_actions", locale).format(id=mailing.id),
        reply_markup=mailing_actions_keyboard(mailing.id, mailing.status.value, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:log:"))
async def mailing_log_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Mailing).where(Mailing.owner_id == callback.from_user.id, Mailing.id == mailing_id)
        )
        mailing = result.scalars().first()
    if not mailing:
        await callback.answer(t("mailing_not_found", locale))
        return
    log_path = get_mailing_log_path(mailing_id)
    if not log_path.exists():
        await callback.answer(t("mailing_log_missing", locale), show_alert=True)
        return
    await callback.message.answer_document(
        FSInputFile(str(log_path), filename=f"mailing_{mailing_id}_log.txt"),
        caption=t("mailing_log_caption", locale).format(id=mailing_id),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^mailing:details:\d+$"))
async def mailing_details_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        mailing = await service.get_mailing(callback.from_user.id, mailing_id)
        if not mailing:
            await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
            await callback.answer()
            return
        stats = await service.get_stats(callback.from_user.id, mailing_id)
    source = mailing.target_source.value
    mention = "yes" if mailing.mention else "no"
    try:
        await edit_with_history(callback.message, 
            t("mailing_details", locale).format(
                id=mailing.id,
                status=mailing.status.value,
                source=source,
                message_type=mailing.message_type.value,
                mention=mention,
                delay=mailing.delay_seconds,
                limit=mailing.limit_count,
                total=stats["total"],
                sent=stats["sent"],
                failed=stats["failed"],
                pending=stats["pending"],
            ),
            parse_mode="HTML",
            reply_markup=mailing_details_keyboard(mailing.id, mailing.target_source.value, locale),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:details:recipients:"))
async def mailing_details_recipients_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer()
        return
    try:
        mailing_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        mailing = await service.get_mailing(callback.from_user.id, mailing_id)
        if not mailing:
            await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
            await callback.answer()
            return
        result = await session.execute(
            select(func.count(MailingRecipient.id)).where(MailingRecipient.mailing_id == mailing_id)
        )
        total = int(result.scalar() or 0)
        total_pages = max((total + RECIPIENTS_PAGE_SIZE - 1) // RECIPIENTS_PAGE_SIZE, 1)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * RECIPIENTS_PAGE_SIZE
        result = await session.execute(
            select(MailingRecipient)
            .where(MailingRecipient.mailing_id == mailing_id)
            .order_by(MailingRecipient.id)
            .offset(offset)
            .limit(RECIPIENTS_PAGE_SIZE)
        )
        recipients = result.scalars().all()

        chat_map = {}
        if mailing.target_source == TargetSource.chats and recipients:
            chat_ids = [rec.user_id for rec in recipients]
            result = await session.execute(
                select(ParsedChat).where(
                    ParsedChat.owner_id == callback.from_user.id,
                    ParsedChat.chat_id.in_(chat_ids),
                )
            )
            chats = result.scalars().all()
            chat_map = {chat.chat_id: chat for chat in chats}

    if total == 0:
        text = t("mailing_recipients_empty", locale)
    else:
        header = t("mailing_recipients_title", locale).format(page=page, pages=total_pages, total=total)
        lines = []
        start_index = offset + 1
        for idx, rec in enumerate(recipients):
            label = None
            if mailing.target_source == TargetSource.chats:
                chat = chat_map.get(rec.user_id)
                if chat:
                    label = chat.title or (f"@{chat.username}" if chat.username else None)
            if not label:
                label = f"@{rec.username}" if rec.username else str(rec.user_id)
            lines.append(f"{start_index + idx}. {label}")
        text = f"{header}\n" + "\n".join(lines)

    await edit_with_history(callback.message, 
        text,
        reply_markup=mailing_recipients_keyboard(mailing_id, page, total_pages, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:details:message:"))
async def mailing_details_message_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        mailing = await service.get_mailing(callback.from_user.id, mailing_id)
    if not mailing:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    if not mailing.text and not mailing.media_path:
        await callback.message.answer(t("mailing_message_empty", locale))
        await callback.answer()
        return

    info_text = t("mailing_message_info", locale).format(id=mailing.id, message_type=mailing.message_type.value)

    text = mailing.text or ""
    if text and len(text) <= 3500:
        await callback.message.answer(f"{info_text}\n\n{text}" if info_text else text)
    elif text:
        settings = get_settings()
        os.makedirs(settings.media_dir, exist_ok=True)
        filename = f"mailing_{mailing.id}_message_{uuid4().hex}.txt"
        filepath = os.path.join(settings.media_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as handle:
                handle.write(text)
            if len(info_text) <= 1000:
                await callback.message.answer(info_text)
            await callback.message.answer_document(FSInputFile(filepath))
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        await callback.message.answer(info_text)

    if mailing.media_path and os.path.isfile(mailing.media_path):
        await callback.message.answer_document(FSInputFile(mailing.media_path))
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:repeat:"))
async def mailing_repeat_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        clone = await service.repeat(callback.from_user.id, mailing_id)
    if not clone:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_repeated", locale).format(id=clone.id),
        reply_markup=mailing_actions_keyboard(clone.id, clone.status.value, locale),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mailing:delete:"))
async def mailing_delete_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        mailing_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = MailingService(session)
        ok = await service.delete(callback.from_user.id, mailing_id)
        result = await session.execute(select(Mailing).where(Mailing.owner_id == callback.from_user.id))
        mailings = result.scalars().all()
    if not ok:
        await edit_with_history(callback.message, t("mailing_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    if not mailings:
        await edit_with_history(callback.message, t("mailing_none", locale), reply_markup=back_to_menu_keyboard(locale))
        await callback.answer()
        return
    await edit_with_history(callback.message, 
        t("mailing_choose", locale),
        reply_markup=mailing_list_keyboard(mailings, locale),
    )
    await callback.answer()
