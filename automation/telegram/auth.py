from __future__ import annotations

from typing import Any

from automation.config import BOT_SETTINGS, env_value


def telegram_token() -> str:
    return env_value("TELEGRAM_BOT_TOKEN")


def allowed_telegram_username() -> str:
    return env_value("TELEGRAM_USERNAME").lstrip("@").casefold()


def allowed_telegram_usernames() -> frozenset[str]:
    return frozenset(
        {
            allowed_telegram_username(),
            *BOT_SETTINGS.extra_telegram_usernames,
        }
    )


def telegram_sender_username(update: dict[str, Any]) -> str:
    message = update.get("message")
    if not isinstance(message, dict):
        return ""
    sender = message.get("from")
    if not isinstance(sender, dict):
        return ""
    return str(sender.get("username") or "").casefold()


def is_primary_telegram_user(update: dict[str, Any]) -> bool:
    return telegram_sender_username(update) == allowed_telegram_username()


def authorize_update(update: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, int | None]:
    message = update.get("message")
    if not isinstance(message, dict):
        return False, None, None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        chat = {}
    chat_id = chat.get("id")
    username = telegram_sender_username(update)
    return username in allowed_telegram_usernames(), message, chat_id
