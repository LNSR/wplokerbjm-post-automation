from __future__ import annotations

from typing import Any

from automation.config import env_value


def telegram_token() -> str:
    return env_value("TELEGRAM_BOT_TOKEN")


def allowed_telegram_username() -> str:
    return env_value("TELEGRAM_USERNAME").lstrip("@").casefold()


def authorize_update(update: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, int | None]:
    message = update.get("message")
    if not isinstance(message, dict):
        return False, None, None
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    username = str(sender.get("username") or "").casefold()
    return username == allowed_telegram_username(), message, chat_id
