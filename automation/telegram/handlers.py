from __future__ import annotations

import json
import os
from typing import Any

from automation.ai.opencode.probe import probe_opencode
from automation.config import BOT_SETTINGS
from automation.main import build_result
from automation.models import AgentError, BuildResult
from automation.skills import load_skill_markdown, read_uploaded_skill
from automation.telegram.auth import allowed_telegram_username, authorize_update
from automation.telegram.client import telegram_send_message
from automation.telegram.files import download_telegram_file, first_photo_file_id
from automation.wordpress.auth import request_graphql_jwt


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
            "Send a flyer image to preview a mock payload. Add caption /post_prod to post to production."
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


def handle_telegram_update(update: dict[str, Any]) -> None:
    authorized, message, chat_id = authorize_update(update)
    if not message or chat_id is None:
        return
    if not authorized:
        telegram_send_message(chat_id, "Unauthorized Telegram username.")
        return

    text = str(message.get("text") or message.get("caption") or "").strip()
    command = text.split()[0].split("@", 1)[0].lower() if text.startswith("/") else ""

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

    if text.startswith("/") and not first_photo_file_id(message):
        telegram_send_message(chat_id, handle_command(chat_id, text))
        return

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
