from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.models import AgentError


def request_json(url: str, token: str, *, timeout: int = 30) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json_response(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, parse_json_response(body)
    except URLError as error:
        raise AgentError(f"Request failed: {error.reason}") from error


def parse_json_response(body: str) -> dict[str, Any]:
    """Recover JSON even when local WordPress appends PHP notices."""

    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(body[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        raise AgentError("Response was not valid JSON.")
