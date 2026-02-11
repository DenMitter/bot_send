from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from app.bot.keyboards import WELCOME_PAGE_COUNT

BASE_DIR = Path(__file__).resolve().parent / "manuals_data"
DEFAULT_LOCALE = "uk"


@dataclass
class ManualSession:
    message_id: int
    is_photo: bool


_manual_sessions: Dict[int, ManualSession] = {}


def _locale_dir(locale: str) -> Path:
    candidate = BASE_DIR / locale
    if candidate.exists():
        return candidate
    return BASE_DIR / DEFAULT_LOCALE


def load_manual_page(locale: str, page: int) -> Tuple[str, List[str]]:
    page = max(1, min(page, WELCOME_PAGE_COUNT))
    manual_dir = _locale_dir(locale)
    page_file = manual_dir / f"page_{page}.md"
    if not page_file.exists():
        raise FileNotFoundError(f"Manual page not found: {page_file}")
    text = page_file.read_text(encoding="utf-8").strip()

    media_file = manual_dir / f"page_{page}.media"
    media_paths: List[str] = []
    if media_file.exists():
        for raw_line in media_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("http://") or line.startswith("https://"):
                media_paths.append(line)
                continue
            candidate = (manual_dir / line).resolve()
            if candidate.exists():
                media_paths.append(str(candidate))
    return text, media_paths


def get_manual_session(chat_id: int) -> Optional[ManualSession]:
    return _manual_sessions.get(chat_id)


def register_manual_session(chat_id: int, message_id: int, is_photo: bool) -> None:
    _manual_sessions[chat_id] = ManualSession(message_id=message_id, is_photo=is_photo)


def clear_manual_session(chat_id: int) -> None:
    _manual_sessions.pop(chat_id, None)


async def clear_manual_media(bot: Bot, chat_id: int) -> None:
    session = get_manual_session(chat_id)
    if not session:
        return
    try:
        await bot.delete_message(chat_id, session.message_id)
    except TelegramBadRequest:
        pass
    clear_manual_session(chat_id)


async def _send_manual_message(
    bot: Bot,
    chat_id: int,
    text: str,
    media_path: Optional[str],
    reply_markup: Optional[InlineKeyboardMarkup],
    parse_mode: Optional[str] = "Markdown",
) -> Tuple[Message, bool]:
    if media_path:
        photo_source = FSInputFile(media_path) if not media_path.startswith("http") else media_path
        sent = await bot.send_photo(chat_id, photo_source, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
        return sent, True
    sent = await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    return sent, False


async def render_manual_message(
    bot: Bot,
    current_message_id: int,
    chat_id: int,
    text: str,
    media_path: Optional[str],
    reply_markup: Optional[InlineKeyboardMarkup],
    parse_mode: Optional[str] = "Markdown",
) -> Message:
    session = get_manual_session(chat_id)
    is_photo = bool(media_path)
    if session and session.message_id == current_message_id:
        try:
            if session.is_photo and is_photo:
                edited = await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=current_message_id,
                    caption=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                register_manual_session(chat_id, current_message_id, True)
                return edited
            if not session.is_photo and not is_photo:
                edited = await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=current_message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                register_manual_session(chat_id, current_message_id, False)
                return edited
        except TelegramBadRequest:
            pass
    else:
        try:
            if is_photo:
                edited = await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=current_message_id,
                    caption=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                register_manual_session(chat_id, current_message_id, True)
                return edited
            edited = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=current_message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            register_manual_session(chat_id, current_message_id, False)
            return edited
        except TelegramBadRequest:
            pass

    try:
        await bot.delete_message(chat_id, current_message_id)
    except TelegramBadRequest:
        pass

    message, sent_is_photo = await _send_manual_message(bot, chat_id, text, media_path, reply_markup, parse_mode)
    register_manual_session(chat_id, message.message_id, sent_is_photo)
    return message
