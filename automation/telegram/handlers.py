from __future__ import annotations

import json
import os
import threading
from typing import Any

from pydantic import ValidationError

from automation.ai.opencode.probe import probe_opencode
from automation.config import BOT_SETTINGS, env_float
from automation.main import build_result
from automation.models import (
    AgentError,
    BuildResult,
    TelegramMediaGroupState,
    TelegramPostDirective,
    normalize_telegram_username,
    validation_error_summary,
)
from automation.skills import load_skill_markdown, read_uploaded_skill
from automation.telegram.auth import (
    allowed_telegram_username,
    allowed_telegram_usernames,
    authorize_update,
    is_primary_telegram_user,
)
from automation.telegram.client import telegram_send_message
from automation.telegram.files import (
    download_telegram_file,
    first_photo_file_id,
)
from automation.payload.constants import AVAILABLE_GEMINI_MODELS
from automation.telegram.state import BulkCommandStore, ModelPreferenceStore, ProcessedMessageStore
from automation.wordpress.auth import request_graphql_jwt


MEDIA_GROUP_DELAY_SECONDS = float(
    env_float("TELEGRAM_MEDIA_GROUP_DELAY_SECONDS", "2")
)
BULK_COMMAND_TTL_SECONDS = float(
    env_float("TELEGRAM_BULK_COMMAND_TTL_SECONDS", "90")
)
_MEDIA_GROUP_LOCK = threading.Lock()
_MEDIA_GROUPS: dict[str, TelegramMediaGroupState] = {}
_MEDIA_GROUP_TIMERS: dict[str, threading.Timer] = {}
_BULK_COMMANDS = BulkCommandStore(ttl_seconds=BULK_COMMAND_TTL_SECONDS)
_PROCESSED_MESSAGES = ProcessedMessageStore(ttl_seconds=120.0)
_MODEL_PREFERENCES = ModelPreferenceStore()
_FLYER_PROCESSING_LOCK = threading.Lock()
MAX_CUSTOM_INSTRUCTION_LENGTH = 2000


def message_command(message: dict[str, Any]) -> str:
    text = str(message.get("text") or message.get("caption") or "").strip()
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@", 1)[0].lower()


def post_directive(
    message: dict[str, Any],
) -> TelegramPostDirective | None:
    if message_command(message) != "/post_prod":
        return None

    text = str(message.get("text") or message.get("caption") or "").strip()
    _, _, instruction = text.partition(" ")
    instruction = instruction.strip()
    if len(instruction) > MAX_CUSTOM_INSTRUCTION_LENGTH:
        raise AgentError(
            "Custom instruction is too long. Keep it at or below "
            f"{MAX_CUSTOM_INSTRUCTION_LENGTH} characters.",
        )
    return TelegramPostDirective(instruction=instruction or None)


def remember_bulk_command(
    chat_id: int | str,
    directive: TelegramPostDirective,
) -> None:
    _BULK_COMMANDS.remember(chat_id, directive)


def remembered_bulk_command(
    chat_id: int | str,
) -> TelegramPostDirective | None:
    return _BULK_COMMANDS.recall(chat_id)


def effective_post_directive(
    chat_id: int | str,
    directive: TelegramPostDirective | None,
) -> TelegramPostDirective | None:
    return _BULK_COMMANDS.effective(chat_id, directive)


def format_preview(result: BuildResult) -> str:
    payload = result.payload.model_dump(exclude_none=True)
    model_info = result.model_name or "unknown"
    wordpress = result.wordpress
    if wordpress:
        lines = [
            "PROD draft posted.",
            f"HTTP: {result.http_status}",
            f"ID: {wordpress.get('id', wordpress.get('existing_id', '-'))}",
            f"Edit: {wordpress.get('edit_url', '-')}",
            f"Model: {model_info}",
        ]
        if result.warnings:
            lines.append("Warnings: " + "; ".join(result.warnings))
        return "\n".join(lines)

    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [
        "Mock payload preview only. Not posted.",
        "Send the same flyer with /post_prod to create a production draft.",
        f"Model: {model_info}",
        "",
        payload_json,
    ]
    if result.warnings:
        lines.append("")
        lines.append("Warnings: " + "; ".join(result.warnings))
    return "\n".join(lines)


def handle_command(
    chat_id: int | str,
    text: str,
    *,
    is_owner: bool,
) -> str:
    command, _, rest = text.strip().partition(" ")
    command = command.split("@", 1)[0].lower()
    rest = rest.strip()

    if command in {"/start", "/help"}:
        models_list = ", ".join(
            f"{alias}={name}"
            for alias, name in AVAILABLE_GEMINI_MODELS.items()
        )
        return (
            "WPLokerBJM bot commands:\n"
            "/set_domain https://wp.example.com\n"
            "/refresh_jwt\n"
            "/set_skill as the caption of an attached SKILL.md file\n"
            "/reset_skill to restore the configured/repository fallback\n"
            "/add_users @username1 @username2 (owner only)\n"
            "/rm_users @username1 [@username2] (owner only)\n"
            "/reset_users (owner only)\n"
            "/set_model [alias]  — choose AI model; omit to list\n"
            "/current_model\n"
            "/status\n"
            f"Available models: {models_list}\n"
            "Send a flyer image to preview a mock payload.\n"
            "Use /post_prod [custom instruction] as an image caption, "
            "or send it first and upload images within 90 seconds."
        )

    if command == "/set_domain":
        if not rest.startswith(("http://", "https://")):
            return "Usage: /set_domain https://wp.example.com"
        BOT_SETTINGS.wordpress_base_url = rest.rstrip("/")
        return "WordPress domain URL updated for this running bot instance."

    if command == "/refresh_jwt":
        if rest:
            return (
                "/refresh_jwt does not accept credentials or other "
                "arguments. Configure WP_LOGIN_USERNAME and "
                "WP_LOGIN_PASSWORD in the deployment environment."
            )
        BOT_SETTINGS.jwt = request_graphql_jwt()
        return (
            "JWT refreshed from GraphQL and stored for this running "
            "bot instance."
        )

    if command == "/reset_skill":
        BOT_SETTINGS.skill_markdown = None
        _, source = load_skill_markdown()
        return f"Runtime skill upload cleared. Active fallback: {source}."

    if command in {"/add_users"}:
        if not is_owner:
            return "Only the primary Telegram owner can change allowed users."
        usernames = rest.replace(",", " ").split()
        if not usernames:
            return "Usage: /add_users @username1 @username2"
        primary = allowed_telegram_username()
        extras = [
            username
            for username in (
                *BOT_SETTINGS.extra_telegram_usernames,
                *usernames,
            )
            if username.lstrip("@").casefold() != primary
        ]
        try:
            BOT_SETTINGS.extra_telegram_usernames = extras
        except ValidationError as error:
            return "Invalid Telegram username list: " + validation_error_summary(
                error,
            )
        if not BOT_SETTINGS.extra_telegram_usernames:
            return "No extra Telegram users configured."
        formatted = ", ".join(
            f"@{username}"
            for username in BOT_SETTINGS.extra_telegram_usernames
        )
        return f"Runtime extra Telegram users now allowed: {formatted}."

    if command in {"/rm_users"}:
        if not is_owner:
            return "Only the primary Telegram owner can change allowed users."
        usernames = rest.replace(",", " ").split()
        if not usernames:
            return "Usage: /rm_users @username1 [@username2]"
        try:
            requested = {
                normalize_telegram_username(username)
                for username in usernames
            }
        except ValueError as error:
            return f"Invalid Telegram username list: {error}"

        existing = BOT_SETTINGS.extra_telegram_usernames
        removed = [
            username for username in existing if username in requested
        ]
        BOT_SETTINGS.extra_telegram_usernames = [
            username for username in existing if username not in requested
        ]
        if not removed:
            return "No matching runtime extra Telegram users found."
        formatted = ", ".join(f"@{username}" for username in removed)
        return f"Runtime extra Telegram users removed: {formatted}."

    if command == "/reset_users":
        if not is_owner:
            return "Only the primary Telegram owner can change allowed users."
        BOT_SETTINGS.extra_telegram_usernames = []
        return "Runtime extra Telegram users cleared."

    if command == "/set_model":
        if not rest:
            lines = [
                "Available AI models (use /set_model <alias>):",
            ]
            for alias, name in AVAILABLE_GEMINI_MODELS.items():
                marker = " ← active" if _MODEL_PREFERENCES.get_model(chat_id) == alias else ""
                lines.append(f"  {alias}  → {name}{marker}")
            lines.append("  default  → environment / fallback")
            return "\n".join(lines)

        if rest == "default":
            _MODEL_PREFERENCES.clear_model(chat_id)
            return (
                "Model preference cleared. "
                "The environment / fallback default will be used."
            )

        if rest not in AVAILABLE_GEMINI_MODELS:
            return (
                f"Unknown model alias \"{rest}\". "
                f"Use /set_model to list available models."
            )

        _MODEL_PREFERENCES.set_model(chat_id, rest)
        return (
            f"AI model set to \"{rest}\" "
            f"({AVAILABLE_GEMINI_MODELS[rest]}).\n"
            "The change applies to the next flyer you send."
        )

    if command == "/current_model":
        alias = _MODEL_PREFERENCES.get_model(chat_id)
        if alias:
            return (
                f"Active AI model: \"{alias}\" "
                f"({AVAILABLE_GEMINI_MODELS[alias]}).\n"
                "Send /set_model to change or choose a different model."
            )
        env_model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash (default)"
        return (
            f"No per-chat preference set. "
            f"Using environment / fallback: {env_model}.\n"
            "Send /set_model to choose a model."
        )

    if command == "/status":
        _, skill_source = load_skill_markdown()
        opencode_status = probe_opencode()
        wordpress_domain = (
            BOT_SETTINGS.wordpress_base_url
            or os.getenv("WPLBJM_API_BASE_URL_PROD")
            or "fallback missing"
        )
        opencode_json = json.dumps(
            opencode_status.model_dump(exclude_none=True),
            ensure_ascii=False,
        )
        allowed_users = ", ".join(
            f"@{username}"
            for username in sorted(allowed_telegram_usernames())
        )
        model_alias = _MODEL_PREFERENCES.get_model(chat_id)
        model_line = (
            f"AI model: \"{model_alias}\" ({AVAILABLE_GEMINI_MODELS[model_alias]})"
            if model_alias
            else "AI model: environment / fallback"
        )
        return (
            "Current runtime settings:\n"
            f"WordPress domain: {wordpress_domain}\n"
            f"JWT: {'runtime set' if BOT_SETTINGS.jwt else 'env fallback'}\n"
            f"Skill: {skill_source}\n"
            + model_line + "\n"
            f"Allowed Telegram users: {allowed_users}\n"
            f"OpenCode: {opencode_json}"
        )

    return "Unknown command. Send /help for options."


def process_flyer_message(
    chat_id: int | str,
    message: dict[str, Any],
    directive: TelegramPostDirective | None,
) -> None:
    file_id = first_photo_file_id(message)
    if not file_id:
        telegram_send_message(
            chat_id,
            "Send a flyer image, or /help for commands.",
        )
        return

    message_id = message.get("message_id")

    image_path = download_telegram_file(file_id)
    try:
        # Keep flyer extraction serialized so webhook and media-group threads
        # do not race through the same provider quota window.
        with _FLYER_PROCESSING_LOCK:
            # Double-check: Telegram webhook may have retried this same
            # update while we were waiting for the lock.  Skip silently
            # when another thread already handled it.
            if message_id and _PROCESSED_MESSAGES.is_processed(chat_id, message_id):
                return

            if message_id:
                _PROCESSED_MESSAGES.mark_processed(chat_id, message_id)

            model_alias = _MODEL_PREFERENCES.get_model(chat_id)
            model_name = (
                AVAILABLE_GEMINI_MODELS.get(model_alias)
                if model_alias
                else None
            )
            result = build_result(
                image_path,
                post=directive is not None,
                model=model_name,
                custom_instruction=(
                    directive.instruction if directive is not None else None
                ),
            )
        telegram_send_message(chat_id, format_preview(result))
    except AgentError as error:
        telegram_send_message(chat_id, f"Failed: {error}")
    finally:
        image_path.unlink(missing_ok=True)


def media_group_key(chat_id: int | str, media_group_id: str) -> str:
    return f"{chat_id}:{media_group_id}"


def queue_media_group_message(
    chat_id: int | str,
    message: dict[str, Any],
    directive: TelegramPostDirective | None,
) -> None:
    media_group_id = str(message.get("media_group_id") or "")
    if not media_group_id:
        process_flyer_message(chat_id, message, directive)
        return
    if directive is not None:
        remember_bulk_command(chat_id, directive)

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
        is_new_message = message_id is None or all(
            item.get("message_id") != message_id
            for item in state.messages
        )
        if is_new_message:
            state.messages.append(message)
        if directive is not None:
            state.directive = directive

        existing_timer = _MEDIA_GROUP_TIMERS.get(key)
        if existing_timer:
            existing_timer.cancel()

        timer = threading.Timer(
            MEDIA_GROUP_DELAY_SECONDS,
            flush_media_group,
            args=(key,),
        )
        timer.daemon = True
        _MEDIA_GROUP_TIMERS[key] = timer
        timer.start()


def flush_media_group(key: str) -> None:
    with _MEDIA_GROUP_LOCK:
        state = _MEDIA_GROUPS.pop(key, None)
        _MEDIA_GROUP_TIMERS.pop(key, None)

    if state is None:
        return

    messages = sorted(
        state.messages,
        key=lambda item: int(item.get("message_id") or 0),
    )
    directive = effective_post_directive(state.chat_id, state.directive)

    if directive is not None:
        instruction_note = (
            " Custom instruction applied."
            if directive.instruction
            else ""
        )
        telegram_send_message(
            state.chat_id,
            f"Processing {len(messages)} media group item(s) with "
            f"/post_prod.{instruction_note}",
        )
    else:
        telegram_send_message(
            state.chat_id,
            f"Processing {len(messages)} media group item(s) as mock "
            "preview.",
        )

    for message in messages:
        process_flyer_message(state.chat_id, message, directive)


def handle_telegram_update(update: dict[str, Any]) -> None:
    authorized, message, chat_id = authorize_update(update)
    if not message or chat_id is None:
        return
    if not authorized:
        telegram_send_message(chat_id, "Unauthorized Telegram username.")
        return

    text = str(message.get("text") or message.get("caption") or "").strip()
    command = message_command(message)
    try:
        directive = post_directive(message)
    except AgentError as error:
        telegram_send_message(chat_id, f"Failed: {error}")
        return

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

    if directive is not None and not first_photo_file_id(message):
        remember_bulk_command(chat_id, directive)
        instruction_note = (
            " The custom instruction will apply to every image."
            if directive.instruction
            else ""
        )
        telegram_send_message(
            chat_id,
            f"Bulk /post_prod armed for the next "
            f"{BULK_COMMAND_TTL_SECONDS:g} seconds. Send the flyer "
            f"images now.{instruction_note}",
        )
        return

    if text.startswith("/") and not first_photo_file_id(message):
        telegram_send_message(
            chat_id,
            handle_command(
                chat_id,
                text,
                is_owner=is_primary_telegram_user(update),
            ),
        )
        return

    if not first_photo_file_id(message):
        telegram_send_message(
            chat_id,
            "Send a flyer image, or /help for commands.",
        )
        return

    if command and directive is None:
        telegram_send_message(
            chat_id,
            "Unsupported image command. Use /post_prod "
            "[custom instruction], or remove the caption for a mock preview.",
        )
        return

    if message.get("media_group_id"):
        queue_media_group_message(chat_id, message, directive)
        return

    process_flyer_message(
        chat_id,
        message,
        effective_post_directive(chat_id, directive),
    )
