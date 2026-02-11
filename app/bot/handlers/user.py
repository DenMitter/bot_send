from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from typing import Optional, Sequence, Set
from datetime import datetime
from pathlib import Path

from app.bot.history import (
    clear_history,
    edit_with_history,
    get_last_message,
    get_welcome_page,
    capture_previous_message,
    pop_state,
    register_message,
    set_welcome_page,
    set_menu_photo,
    get_menu_photo,
)
from app.db.models import BotSubscriber, Mailing, BalanceTransaction, ReferralReward
from app.db.session import get_session_factory
from app.i18n.translator import t
from app.bot.handlers.common import is_admin, normalize_locale, resolve_locale, build_mailing_intro
from app.services.auth import AccountService
from app.services.billing import BillingService
from app.services.settings import get_setting, SUPPORT_CONTACT_KEY
from app.bot.keyboards import (
    BUTTON_ICONS,
    add_account_keyboard,
    language_keyboard,
    manual_inline_keyboard,
    mailing_intro_keyboard,
    parsing_intro_keyboard,
    parse_mode_keyboard,
    admin_panel_keyboard,
    profile_keyboard,
    support_keyboard,
    referral_keyboard,
    welcome_entry_keyboard,
    welcome_keyboard,
    WELCOME_PAGE_COUNT,
    mailing_list_keyboard,
)
from app.bot.handlers.admin import ParseStates, _parse_chat_for_user, send_parsed_users_file
from app.bot.handlers.accounts import account_list
from app.bot.manuals import clear_manual_media, load_manual_page, render_manual_message


router = Router()
WELCOME_MENU_PHOTO = Path(__file__).resolve().parent.parent / "assets" / "welcome_menu.jpg"


def _first_media_path(media_paths: Optional[Sequence[str]]) -> Optional[str]:
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
    menu_photo_id = get_menu_photo(message.chat.id)
    if menu_photo_id:
        try:
            await message.bot.delete_message(message.chat.id, menu_photo_id)
        except TelegramBadRequest:
            pass
        set_menu_photo(message.chat.id, None)
    if WELCOME_MENU_PHOTO.exists():
        sent_photo = await message.answer_photo(
            FSInputFile(str(WELCOME_MENU_PHOTO)),
            reply_markup=welcome_keyboard(locale, is_admin(message)),
        )
        set_menu_photo(message.chat.id, sent_photo.message_id)
    else:
        await message.answer(t("menu", locale), reply_markup=welcome_keyboard(locale, is_admin(message)))
    sent = await message.answer(caption, reply_markup=welcome_entry_keyboard(locale))
    register_message(sent)


def _button_texts(key: str) -> Set[str]:
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
    last_snapshot = get_last_message(message.chat.id)
    target_message_id = message.message_id
    if message.from_user and not message.from_user.is_bot and last_snapshot:
        target_message_id = last_snapshot.message_id
        capture_previous_message(message.chat.id)
    elif last_snapshot and last_snapshot.message_id == target_message_id:
        capture_previous_message(message.chat.id)
    edited = await render_manual_message(
        bot=message.bot,
        current_message_id=target_message_id,
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
    referrer_id = None
    if message.text and " " in message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].isdigit():
            referrer_id = int(parts[1])
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
        if (
            referrer_id
            and referrer_id != message.from_user.id
            and subscriber.referrer_id is None
        ):
            subscriber.referrer_id = referrer_id
            subscriber.referred_at = datetime.utcnow()
            await session.commit()

    if not subscriber.language:
        await message.answer(t("choose_language", locale), reply_markup=language_keyboard())
        return

    clear_history(message.chat.id)
    await _send_welcome_menu(message, normalize_locale(subscriber.language))

@router.message(Command("manuals"))
async def manuals_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await _show_manual_page(message, locale, 1)


@router.message(Command("tasks"))
async def tasks_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("tasks_info", locale))


@router.message(Command("franchise"))
async def franchise_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("franchise_info", locale))


@router.message(Command("balance"))
async def balance_handler(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        balance = await billing.get_balance(message.from_user.id)
        txs = await billing.list_transactions(message.from_user.id, limit=10)
    lines = [t("balance_info", locale).format(balance=balance)]
    if txs:
        lines.append(t("balance_history_title", locale))
        for tx in txs:
            reason = tx.reason or "-"
            lines.append(t("balance_history_line", locale).format(
                amount=tx.amount,
                tx_type=tx.tx_type,
                reason=reason,
                created_at=tx.created_at.strftime("%Y-%m-%d %H:%M"),
            ))
    else:
        lines.append(t("balance_history_empty", locale))
    await message.answer("\n".join(lines))


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
    await _send_welcome_menu(callback.message, locale)
    await callback.answer()


@router.callback_query(F.data == "welcome:action:support")
async def welcome_support(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await _send_support_message(callback.message, locale)
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
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await state.clear()
    intro = await build_mailing_intro(locale)
    sent = await message.answer(intro, reply_markup=mailing_intro_keyboard(locale, show_start=True))
    register_message(sent)


@router.message(lambda message: _matches_button("btn_welcome_parsing", message.text))
async def welcome_parsing(message: Message, state: FSMContext) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await state.clear()
    sent = await message.answer(t("parsing_intro", locale), reply_markup=parsing_intro_keyboard(locale))
    register_message(sent)


@router.message(lambda message: _matches_button("btn_parsed_users_db", message.text))
async def welcome_parsed_users(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await send_parsed_users_file(message, locale)


@router.message(lambda message: _matches_button("btn_welcome_profile", message.text))
async def welcome_profile(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        balance = await billing.get_balance(message.from_user.id)
    profile_text = t("profile_text", locale).format(
        user_id=message.from_user.id,
        balance=f"{balance:.3f}",
        status=t("profile_status_basic", locale),
        updated=t("profile_last_update_now", locale),
    )
    await message.answer(profile_text, reply_markup=profile_keyboard(locale))


@router.callback_query(F.data == "profile:history")
async def profile_history(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        billing = BillingService(session)
        txs = await billing.list_transactions(callback.from_user.id, limit=10)
    if not txs:
        await callback.message.answer(t("balance_history_empty", locale))
        await callback.answer()
        return
    lines = [t("balance_history_title", locale)]
    for tx in txs:
        reason = tx.reason or "-"
        lines.append(
            t("balance_history_line", locale).format(
                amount=tx.amount,
                tx_type=tx.tx_type,
                reason=reason,
                created_at=tx.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        )
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "profile:topup")
async def profile_topup(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("profile_topup_info", locale))
    await callback.answer()


@router.callback_query(F.data == "profile:promo")
async def profile_promo(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("profile_promo_info", locale))
    await callback.answer()


@router.callback_query(F.data == "profile:ref")
async def profile_ref(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        bot_info = await callback.bot.get_me()
        bot_username = getattr(bot_info, "username", None)
        ref_link = ""
        if bot_username:
            ref_link = f"https://t.me/{bot_username}?start={callback.from_user.id}"

        referral_count_result = await session.execute(
            select(BotSubscriber).where(BotSubscriber.referrer_id == callback.from_user.id)
        )
        referrals = referral_count_result.scalars().all()
        referral_ids = [ref.user_id for ref in referrals]

        total_topups = 0.0
        if referral_ids:
            tx_result = await session.execute(
                select(BalanceTransaction)
                .where(
                    BalanceTransaction.user_id.in_(referral_ids),
                    BalanceTransaction.tx_type == "topup",
                    BalanceTransaction.amount > 0,
                )
            )
            total_topups = sum(tx.amount for tx in tx_result.scalars().all())

        reward_result = await session.execute(
            select(ReferralReward).where(ReferralReward.referrer_id == callback.from_user.id)
        )
        rewards = reward_result.scalars().all()
        total_reward = sum(r.amount for r in rewards)

    percent = 20
    available = total_reward
    text = t("referral_text", locale).format(
        link=ref_link or t("referral_link_unavailable", locale),
        percent=percent,
        count=len(referrals),
        total_topups=f"{total_topups:.2f}",
        total_reward=f"{total_reward:.2f}",
        available=f"{available:.2f}",
    )
    await callback.message.answer(text, reply_markup=referral_keyboard(locale, ref_link))
    await callback.answer()


@router.callback_query(F.data == "referral:balance")
async def referral_balance(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        reward_result = await session.execute(
            select(ReferralReward).where(ReferralReward.referrer_id == callback.from_user.id)
        )
        rewards = reward_result.scalars().all()
        total_reward = sum(r.amount for r in rewards)
    await callback.message.answer(t("referral_balance_info", locale).format(amount=f"{total_reward:.2f}"))
    await callback.answer()


@router.callback_query(F.data == "profile:pro")
async def profile_pro(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("profile_pro_info", locale))
    await callback.answer()


@router.callback_query(F.data == "profile:settings")
async def profile_settings(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("profile_settings_info", locale))
    await callback.answer()


@router.callback_query(F.data == "profile:support")
async def profile_support(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await _send_support_message(callback.message, locale)
    await callback.answer()


def _normalize_support_contact(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    if value.startswith("t.me/"):
        return f"https://{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://t.me/{value}"


async def _send_support_message(message: Message, locale: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        raw = await get_setting(session, SUPPORT_CONTACT_KEY)
    url = _normalize_support_contact(raw or "")
    if not url:
        await message.answer(t("support_no_contact", locale))
        return
    capture_previous_message(message.chat.id)
    link = f'<a href="{url}">{t("support_link_text", locale)}</a>'
    text = t("support_text", locale).format(link=link)
    sent = await message.answer(text, reply_markup=support_keyboard(locale, url), parse_mode="HTML")
    register_message(sent)


@router.callback_query(F.data == "profile:tariffs")
async def profile_tariffs(callback: CallbackQuery) -> None:
    locale = await resolve_locale(callback.from_user.id, callback.from_user.language_code)
    await callback.message.answer(t("profile_tariffs_info", locale))
    await callback.answer()




@router.message(lambda message: _matches_button("btn_welcome_accounts", message.text))
async def welcome_accounts(message: Message) -> None:
    await account_list(message)


@router.message(lambda message: _matches_button("btn_admin", message.text))
async def welcome_admin_panel(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    if not is_admin(message):
        await message.answer(t("admin_only", locale))
        return
    await message.answer(t("admin_panel_title", locale), reply_markup=admin_panel_keyboard(locale))


@router.message(lambda message: _matches_button("btn_welcome_manuals", message.text))
async def welcome_manuals(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await _show_manual_page(message, locale, 1)


@router.message(lambda message: _matches_button("btn_welcome_tasks", message.text))
async def welcome_tasks(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Mailing).where(Mailing.owner_id == message.from_user.id))
        mailings = result.scalars().all()
    if not mailings:
        await message.answer(t("tasks_empty", locale))
        return
    await message.answer(
        t("mailing_choose", locale),
        reply_markup=mailing_list_keyboard(mailings, locale, back_callback="mailing:back:menu"),
    )


@router.message(lambda message: _matches_button("btn_welcome_franchise", message.text))
async def welcome_franchise(message: Message) -> None:
    locale = await resolve_locale(message.from_user.id, message.from_user.language_code)
    await message.answer(t("franchise_info", locale))


@router.message(StateFilter(None), lambda message: _looks_like_chat(message.text))
async def parse_link_message(message: Message) -> None:
    chat = (message.text or "").strip()
    if not chat:
        return
    await _parse_chat_for_user(message, chat)
