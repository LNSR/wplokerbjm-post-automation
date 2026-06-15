from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.models import AgentError
from automation.telegram.auth import telegram_token
from automation.telegram.client import telegram_api


def telegram_file_path(file_id: str) -> str:
    data = telegram_api("getFile", {"file_id": file_id})
    result = data.get("result")
    if not isinstance(result, dict):
        result = {}
    file_path = result.get("file_path")
    if not file_path:
        raise AgentError("Telegram did not return a file_path.")
    return str(file_path)


def download_telegram_file(file_id: str) -> Path:
    remote_path = telegram_file_path(file_id)
    suffix = Path(remote_path).suffix or ".jpg"
    local_path = Path(tempfile.gettempdir()) / f"telegram-flyer-{uuid.uuid4().hex}{suffix}"
    request = Request(f"https://api.telegram.org/file/bot{telegram_token()}/{remote_path}")
    try:
        with urlopen(request, timeout=60) as response:
            local_path.write_bytes(response.read())
    except HTTPError as error:
        raise AgentError(f"Telegram file download failed ({error.code}).") from error
    except URLError as error:
        raise AgentError(f"Telegram file download failed: {error.reason}") from error
    return local_path


def telegram_document(message: dict[str, Any]) -> dict[str, Any] | None:
    document = message.get("document")
    return document if isinstance(document, dict) else None


def skill_document_file_id(message: dict[str, Any]) -> str | None:
    document = telegram_document(message)
    if not document or not document.get("file_id"):
        return None

    filename = str(document.get("file_name") or "")
    mime_type = str(document.get("mime_type") or "")
    is_markdown = filename.casefold().endswith(".md") or mime_type in {
        "text/markdown",
        "text/plain",
    }
    if not is_markdown:
        return None

    file_size = int(document.get("file_size") or 0)
    if file_size > 256 * 1024:
        raise AgentError("SKILL.md upload is too large; maximum size is 256 KB.")
    return str(document["file_id"])


def first_photo_file_id(message: dict[str, Any]) -> str | None:
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        candidates = [item for item in photos if isinstance(item, dict) and item.get("file_id")]
        if candidates:
            largest = max(candidates, key=lambda item: int(item.get("file_size") or 0))
            return str(largest["file_id"])

    document = telegram_document(message)
    if document:
        mime_type = str(document.get("mime_type") or "")
        if mime_type.startswith("image/") and document.get("file_id"):
            return str(document["file_id"])
    return None
