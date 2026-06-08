from __future__ import annotations

import os
from typing import Any

from automation.telegram.client import telegram_api


def public_base_url() -> str | None:
    explicit_url = os.getenv("PUBLIC_BASE_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")

    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if render_hostname:
        return f"https://{render_hostname.strip('/')}"

    return None


def telegram_webhook_url() -> str | None:
    base_url = public_base_url()
    return f"{base_url}/telegram/webhook" if base_url else None


def register_telegram_webhook() -> dict[str, Any] | None:
    webhook_url = telegram_webhook_url()
    if not webhook_url:
        return None

    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message"],
        "drop_pending_updates": False,
    }
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret:
        payload["secret_token"] = secret

    return telegram_api("setWebhook", payload)
