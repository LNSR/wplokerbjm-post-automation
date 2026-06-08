from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from automation.ai.opencode.probe import probe_opencode
from automation.config import BOT_SETTINGS
from automation.main import build_result
from automation.models import AgentError, BuildResult, TelegramChatCommandState, TelegramMediaGroupState
from automation.skills import load_skill_markdown, read_uploaded_skill
from automation.telegram.auth import allowed_telegram_username, authorize_update
from automation.telegram.client import telegram_send_message
from automation.telegram.files import download_telegram_file, first_photo_file_id
from automation.wordpress.auth import request_graphql_jwt


MEDIA_GROUP_DELAY_SECONDS = float(os.getenv("TELEGRAM_MEDIA_GROUP_DELAY_SECONDS", "2"))
BULK_COMMAND_TTL_SECONDS = float(os.getenv("TELEGRAM_BULK_COMMAND_TTL_SECONDS", "90"))
_MEDIA_GROUP_LOCK = threading.Lock()
_CHAT_COMMAND_LOCK = threading.Lock()
_MEDIA_GROUPS: dict[str, TelegramMediaGroupState] = {}
_MEDIA_GROUP_TIMERS: dict[str, threading.Timer] = {}
_CHAT_COMMANDS: dict[str, TelegramChatCommandState] = {}


def message_command(message: dict[str, Any]) -> str:
    text = str(message.get("text") or message.get("caption") or "").strip()
    return text.split()[0].split("@", 1)[0].lower() if text.startswith("/") else ""


def chat_key(chat_id: int | str) -> str:
    return str(chat_id)


def remember_bulk_command(chat_id: int | str, command: str) -> None:
    if command not in {"/post_prod", "/post_dev"}:
        return
    with _CHAT_COMMAND_LOCK:
        _CHAT_COMMANDS[chat_key(chat_id)] = TelegramChatCommandState(
            command=command,
            expires_at=time.monotonic() + BULK_COMMAND_TTL_SECONDS,
        )


def remembered_bulk_command(chat_id: int | str) -> str:
    key = chat_key(chat_id)
    with _CHAT_COMMAND_LOCK:
        state = _CHAT_COMMANDS.get(key)
        if state is None:
            return ""
        if state.expires_at < time.monotonic():
            _CHAT_COMMANDS.pop(key, None)
            return ""
        return state.command


def effective_flyer_command(chat_id: int | str, command: str) -> str:
    if command:
        remember_bulk_command(chat_id, command)
        return command
    return remembered_bulk_command(chat_id)


def format_preview(result: BuildResult) -> str:
    payload = result.payload.model_dump(exclude_none=True)
    wordpress = result.wordpress
    if wordpress:
        lines = [
            "PROD draft posted.",
            f"HTTP: {result.http_status}",
            f"ID: {wordpress.get('id', wordpress.get('existing_id', '-'))}",
            f"Edit: {wordpress.get('edit_url', '-')}",
        ]
        if result.warnings:
            lines.append("Warnings: " + "; ".join(result.warnings))
        return "\n".join(lines)

    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [
        "Mock payload preview only. Not posted.",
        "Send the same flyer with /post_prod to create a production draft.",
        "",
        payload_json,
    ]
    if result.warnings:
        lines.append("")
        lines.append("Warnings: " + "; ".join(result.warnings))
    return "\n".join(lines)


def handle_command(chat_id: int | str, text: str) -> str:
    command, _, rest = text.strip().partition(" ")
    command = command.split("@", 1)[0].lower()
    rest = rest.strip()

    if command in {"/start", "/help"}:
        return (
            "WPLokerBJM bot commands:\n"
            "/set_domain https://wp.example.com\n"
            "/refresh_jwt <wp_username> <wp_password>\n"
            "/set_skill as the caption of an attached SKILL.md file\n"
            "/reset_skill to restore the configured/repository fallback\n"
            "/status\n"
            "Send a flyer image to preview a mock payload.\n"
            "For bulk production posting, send /post_prod first and upload the images within 90 seconds."
        )

    if command == "/set_domain":
        if not rest.startswith(("http://", "https://")):
            return "Usage: /set_domain https://wp.example.com"
        BOT_SETTINGS.wordpress_base_url = rest.rstrip("/")
        return "WordPress domain URL updated for this running bot instance."

    if command in {"/refresh_jwt", "/set_jwt"}:
        username, _, password = rest.partition(" ")
        username = username or os.getenv("WP_LOGIN_USERNAME", "")
        password = password or os.getenv("WP_LOGIN_PASSWORD", "")
        if not username or not password:
            return "Usage: /refresh_jwt <wp_username> <wp_password>, or set WP_LOGIN_USERNAME/WP_LOGIN_PASSWORD env."
        BOT_SETTINGS.jwt = request_graphql_jwt(username, password)
        return "JWT refreshed from GraphQL and stored for this running bot instance."

    if command == "/reset_skill":
        BOT_SETTINGS.skill_markdown = None
        _, source = load_skill_markdown()
        return f"Runtime skill upload cleared. Active fallback: {source}."

    if command == "/status":
        _, skill_source = load_skill_markdown()
        opencode_status = probe_opencode()
        return (
            "Current runtime settings:\n"
            f"WordPress domain: {BOT_SETTINGS.wordpress_base_url or os.getenv('WPLBJM_WORDPRESS_DOMAIN') or os.getenv('WPLBJM_API_BASE_URL_PROD') or 'fallback missing'}\n"
            f"JWT: {'runtime set' if BOT_SETTINGS.jwt else 'env fallback'}\n"
            f"Skill: {skill_source}\n"
            f"Allowed Telegram username: @{allowed_telegram_username()}\n"
            f"OpenCode: {json.dumps(opencode_status.model_dump(exclude_none=True), ensure_ascii=False)}"
        )

    return "Unknown command. Send /help for options."


def process_flyer_message(chat_id: int | str, message: dict[str, Any], command: str) -> None:
    file_id = first_photo_file_id(message)
    if not file_id:
        telegram_send_message(chat_id, "Send a flyer image, or /help for commands.")
        return

    if command == "/post_dev":
        telegram_send_message(chat_id, "DEV posting has been removed. Send the flyer without a caption for mock preview, or use /post_prod to post to production.")
        return

    should_post = command == "/post_prod"

    image_path = download_telegram_file(file_id)
    try:
        result = build_result(image_path, post=should_post, model=None)
        telegram_send_message(chat_id, format_preview(result))
    except AgentError as error:
        telegram_send_message(chat_id, f"Failed: {error}")
    finally:
        image_path.unlink(missing_ok=True)


def media_group_key(chat_id: int | str, media_group_id: str) -> str:
    return f"{chat_id}:{media_group_id}"


def queue_media_group_message(chat_id: int | str, message: dict[str, Any], command: str) -> None:
    media_group_id = str(message.get("media_group_id") or "")
    if not media_group_id:
        process_flyer_message(chat_id, message, command)
        return
    if command:
        remember_bulk_command(chat_id, command)

    key = media_group_key(chat_id, media_group_id)
    with _MEDIA_GROUP_LOCK:
        state = _MEDIA_GROUPS.get(key)
        if state is None:
            state = TelegramMediaGroupState(
                chat_id=chat_id,
                media_group_id=media_group_id,
            )
            _MEDIA_GROUPS[key] = state

        message_id = message.get("message_id")
        if message_id is None or all(item.get("message_id") != message_id for item in state.messages):
            state.messages.append(message)
        if command:
            state.command = command

        existing_timer = _MEDIA_GROUP_TIMERS.get(key)
        if existing_timer:
            existing_timer.cancel()

        timer = threading.Timer(MEDIA_GROUP_DELAY_SECONDS, flush_media_group, args=(key,))
        timer.daemon = True
        _MEDIA_GROUP_TIMERS[key] = timer
        timer.start()


def flush_media_group(key: str) -> None:
    with _MEDIA_GROUP_LOCK:
        state = _MEDIA_GROUPS.pop(key, None)
        _MEDIA_GROUP_TIMERS.pop(key, None)

    if state is None:
        return

    messages = sorted(state.messages, key=lambda item: int(item.get("message_id") or 0))
    command = effective_flyer_command(state.chat_id, state.command or "")

    if command == "/post_prod":
        telegram_send_message(state.chat_id, f"Processing {len(messages)} media group item(s) with /post_prod.")
    elif not command:
        telegram_send_message(state.chat_id, f"Processing {len(messages)} media group item(s) as mock preview.")

    for message in messages:
        process_flyer_message(state.chat_id, message, command)


def handle_telegram_update(update: dict[str, Any]) -> None:
    authorized, message, chat_id = authorize_update(update)
    if not message or chat_id is None:
        return
    if not authorized:
        telegram_send_message(chat_id, "Unauthorized Telegram username.")
        return

    text = str(message.get("text") or message.get("caption") or "").strip()
    command = message_command(message)

    if command == "/set_skill":
        try:
            BOT_SETTINGS.skill_markdown = read_uploaded_skill(message)
            telegram_send_message(
                chat_id,
                "Uploaded SKILL.md is active for this running bot instance.",
            )
        except AgentError as error:
            telegram_send_message(chat_id, f"Failed: {error}")
        return

    if command == "/post_prod" and not first_photo_file_id(message):
        remember_bulk_command(chat_id, command)
        telegram_send_message(
            chat_id,
            f"Bulk /post_prod armed for the next {BULK_COMMAND_TTL_SECONDS:g} seconds. Send the flyer images now.",
        )
        return

    if text.startswith("/") and not first_photo_file_id(message):
        telegram_send_message(chat_id, handle_command(chat_id, text))
        return

    if not first_photo_file_id(message):
        telegram_send_message(chat_id, "Send a flyer image, or /help for commands.")
        return

    if message.get("media_group_id"):
        queue_media_group_message(chat_id, message, command)
        return

    process_flyer_message(chat_id, message, effective_flyer_command(chat_id, command))
