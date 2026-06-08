from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from automation.ai.opencode.vision import (
    data_url_for_image,
    image_mime_type,
    opencode_direct_image_text,
    opencode_user_text,
)
from automation.models import AgentError


def opencode_endpoint(provider: str, endpoint_style: str) -> str:
    if provider == "zen":
        base = "https://opencode.ai/zen/v1"
    elif provider == "go":
        base = "https://opencode.ai/zen/go/v1"
    else:
        raise AgentError(f"Unsupported OpenCode provider: {provider}")

    if endpoint_style == "chat":
        return f"{base}/chat/completions"
    if endpoint_style == "messages":
        return f"{base}/messages"
    raise AgentError(f"Unsupported OpenCode endpoint style: {endpoint_style}")


def opencode_headers(api_key: str, endpoint_style: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "WPLokerBJMPostAutomation/1.0",
    }
    if endpoint_style == "messages":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def opencode_chat_body(
    model: str,
    prompt: str,
    image_path: Path,
    vision_text: str,
    *,
    contract_error: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": opencode_user_text(image_path, vision_text, contract_error),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def opencode_chat_image_body(
    model: str,
    prompt: str,
    image_path: Path,
    *,
    contract_error: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": opencode_direct_image_text(image_path, contract_error),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url_for_image(image_path)},
                    },
                ],
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def opencode_messages_body(
    model: str,
    prompt: str,
    image_path: Path,
    vision_text: str,
    *,
    contract_error: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "system": prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": opencode_user_text(image_path, vision_text, contract_error),
                    },
                ],
            }
        ],
    }


def opencode_messages_image_body(
    model: str,
    prompt: str,
    image_path: Path,
    *,
    contract_error: str | None = None,
) -> dict[str, Any]:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "system": prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": opencode_direct_image_text(image_path, contract_error),
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_mime_type(image_path),
                            "data": encoded,
                        },
                    },
                ],
            }
        ],
    }


def opencode_response_text(data: dict[str, Any], endpoint_style: str) -> str | None:
    if endpoint_style == "chat":
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(
                        str(part.get("text", ""))
                        for part in content
                        if isinstance(part, dict)
                    )
    if endpoint_style == "messages":
        content = data.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
    return None
