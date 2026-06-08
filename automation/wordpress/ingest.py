from __future__ import annotations

import json
import ssl
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.ai.opencode.vision import image_mime_type
from automation.models import AgentError, NormalizedPayload, WordpressConfig
from automation.wordpress.client import parse_json_response, request_json


def ingest_options(config: WordpressConfig) -> dict[str, Any]:
    status, data = request_json(
        f"{config.base_url}/wp-json/wplokerbjm/v1/lowongan/ingest/options",
        config.jwt,
    )
    if status != 200:
        code = data.get("code", "options_request_failed")
        message = data.get("message", "Unable to load ingest options.")
        raise AgentError(f"Options request failed ({status} {code}): {message}")
    return data


def encode_multipart(payload: NormalizedPayload, image_path: Path) -> tuple[str, bytes]:
    boundary = "----wplbjm" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def add(value: str | bytes) -> None:
        chunks.append(value if isinstance(value, bytes) else value.encode("utf-8"))

    add(f"--{boundary}\r\n")
    add('Content-Disposition: form-data; name="payload"\r\n\r\n')
    add(json.dumps(payload.model_dump(exclude_none=True), ensure_ascii=False))
    add("\r\n")

    add(f"--{boundary}\r\n")
    add(f'Content-Disposition: form-data; name="featured_image"; filename="{image_path.name}"\r\n')
    add(f"Content-Type: {image_mime_type(image_path)}\r\n\r\n")
    chunks.append(image_path.read_bytes())
    add("\r\n")

    add(f"--{boundary}--\r\n")
    return boundary, b"".join(chunks)


def post_draft(config: WordpressConfig, payload: NormalizedPayload, image_path: Path) -> tuple[int, dict[str, Any]]:
    boundary, body = encode_multipart(payload, image_path)
    request = Request(
        f"{config.base_url}/wp-json/wplokerbjm/v1/lowongan/ingest",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {config.jwt}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=120) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json_response(body_text)
    except HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        return error.code, parse_json_response(body_text)
    except URLError as error:
        raise AgentError(f"Draft post failed: {error.reason}") from error
