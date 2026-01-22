from io import BytesIO

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
import qrcode
from telethon.errors.rpcerrorlist import (
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    PhoneNumberUnoccupiedError,
)
from telethon.utils import parse_phone

from app.bot.history import edit_with_history
from app.bot.handlers.common import is_admin, resolve_locale
from app.bot.keyboards import (
    account_actions_keyboard,
    account_auth_method_keyboard,
    account_list_keyboard,
    account_qr_confirm_keyboard,
    account_web_confirm_keyboard,
    back_to_menu_keyboard,
    admin_menu_keyboard,
)
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.services.auth import AccountService
from app.services.auth_registry import auth_flow_manager


async def _reply_with_history(message: Message, text: str, reply_markup=None) -> Message:
    try:
        return await edit_with_history(message, text, reply_markup=reply_markup)
    except TelegramBadRequest:
        return await message.answer(text, reply_markup=reply_markup)


async def _safe_callback_answer(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass


router = Router()


class AccountStates(StatesGroup):
    method = State()
    phone = State()
    code = State()
    password = State()
    id_action = State()
    qr_wait = State()
    web_wait = State()


def _sent_code_method_name(code_type: object, locale: str) -> str:
    if not code_type:
        return t("account_code_method_unknown", locale)
    name = type(code_type).__name__
    mapping = {
        "SentCodeTypeApp": "account_code_method_app",
        "SentCodeTypeSms": "account_code_method_sms",
        "SentCodeTypeCall": "account_code_method_call",
        "SentCodeTypeFlashCall": "account_code_method_flash_call",
        "SentCodeTypeMissedCall": "account_code_method_missed_call",
        "SentCodeTypeEmailCode": "account_code_method_email",
    }
    return t(mapping.get(name, "account_code_method_unknown"), locale)


@router.message(Command("account_add"))
async def account_add(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await state.clear()
    await message.answer(t("account_method", locale), reply_markup=account_auth_method_keyboard(locale))
    await state.set_state(AccountStates.method)


@router.callback_query(F.data == "account:add")
async def account_add_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await state.clear()
    await edit_with_history(callback.message, t("account_method", locale), reply_markup=account_auth_method_keyboard(locale))
    await state.set_state(AccountStates.method)
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "auth:phone")
async def account_method_phone(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await state.update_data(auth_method="code")
    await edit_with_history(callback.message, t("account_phone", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(AccountStates.phone)
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "auth:web")
async def account_method_web(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await state.update_data(auth_method="web")
    await edit_with_history(callback.message, t("account_phone", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(AccountStates.phone)
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "auth:qr")
async def account_method_qr(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        qr_url = await auth_flow_manager.start_qr(callback.from_user.id)
    except Exception:
        await edit_with_history(callback.message, t("account_failed", locale))
        await state.clear()
        await _safe_callback_answer(callback)
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await edit_with_history(callback.message, t("account_qr_hint", locale))
    await callback.message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename="qr.png"),
        reply_markup=account_qr_confirm_keyboard(locale),
    )
    await state.set_state(AccountStates.qr_wait)
    await _safe_callback_answer(callback)


@router.message(AccountStates.phone)
async def account_phone(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    raw_phone = (message.text or "").strip()
    parsed_phone = parse_phone(raw_phone)
    if not parsed_phone:
        await message.answer(t("account_phone_invalid", locale))
        return
    phone = f"+{parsed_phone}"
    data = await state.get_data()
    method = data.get("auth_method") or "code"
    try:
        if method == "web":
            token = await auth_flow_manager.start_web(message.from_user.id, phone)
        else:
            await auth_flow_manager.start(message.from_user.id, phone)
            token = None
    except PhoneNumberInvalidError:
        await message.answer(t("account_phone_invalid", locale))
        await state.clear()
        return
    except PhoneNumberBannedError:
        await message.answer(t("account_phone_banned", locale))
        await state.clear()
        return
    except PhoneNumberFloodError:
        await message.answer(t("account_phone_flood", locale))
        await state.clear()
        return
    except PhoneNumberUnoccupiedError:
        await message.answer(t("account_phone_unoccupied", locale))
        await state.clear()
        return
    except Exception:
        await message.answer(t("account_failed", locale))
        await state.clear()
        return
    await state.update_data(phone=phone)
    code_type, next_code_type, timeout = auth_flow_manager.get_delivery_info(message.from_user.id)
    if code_type:
        method_name = _sent_code_method_name(code_type, locale)
        await message.answer(t("account_code_delivery", locale).format(method=method_name))
        if next_code_type and timeout:
            next_name = _sent_code_method_name(next_code_type, locale)
            await message.answer(
                t("account_code_delivery_next", locale).format(method=next_name, timeout=timeout)
            )
    if method == "web":
        settings = get_settings()
        link = f"{settings.web_auth_base_url}/auth/{token}"
        await message.answer(f"{t('account_web_hint', locale)}\n{link}", reply_markup=account_web_confirm_keyboard(locale))
        await message.answer(t("account_web_wait", locale))
        await state.set_state(AccountStates.web_wait)
        return
    await message.answer(t("account_code", locale), reply_markup=back_to_menu_keyboard(locale))
    await state.set_state(AccountStates.code)


@router.message(AccountStates.code)
async def account_code(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    code = (message.text or "").strip()
    result = await auth_flow_manager.submit_code(message.from_user.id, code)
    if result == "PASSWORD_REQUIRED":
        await message.answer(t("account_password", locale), reply_markup=back_to_menu_keyboard(locale))
        await state.set_state(AccountStates.password)
        return
    if not result:
        await message.answer(t("account_failed", locale))
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        existing = await service.get_by_phone(phone)
        if existing and existing.owner_id != message.from_user.id:
            await message.answer(t("account_taken", locale))
            await state.clear()
            return
        if existing:
            existing.session_string = result
            await session.commit()
        else:
            await service.add_account(message.from_user.id, phone, result)
    await message.answer(t("account_added", locale))
    await state.clear()


@router.message(AccountStates.password)
async def account_password(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    password = (message.text or "").strip()
    result = await auth_flow_manager.submit_password(message.from_user.id, password)
    if not result:
        await message.answer(t("account_failed", locale))
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        existing = await service.get_by_phone(phone)
        if existing and existing.owner_id != message.from_user.id:
            await message.answer(t("account_taken", locale))
            await state.clear()
            return
        if existing:
            existing.session_string = result
            await session.commit()
        else:
            await service.add_account(message.from_user.id, phone, result)
    await message.answer(t("account_added", locale))
    await state.clear()


@router.callback_query(F.data == "auth:qr_done")
async def account_qr_wait(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_string, phone = await auth_flow_manager.confirm_qr(callback.from_user.id)
    if not session_string or not phone:
        await _reply_with_history(callback.message, t("account_failed", locale))
        await state.clear()
        await _safe_callback_answer(callback)
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        existing = await service.get_by_phone(phone)
        if existing and existing.owner_id != callback.from_user.id:
            await _reply_with_history(callback.message, t("account_taken", locale))
            await state.clear()
            await _safe_callback_answer(callback)
            return
        if existing:
            existing.session_string = session_string
            await session.commit()
        else:
            await service.add_account(callback.from_user.id, phone, session_string)
    await _reply_with_history(callback.message, t("account_added", locale))
    await state.clear()
    try:
        await _safe_callback_answer(callback)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "auth:web_check")
async def account_web_wait(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_string, phone, status = await auth_flow_manager.confirm_web(callback.from_user.id)
    if status == "WAIT_CODE":
        await edit_with_history(callback.message, t("account_web_wait", locale))
        await _safe_callback_answer(callback)
        return
    if status == "NEED_PASSWORD":
        await edit_with_history(callback.message, t("account_web_need_password", locale))
        await _safe_callback_answer(callback)
        return
    if status != "DONE":
        await edit_with_history(callback.message, t("account_failed", locale))
        await state.clear()
        await _safe_callback_answer(callback)
        return
    if not session_string or not phone:
        await edit_with_history(callback.message, t("account_failed", locale))
        await state.clear()
        await _safe_callback_answer(callback)
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        existing = await service.get_by_phone(phone)
        if existing and existing.owner_id != callback.from_user.id:
            await edit_with_history(callback.message, t("account_taken", locale))
            await state.clear()
            await _safe_callback_answer(callback)
            return
        if existing:
            existing.session_string = session_string
            await session.commit()
        else:
            await service.add_account(callback.from_user.id, phone, session_string)
    await edit_with_history(callback.message, t("account_web_ok", locale))
    await state.clear()
    await _safe_callback_answer(callback)


@router.message(Command("account_list"))
async def account_list(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(message.from_user.id)

    if not accounts:
        await message.answer(t("account_none", locale))
        return

    await message.answer(
        t("account_choose", locale),
        reply_markup=account_list_keyboard(accounts, locale, page=1),
    )


@router.callback_query(F.data.startswith("account:list"))
async def account_list_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(callback.from_user.id)

    if not accounts:
        await edit_with_history(callback.message, t("account_none", locale), reply_markup=back_to_menu_keyboard(locale))
        await _safe_callback_answer(callback)
        return

    data = callback.data.split(":")
    page = 1
    if len(data) >= 4 and data[2] == "page":
        try:
            page = max(1, int(data[3]))
        except ValueError:
            pass
    await edit_with_history(callback.message, 
        t("account_choose", locale),
        reply_markup=account_list_keyboard(accounts, locale, page=page),
    )
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("account:select:"))
async def account_select_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        account_id = int(callback.data.split(":")[-1])
    except ValueError:
        await _safe_callback_answer(callback)
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
        account = next((acc for acc in accounts if acc.id == account_id), None)
    if not account:
        await edit_with_history(callback.message, t("account_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await _safe_callback_answer(callback)
        return
    if not account.is_active:
        await state.clear()
        await state.set_state(AccountStates.method)
        await edit_with_history(
            callback.message,
            t("account_not_bound", locale).format(phone=account.phone),
            reply_markup=account_auth_method_keyboard(locale),
        )
        await _safe_callback_answer(callback)
        return
    await edit_with_history(callback.message, 
        t("account_actions", locale).format(phone=account.phone),
        reply_markup=account_actions_keyboard(account.id, account.is_active, locale),
    )
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("account:act:"))
async def account_activate_action_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        account_id = int(callback.data.split(":")[-1])
    except ValueError:
        await _safe_callback_answer(callback)
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await AccountService(session).set_active(callback.from_user.id, account_id, True)
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
        account = next((acc for acc in accounts if acc.id == account_id), None)
    if not ok or not account:
        await edit_with_history(callback.message, t("account_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await _safe_callback_answer(callback)
        return
    await edit_with_history(callback.message, 
        t("account_actions", locale).format(phone=account.phone),
        reply_markup=account_actions_keyboard(account.id, account.is_active, locale),
    )
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("account:deact:"))
async def account_deactivate_action_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    try:
        account_id = int(callback.data.split(":")[-1])
    except ValueError:
        await _safe_callback_answer(callback)
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await AccountService(session).set_active(callback.from_user.id, account_id, False)
        accounts = await AccountService(session).list_accounts(callback.from_user.id)
        account = next((acc for acc in accounts if acc.id == account_id), None)
    if not ok or not account:
        await edit_with_history(callback.message, t("account_not_found", locale), reply_markup=back_to_menu_keyboard(locale))
        await _safe_callback_answer(callback)
        return
    await edit_with_history(callback.message, 
        t("account_actions", locale).format(phone=account.phone),
        reply_markup=account_actions_keyboard(account.id, account.is_active, locale),
    )
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "account:activate")
async def account_activate_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("enter_id", locale))
    await state.set_state(AccountStates.id_action)
    await state.update_data(action="activate")
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "account:deactivate")
async def account_deactivate_cb(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await edit_with_history(callback.message, t("enter_id", locale))
    await state.set_state(AccountStates.id_action)
    await state.update_data(action="deactivate")
    await _safe_callback_answer(callback)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_cb(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    if is_admin(callback.message):
        await edit_with_history(callback.message, t("menu", locale), reply_markup=admin_menu_keyboard(locale))
    await _safe_callback_answer(callback)


@router.message(AccountStates.id_action)
async def account_id_action(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    try:
        account_id = int((message.text or "").strip())
    except ValueError:
        await message.answer(t("enter_id", locale))
        return
    data = await state.get_data()
    action = data.get("action")
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = AccountService(session)
        if action == "activate":
            ok = await service.set_active(message.from_user.id, account_id, True)
            await message.answer(t("account_activated", locale) if ok else t("account_not_found", locale))
        elif action == "deactivate":
            ok = await service.set_active(message.from_user.id, account_id, False)
            await message.answer(t("account_deactivated", locale) if ok else t("account_not_found", locale))
    await state.clear()


@router.message(Command("account_activate"))
async def account_activate(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    account_id = int(parts[1].strip())
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await AccountService(session).set_active(message.from_user.id, account_id, True)
    await message.answer(t("account_activated", locale) if ok else t("account_not_found", locale))


@router.message(Command("account_deactivate"))
async def account_deactivate(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    account_id = int(parts[1].strip())
    session_factory = get_session_factory()
    async with session_factory() as session:
        ok = await AccountService(session).set_active(message.from_user.id, account_id, False)
    await message.answer(t("account_deactivated", locale) if ok else t("account_not_found", locale))
