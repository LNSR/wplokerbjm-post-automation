from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from automation.models import (
    BuildResult,
    NormalizedPayload,
    TelegramPostDirective,
)
from automation.telegram import handlers


@pytest.fixture(autouse=True)
def reset_handler_state() -> None:
    handlers._MEDIA_GROUPS.clear()
    handlers._MEDIA_GROUP_TIMERS.clear()
    handlers._BULK_COMMANDS = handlers.BulkCommandStore(
        ttl_seconds=handlers.BULK_COMMAND_TTL_SECONDS,
    )


def cancel_and_flush_all_groups() -> None:
    for key in list(handlers._MEDIA_GROUP_TIMERS):
        with handlers._MEDIA_GROUP_LOCK:
            timer = handlers._MEDIA_GROUP_TIMERS.pop(key)
            timer.cancel()
        handlers.flush_media_group(key)


def image_message(
    *,
    message_id: int,
    media_group_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": message_id,
        "photo": [{"file_id": f"file-{message_id}", "file_size": 10}],
    }
    if media_group_id:
        message["media_group_id"] = media_group_id
    if caption:
        message["caption"] = caption
    return message


def test_split_media_groups_inherit_post_prod_and_deduplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[
        tuple[
            str,
            int | str,
            int | str | None,
            TelegramPostDirective | None,
        ]
    ] = []
    sent: list[str] = []
    directive = TelegramPostDirective(
        instruction="Prefer the QR application URL.",
    )

    monkeypatch.setattr(
        handlers,
        "telegram_send_message",
        lambda chat_id, text: sent.append(str(text)),
    )
    monkeypatch.setattr(
        handlers,
        "process_flyer_message",
        lambda chat_id, message, current_directive: calls.append(
            (
                "process",
                chat_id,
                message.get("message_id"),
                current_directive,
            )
        ),
    )

    handlers.queue_media_group_message(
        123,
        image_message(
            message_id=1,
            media_group_id="album-1",
            caption="/post_prod Prefer the QR application URL.",
        ),
        directive,
    )
    handlers.queue_media_group_message(
        123,
        image_message(message_id=2, media_group_id="album-2"),
        None,
    )
    handlers.queue_media_group_message(
        123,
        image_message(message_id=2, media_group_id="album-2"),
        None,
    )

    cancel_and_flush_all_groups()

    assert calls == [
        ("process", 123, 1, directive),
        ("process", 123, 2, directive),
    ]
    assert sent == [
        "Processing 1 media group item(s) with /post_prod. "
        "Custom instruction applied.",
        "Processing 1 media group item(s) with /post_prod. "
        "Custom instruction applied.",
    ]


def test_standalone_post_prod_arms_bulk_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies: list[str] = []
    monkeypatch.setattr(
        handlers,
        "authorize_update",
        lambda update: (True, update["message"], update["message"]["chat"]["id"]),
    )
    monkeypatch.setattr(
        handlers,
        "telegram_send_message",
        lambda chat_id, text: replies.append(str(text)),
    )

    handlers.handle_telegram_update(
        {
            "message": {
                "chat": {"id": 123},
                "text": "/post_prod Keep titles concise",
            }
        }
    )

    assert handlers.remembered_bulk_command(123) == TelegramPostDirective(
        instruction="Keep titles concise",
    )
    assert replies == [
        "Bulk /post_prod armed for the next 90 seconds. Send the flyer "
        "images now. The custom instruction will apply to every image."
    ]


def test_plain_album_without_command_is_mock_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[
        tuple[
            int | str,
            int | str | None,
            TelegramPostDirective | None,
        ]
    ] = []
    sent: list[str] = []
    monkeypatch.setattr(
        handlers,
        "telegram_send_message",
        lambda chat_id, text: sent.append(str(text)),
    )
    monkeypatch.setattr(
        handlers,
        "process_flyer_message",
        lambda chat_id, message, directive: calls.append(
            (chat_id, message.get("message_id"), directive)
        ),
    )

    handlers.queue_media_group_message(
        123,
        image_message(message_id=1, media_group_id="album-1"),
        None,
    )
    cancel_and_flush_all_groups()

    assert sent == ["Processing 1 media group item(s) as mock preview."]
    assert calls == [(123, 1, None)]


def test_post_directive_extracts_custom_instruction() -> None:
    directive = handlers.post_directive(
        {
            "caption": (
                "/post_prod@wplokerbjm_bot "
                "Use the decoded QR URL as the application link"
            )
        }
    )

    assert directive == TelegramPostDirective(
        instruction="Use the decoded QR URL as the application link",
    )


def test_unknown_image_command_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies: list[str] = []
    processed: list[bool] = []
    message = image_message(message_id=1, caption="/unknown")
    message["chat"] = {"id": 123}
    monkeypatch.setattr(
        handlers,
        "authorize_update",
        lambda update: (True, update["message"], 123),
    )
    monkeypatch.setattr(
        handlers,
        "telegram_send_message",
        lambda chat_id, text: replies.append(str(text)),
    )
    monkeypatch.setattr(
        handlers,
        "process_flyer_message",
        lambda *args: processed.append(True),
    )

    handlers.handle_telegram_update({"message": message})

    assert processed == []
    assert replies == [
        "Unsupported image command. Use /post_prod [custom instruction], "
        "or remove the caption for a mock preview."
    ]


def test_owner_can_add_runtime_extra_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "primary_owner")
    handlers.BOT_SETTINGS.extra_telegram_usernames = ["existing_user"]

    response = handlers.handle_command(
        123,
        "/add_users @Second_User, third_user @SECOND_USER",
        is_owner=True,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == [
        "existing_user",
        "second_user",
        "third_user",
    ]
    assert response == (
        "Runtime extra Telegram users now allowed: "
        "@existing_user, @second_user, @third_user."
    )


def test_extra_user_cannot_change_runtime_access() -> None:
    response = handlers.handle_command(
        123,
        "/add_users @another_user",
        is_owner=False,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == []
    assert response == (
        "Only the primary Telegram owner can change allowed users."
    )


def test_owner_can_clear_runtime_extra_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "primary_owner")
    handlers.BOT_SETTINGS.extra_telegram_usernames = ["second_user"]

    response = handlers.handle_command(
        123,
        "/reset_users",
        is_owner=True,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == []
    assert response == "Runtime extra Telegram users cleared."


def test_owner_can_remove_selected_runtime_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "primary_owner")
    handlers.BOT_SETTINGS.extra_telegram_usernames = [
        "first_user",
        "second_user",
        "third_user",
    ]

    response = handlers.handle_command(
        123,
        "/rm_users @SECOND_USER, @third_user",
        is_owner=True,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == ["first_user"]
    assert response == (
        "Runtime extra Telegram users removed: "
        "@second_user, @third_user."
    )


def test_remove_unknown_runtime_user_keeps_current_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "primary_owner")
    handlers.BOT_SETTINGS.extra_telegram_usernames = ["first_user"]

    response = handlers.handle_command(
        123,
        "/rm_users @missing_user",
        is_owner=True,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == ["first_user"]
    assert response == "No matching runtime extra Telegram users found."


def test_owner_cannot_set_invalid_runtime_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_USERNAME", "primary_owner")

    response = handlers.handle_command(
        123,
        "/add_users invalid user!",
        is_owner=True,
    )

    assert handlers.BOT_SETTINGS.extra_telegram_usernames == []
    assert response.startswith("Invalid Telegram username list:")


def test_flyer_processing_is_serialized_across_threads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    active = 0
    max_active = 0
    state_lock = threading.Lock()
    sent: list[str] = []
    counter = 0

    monkeypatch.setattr(
        handlers,
        "first_photo_file_id",
        lambda message: str(message["message_id"]),
    )

    def fake_download(file_id: str) -> Path:
        nonlocal counter
        counter += 1
        path = tmp_path / f"flyer-{counter}.jpg"
        path.write_bytes(b"image")
        return path

    def fake_build_result(*args, **kwargs) -> BuildResult:
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with state_lock:
            active -= 1
        return BuildResult(
            mode="mock_preview",
            payload=NormalizedPayload(
                title="Test | AI posted draft",
            ),
        )

    monkeypatch.setattr(handlers, "download_telegram_file", fake_download)
    monkeypatch.setattr(handlers, "build_result", fake_build_result)
    monkeypatch.setattr(
        handlers,
        "telegram_send_message",
        lambda chat_id, text: sent.append(str(text)),
    )

    threads = [
        threading.Thread(
            target=handlers.process_flyer_message,
            args=(123, image_message(message_id=message_id), None),
        )
        for message_id in (1, 2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
    assert len(sent) == 2
