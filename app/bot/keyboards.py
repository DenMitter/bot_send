from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from typing import Dict

from app.i18n.translator import t


WELCOME_PAGE_COUNT = 10

BUTTON_ICONS: Dict[str, str] = {
    "btn_welcome_mailing": "🚀",
    "btn_welcome_parsing": "🧠",
    "btn_parsed_users_db": "🗂️",
    "btn_welcome_profile": "👤",
    "btn_welcome_accounts": "💼",
    "btn_welcome_manuals": "📘",
    "btn_welcome_tasks": "📝",
    "btn_welcome_franchise": "🤝",
}


def _button_label(key: str, locale: str) -> str:
    icon = BUTTON_ICONS.get(key)
    label = t(key, locale)
    return f"{icon} {label}" if icon else label


def _account_status_icon(is_active: bool) -> str:
    return "🟢" if is_active else "⚠️"


def back_button(locale: str, callback_data: str = "back:prev") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t("btn_back", locale), callback_data=callback_data)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Українська", callback_data="lang:uk"),
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
            ],
        ]
    )


def welcome_keyboard(locale: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=_button_label("btn_welcome_mailing", locale))],
            [KeyboardButton(text=_button_label("btn_welcome_parsing", locale))],
            [KeyboardButton(text=_button_label("btn_parsed_users_db", locale))],
            [KeyboardButton(text=_button_label("btn_welcome_tasks", locale))],
            [KeyboardButton(text=_button_label("btn_welcome_manuals", locale))],
            [
                KeyboardButton(text=_button_label("btn_welcome_profile", locale)),
                KeyboardButton(text=_button_label("btn_welcome_accounts", locale)),
            ],
            # [
            #     KeyboardButton(text=f"?? {t('btn_welcome_tasks', locale)}"),
            #     KeyboardButton(text=f"?? {t('btn_welcome_franchise', locale)}"),
            # ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def welcome_entry_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_button_label("btn_welcome_manuals", locale), callback_data="welcome:manual"),
            ]
        ]
    )


def manual_inline_keyboard(locale: str, page: int) -> InlineKeyboardMarkup:
    page = max(1, min(page, WELCOME_PAGE_COUNT))
    nav_row = [InlineKeyboardButton(text=f"{page}/{WELCOME_PAGE_COUNT}", callback_data="welcome:page:info")]
    if page > 1:
        nav_row.insert(0, InlineKeyboardButton(text=t("btn_welcome_page_prev", locale), callback_data="welcome:page:prev"))
    if page < WELCOME_PAGE_COUNT:
        nav_row.append(InlineKeyboardButton(text=t("btn_welcome_page_next", locale), callback_data="welcome:page:next"))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav_row,
            [
                InlineKeyboardButton(text=t("btn_welcome_start_work", locale), callback_data="welcome:action:start"),
                InlineKeyboardButton(text=t("btn_welcome_support", locale), callback_data="welcome:action:support"),
            ],
        ]
    )


def admin_menu_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_mailing_list", locale), callback_data="mailing:list"),
                InlineKeyboardButton(text=t("btn_account_list", locale), callback_data="account:list"),
            ],
            [
                InlineKeyboardButton(text=t("btn_parse", locale), callback_data="parse:start"),
                InlineKeyboardButton(text=t("btn_parse_chats", locale), callback_data="parse:chats"),
            ],
        ]
    )


def account_auth_method_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_auth_phone", locale), callback_data="auth:phone"),
                InlineKeyboardButton(text=t("btn_auth_qr", locale), callback_data="auth:qr"),
            ],
            [InlineKeyboardButton(text=t("btn_auth_web", locale), callback_data="auth:web")],
            [back_button(locale)],
        ]
    )


def account_qr_confirm_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_auth_qr_done", locale), callback_data="auth:qr_done")],
            [back_button(locale)],
        ]
    )


def account_web_confirm_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_auth_web_check", locale), callback_data="auth:web_check")],
            [back_button(locale)],
        ]
    )


def mailing_source_keyboard(locale: str, is_admin_user: bool) -> InlineKeyboardMarkup:
    row = []
    if is_admin_user:
        row.append(InlineKeyboardButton(text=t("btn_source_subscribers", locale), callback_data="mailing:source:subscribers"))
    row.extend(
        [
            InlineKeyboardButton(text=t("btn_source_parsed", locale), callback_data="mailing:source:parsed"),
            InlineKeyboardButton(text=t("btn_source_chats", locale), callback_data="mailing:source:chats"),
        ]
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [back_button(locale, "mailing:back:account")],
        ]
    )


def mailing_mention_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_mention_yes", locale), callback_data="mailing:mention:yes"),
                InlineKeyboardButton(text=t("btn_mention_no", locale), callback_data="mailing:mention:no"),
            ],
            [back_button(locale, "mailing:back:source")],
        ]
    )


def account_select_keyboard(accounts, locale: str) -> InlineKeyboardMarkup:
    rows = []
    for acc in accounts:
        status = _account_status_icon(acc.is_active)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {acc.id}: {acc.phone}",
                    callback_data=f"mailing:account:{acc.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=t("btn_use_active", locale), callback_data="mailing:account:active")])
    rows.append([back_button(locale, "mailing:back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_account_keyboard(accounts, locale: str, mode: str) -> InlineKeyboardMarkup:
    rows = []
    for acc in accounts:
        status = _account_status_icon(acc.is_active)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {acc.id}: {acc.phone}",
                    callback_data=f"parse:{mode}:account:{acc.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("btn_use_active", locale),
                callback_data=f"parse:{mode}:account:active",
            )
        ]
    )
    rows.append([back_button(locale)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chats_scope_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_chats_all", locale), callback_data="mailing:chats:all"),
                InlineKeyboardButton(text=t("btn_chats_select", locale), callback_data="mailing:chats:select"),
            ],
            [back_button(locale, "mailing:back:source")],
        ]
    )


def chats_select_keyboard(chats, selected_ids, locale: str) -> InlineKeyboardMarkup:
    rows = []
    for chat in chats:
        label = chat.title or chat.username or str(chat.chat_id)
        checked = "✅ " if chat.chat_id in selected_ids else ""
        rows.append([InlineKeyboardButton(text=f"{checked}{label}", callback_data=f"mailing:chat:{chat.chat_id}")])
    rows.append(
        [
            InlineKeyboardButton(text=t("btn_done", locale), callback_data="mailing:chats:done"),
            back_button(locale, "mailing:chats:back"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[back_button(locale)]]
    )


def step_back_keyboard(locale: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[back_button(locale, callback_data)]]
    )


def account_list_keyboard(accounts, locale: str, page: int = 1, page_size: int = 5) -> InlineKeyboardMarkup:
    total = len(accounts)
    start = max(0, (page - 1) * page_size)
    end = min(total, start + page_size)
    page_accounts = accounts[start:end]

    rows = []
    for acc in page_accounts:
        status = _account_status_icon(acc.is_active)
        rows.append(
            [InlineKeyboardButton(text=f"{status} {acc.id}: {acc.phone}", callback_data=f"account:select:{acc.id}")]
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text=t("btn_prev", locale), callback_data=f"account:list:page:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text=t("btn_next", locale), callback_data=f"account:list:page:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("btn_account_add", locale), callback_data="account:add")])
    rows.append([back_button(locale)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def account_actions_keyboard(account_id: int, is_active: bool, locale: str) -> InlineKeyboardMarkup:
    rows = []
    if is_active:
        rows.append([InlineKeyboardButton(text=t("btn_account_deactivate", locale), callback_data=f"account:deact:{account_id}")])
    else:
        rows.append([InlineKeyboardButton(text=t("btn_account_activate", locale), callback_data=f"account:act:{account_id}")])
    rows.append([back_button(locale, "account:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mailing_list_keyboard(mailings, locale: str, back_callback: str = "back:prev") -> InlineKeyboardMarkup:
    rows = []
    for mailing in mailings:
        status = mailing.status.value
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{mailing.id} • {status}",
                    callback_data=f"mailing:select:{mailing.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=t("btn_mailing_new", locale), callback_data="mailing:new")])
    rows.append([back_button(locale, back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mailing_actions_keyboard(mailing_id: int, status: str, locale: str) -> InlineKeyboardMarkup:
    rows = []
    rows.append([InlineKeyboardButton(text=t("btn_mailing_details", locale), callback_data=f"mailing:details:{mailing_id}")])
    rows.append([InlineKeyboardButton(text=t("btn_mailing_edit", locale), callback_data=f"mailing:edit:{mailing_id}")])
    if status == "running":
        rows.append([InlineKeyboardButton(text=t("btn_mailing_pause", locale), callback_data=f"mailing:pause:{mailing_id}")])
    if status in ("paused", "failed"):
        rows.append([InlineKeyboardButton(text=t("btn_mailing_resume", locale), callback_data=f"mailing:resume:{mailing_id}")])
    rows.append([InlineKeyboardButton(text=t("btn_mailing_repeat", locale), callback_data=f"mailing:repeat:{mailing_id}")])
    rows.append([InlineKeyboardButton(text=t("btn_mailing_delete", locale), callback_data=f"mailing:delete:{mailing_id}")])
    rows.append([back_button(locale, "mailing:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mailing_details_keyboard(mailing_id: int, target_source: str, locale: str) -> InlineKeyboardMarkup:
    rows = []
    recipients_label = (
        t("btn_mailing_chat_list", locale)
        if target_source == "chats"
        else t("btn_mailing_recipient_list", locale)
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=recipients_label,
                callback_data=f"mailing:details:recipients:{mailing_id}:1",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text=t("btn_mailing_show_message", locale), callback_data=f"mailing:details:message:{mailing_id}")]
    )
    rows.append(
        [InlineKeyboardButton(text=t("btn_mailing_log", locale), callback_data=f"mailing:log:{mailing_id}")]
    )
    rows.append([back_button(locale, f"mailing:select:{mailing_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mailing_recipients_keyboard(mailing_id: int, page: int, total_pages: int, locale: str) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_prev", locale),
                callback_data=f"mailing:details:recipients:{mailing_id}:{page - 1}",
            )
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton(
                text=t("btn_next", locale),
                callback_data=f"mailing:details:recipients:{mailing_id}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)
    rows.append([back_button(locale, f"mailing:details:{mailing_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
