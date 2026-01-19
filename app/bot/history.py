from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from aiogram.types import InlineKeyboardMarkup, Message

STACK_LIMIT = 25


@dataclass
class MessageSnapshot:
    message_id: int
    text: str
    reply_markup: InlineKeyboardMarkup | None
    options: Dict[str, Any]
    media_paths: List[str] = field(default_factory=list)


_history: Dict[int, List[MessageSnapshot]] = defaultdict(list)
_last_message: Dict[int, MessageSnapshot] = {}
_welcome_pages: Dict[int, int] = {}


def _extract_text(message: Message) -> str:
    return message.text or message.caption or ""


def _push_snapshot(chat_id: int, snapshot: MessageSnapshot) -> None:
    stack = _history.setdefault(chat_id, [])
    stack.append(snapshot)
    if len(stack) > STACK_LIMIT:
        stack.pop(0)


def push_state(
    message: Message,
    options: Dict[str, Any],
    media_paths: Sequence[str] | None = None,
) -> None:
    _push_snapshot(
        message.chat.id,
        MessageSnapshot(
            message_id=message.message_id,
            text=_extract_text(message),
            reply_markup=message.reply_markup,
            options=dict(options),
            media_paths=list(media_paths) if media_paths else [],
        ),
    )


def capture_previous_message(chat_id: int) -> None:
    snapshot = _last_message.get(chat_id)
    if not snapshot:
        return
    _push_snapshot(chat_id, snapshot)


def register_message(
    message: Message,
    options: Dict[str, Any] | None = None,
    media_paths: Sequence[str] | None = None,
) -> None:
    _last_message[message.chat.id] = MessageSnapshot(
        message_id=message.message_id,
        text=_extract_text(message),
        reply_markup=message.reply_markup,
        options=dict(options) if options else {},
        media_paths=list(media_paths) if media_paths else [],
    )


def pop_state(chat_id: int) -> MessageSnapshot | None:
    stack = _history.get(chat_id)
    if not stack:
        return None
    return stack.pop()


def clear_history(chat_id: int) -> None:
    _history.pop(chat_id, None)
    _last_message.pop(chat_id, None)
    _welcome_pages.pop(chat_id, None)


def set_welcome_page(chat_id: int, page: int) -> None:
    _welcome_pages[chat_id] = max(1, page)


def get_welcome_page(chat_id: int) -> int:
    return _welcome_pages.get(chat_id, 1)


async def edit_with_history(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    media_paths: Sequence[str] | None = None,
    **options: Any,
) -> Message:
    push_state(message, options, media_paths)
    edited = await message.edit_text(text, reply_markup=reply_markup, **options)
    register_message(edited, options, media_paths)
    return edited
