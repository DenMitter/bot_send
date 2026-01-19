from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.config import get_settings


def _logs_dir() -> Path:
    settings = get_settings()
    return Path(settings.media_dir) / "mailing_logs"


def get_mailing_log_path(mailing_id: int) -> Path:
    return _logs_dir() / f"mailing_{mailing_id}.txt"


def append_recipient_log(mailing_id: int, user_id: int | str, username: str | None, error: str) -> None:
    path = get_mailing_log_path(mailing_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().isoformat()
    line = f"[{timestamp}] recipient={user_id} username={username or '-'} error={error}\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
