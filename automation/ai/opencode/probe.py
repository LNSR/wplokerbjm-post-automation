from __future__ import annotations

import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from automation.ai.opencode.client import (
    opencode_endpoint,
    opencode_headers,
    opencode_response_text,
)
from automation.config import opencode_api_key, opencode_key_label
from automation.models import (
    AgentError,
    OpenCodeAttempt,
    OpenCodeProbeAttemptResult,
    OpenCodeProbeResult,
    validation_error_summary,
)
from automation.payload.constants import DEFAULT_OPENCODE_CHAIN
from automation.wordpress.client import parse_json_response


def normalize_opencode_attempt(attempt: OpenCodeAttempt) -> OpenCodeAttempt:
    if attempt.provider == "zen" and attempt.model == "minimax-m3":
        return OpenCodeAttempt(
            provider="go", model=attempt.model, endpoint_style="messages"
        )
    if (
        attempt.provider == "go"
        and attempt.model == "minimax-m3"
        and attempt.endpoint_style != "messages"
    ):
        return OpenCodeAttempt(
            provider=attempt.provider, model=attempt.model, endpoint_style="messages"
        )
    return attempt


def new_opencode_attempt(
    provider: str, model: str, endpoint_style: str
) -> OpenCodeAttempt:
    try:
        return normalize_opencode_attempt(
            OpenCodeAttempt(
                provider=provider, model=model, endpoint_style=endpoint_style
            ),
        )
    except ValidationError as error:
        raise AgentError(
            f"Invalid OpenCode model chain item: {validation_error_summary(error)}"
        ) from error


def probe_opencode_attempt(attempt: OpenCodeAttempt) -> OpenCodeProbeAttemptResult:
    attempt = normalize_opencode_attempt(attempt)
    api_key = opencode_api_key(attempt.provider)
    if not api_key:
        return OpenCodeProbeAttemptResult(
            provider=attempt.provider,
            model=attempt.model,
            endpoint_style=attempt.endpoint_style,
            ok=False,
            message=f"missing {opencode_key_label(attempt.provider)}",
        )

    if attempt.endpoint_style == "messages":
        body = {
            "model": attempt.model,
            "max_tokens": 8,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Reply with OK only."}],
                }
            ],
        }
    else:
        body = {
            "model": attempt.model,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
            "temperature": 0,
            "max_tokens": 8,
        }

    request = Request(
        opencode_endpoint(attempt.provider, attempt.endpoint_style),
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=opencode_headers(api_key, attempt.endpoint_style),
    )
    try:
        with urlopen(
            request, context=ssl._create_unverified_context(), timeout=30
        ) as response:
            data = parse_json_response(
                response.read().decode("utf-8", errors="replace")
            )
            text = opencode_response_text(data, attempt.endpoint_style)
            return OpenCodeProbeAttemptResult(
                provider=attempt.provider,
                ok=response.status == 200,
                status=response.status,
                model=attempt.model,
                endpoint_style=attempt.endpoint_style,
                sample=(text or "")[:20],
            )
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        data = parse_json_response(body)
        message = data.get("message") or data.get("error") or data
        return OpenCodeProbeAttemptResult(
            provider=attempt.provider,
            model=attempt.model,
            endpoint_style=attempt.endpoint_style,
            ok=False,
            status=error.code,
            message=message,
        )
    except URLError as error:
        return OpenCodeProbeAttemptResult(
            provider=attempt.provider,
            model=attempt.model,
            endpoint_style=attempt.endpoint_style,
            ok=False,
            message=str(error.reason),
        )


def probe_opencode() -> OpenCodeProbeResult:
    chain = opencode_attempts()
    return OpenCodeProbeResult(
        attempts=[probe_opencode_attempt(attempt) for attempt in chain],
        chain=chain,
    )


def probe_opencode_simple() -> dict[str, str]:
    """Instant env-var check — no HTTP calls. Safe for Telegram /status, Render free has timeout limit for free tier"""
    api_key = opencode_api_key("go")
    gemini_key = os.getenv("GOOGLE_AI_STUDIO_KEY")
    jwt = os.getenv("WPLBJM_JWT_PROD")
    chain = os.getenv("OPENCODE_MODEL_CHAIN", DEFAULT_OPENCODE_CHAIN)
    return {
        "opencode_key": "present" if api_key else "missing",
        "gemini_key": "present" if gemini_key else "missing",
        "jwt": "present" if jwt else "missing",
        "chain": chain,
    }


def opencode_attempts(
    model_override: str | None = None,
    *,
    chain_override: str | None = None,
) -> list[OpenCodeAttempt]:
    """Parse an OpenCode model chain.

    ``model_override`` supports explicit ``provider:model`` or
    ``provider:model:endpoint_style`` syntax for CLI use.

    ``chain_override`` takes priority over the ``OPENCODE_MODEL_CHAIN`` env var
    when ``model_override`` is not given or is a bare model name (no colon).

    Bare model names (no ``:``) are **not** auto-wrapped with any provider —
    they fall through to the chain, avoiding accidental ``zen:`` billing.
    """
    if model_override and ":" in model_override:
        parts = model_override.split(":")
        if len(parts) == 2:
            return [new_opencode_attempt(parts[0], parts[1], "chat")]
        if len(parts) == 3:
            return [new_opencode_attempt(parts[0], parts[1], parts[2])]
        raise AgentError(
            "--model must be provider:model or provider:model:endpoint_style"
        )

    chain = chain_override or os.getenv("OPENCODE_MODEL_CHAIN", DEFAULT_OPENCODE_CHAIN)
    attempts: list[OpenCodeAttempt] = []
    for raw_item in chain.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise AgentError(
                "OPENCODE_MODEL_CHAIN items must use provider:model:endpoint_style"
            )
        attempts.append(new_opencode_attempt(parts[0], parts[1], parts[2]))
    return attempts
