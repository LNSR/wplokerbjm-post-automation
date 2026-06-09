from __future__ import annotations

from automation.config import BOT_SETTINGS
from automation.telegram.auth import (
    allowed_telegram_usernames,
    authorize_update,
    is_primary_telegram_user,
)


def telegram_update(username: str) -> dict[str, object]:
    return {
        "message": {
            "chat": {"id": 123},
            "from": {"username": username},
            "text": "/status",
        }
    }


def test_runtime_extra_username_is_authorized(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "PrimaryOwner")
    BOT_SETTINGS.extra_telegram_usernames = ["@Extra_User"]

    authorized, _, _ = authorize_update(telegram_update("extra_user"))

    assert authorized is True
    assert allowed_telegram_usernames() == {
        "primaryowner",
        "extra_user",
    }


def test_runtime_extra_username_is_not_primary_owner(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "PrimaryOwner")
    BOT_SETTINGS.extra_telegram_usernames = ["extra_user"]

    assert is_primary_telegram_user(telegram_update("extra_user")) is False
    assert is_primary_telegram_user(telegram_update("PRIMARYOWNER")) is True


def test_unknown_username_remains_unauthorized(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "PrimaryOwner")
    BOT_SETTINGS.extra_telegram_usernames = ["extra_user"]

    authorized, _, _ = authorize_update(telegram_update("unknown_user"))

    assert authorized is False
