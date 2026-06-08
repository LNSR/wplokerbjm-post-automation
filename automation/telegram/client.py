from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.models import AgentError
from automation.telegram.auth import telegram_token
from automation.wordpress.client import parse_json_response


def telegram_api(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{telegram_token()}/{method}",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = parse_json_response(response.read().decode("utf-8", errors="replace"))
    except HTTPError as error:
        data = parse_json_response(error.read().decode("utf-8", errors="replace"))
        raise AgentError(f"Telegram API failed ({error.code}): {data.get('description', data)}") from error
    except URLError as error:
        raise AgentError(f"Telegram API failed: {error.reason}") from error

    if data.get("ok") is False:
        raise AgentError(f"Telegram API failed: {data.get('description', 'unknown error')}")
    return data


def telegram_send_message(chat_id: int | str, text: str) -> None:
    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": True,
        },
    )
