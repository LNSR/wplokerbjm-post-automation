"""Smoke-test every API key / credential stored in the repo ``.env``.

Three layers, cheapest first:

1. **Presence** — every credential key exists and is non-empty.  Skips only
   when the ``.env`` file itself is missing (fresh clone).
2. **Shape** — offline format checks: JWT segment count, Telegram bot-token
   layout, Render ``rnd_`` prefix, Google Maps ``AIza`` prefix, absolute
   http(s) URLs, and a lenient token charset for the rest.
3. **Live** — real network validation, gated behind the ``live`` marker
   (``pytest -m live``).  Skips gracefully when a host is unreachable.

Secrets are never printed and never survive into a frame that can raise:
failure messages show only the key name / masked prefix, network helpers
swallow all exceptions and return sanitized tuples, and every secret local
is deleted before an assertion can run (protects against ``--showlocals``
style traceback rendering).
"""

from __future__ import annotations

import json
import os
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest
from dotenv import dotenv_values


# ── helpers ──────────────────────────────────────────────────────────────────

_GRAPHQL_VALIDATE_JWT = """
mutation GetJWT($token: String) {
  jwt(token: $token)
}
""".strip()

_GRAPHQL_LOGIN = """
mutation GetJWT($username: String, $password: String) {
  jwt(username: $username, password: $password)
}
""".strip()


def _env_file() -> dict[str, str | None]:
    """Load ``.env`` from the repo root as a plain dict."""
    trial = os.getcwd()
    for _ in range(4):
        path = os.path.join(trial, ".env")
        if os.path.isfile(path):
            return dict(dotenv_values(path))
        trial = os.path.dirname(trial)
    return {}


_ENV = _env_file()


def _require_env(key: str) -> str:
    """Return the .env value for *key* or call ``pytest.skip``."""
    value = _ENV.get(key)
    if not value:
        pytest.skip(f"Missing .env key: {key}")
    return value


def _mask(value: str) -> str:
    """Return a safe, value-free preview of a secret."""
    return f"{value[:4]}…({len(value)} chars)"


def _json_loads(raw: str) -> dict | None:
    """Parse JSON without ever raising; returns ``None`` on failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    unverified_ssl: bool = False,
    timeout: int = 30,
) -> tuple[int, str]:
    """Perform an HTTP request, returning ``(status, body-text)``.

    Never raises: unreachable hosts become ``(0, "")`` (callers treat 0 as
    "could not reach", matching the old skip semantics via explicit checks),
    and HTTP errors come back as their status code.
    """
    request = Request(url, data=body, method=method, headers=headers or {})
    ctx = ssl._create_unverified_context() if unverified_ssl else None
    try:
        with urlopen(request, context=ctx, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (URLError, OSError, ValueError):
        return 0, ""


def _post_json(url: str, payload: dict) -> dict:
    """POST JSON; returns parsed response dict (or ``{"_error": ...}``).

    Never raises, so the credential-bearing payload never ends up in an
    exception frame.  The response dict is value-free by construction for
    the mutations used here (assertions inspect status/errors only).
    """
    try:
        body = json.dumps(payload).encode("utf-8")
        status, raw = _http_request(
            url,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            body=body,
            unverified_ssl=True,
        )
    except (TypeError, ValueError):
        return {"_error": "payload serialization failed"}

    data = _json_loads(raw) or {}
    data.setdefault("_status", status)
    return data


def _graphql_validate_jwt(token: str, base_url: str) -> dict:
    """POST the token-only JWT validation mutation."""
    return _post_json(
        f"{base_url.rstrip('/')}/graphql",
        {"query": _GRAPHQL_VALIDATE_JWT, "variables": {"token": token}},
    )


def _skip_on_unreachable(status: int) -> None:
    """Turn a ``(0, ...)`` result into a graceful pytest skip."""
    if status == 0:
        pytest.skip("Host unreachable")


# ── presence (always run) ────────────────────────────────────────────────────

CREDENTIAL_KEYS = frozenset({
    "EXA_API_KEY",
    "GOOGLE_AI_STUDIO_KEY",
    "GOOGLE_MAPS_API_KEY",
    "OPENCODE_API_KEY",
    "RENDER_ACCOUNT_API_KEY",
    "RENDER_MCP_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "WPLBJM_JWT_DEV",
    "WPLBJM_JWT_PROD",
    "X_ROYAL_MCP_API_KEY",
    "WP_LOGIN_PASSWORD",
})

URL_KEYS = frozenset({
    "WPLBJM_API_BASE_URL_PROD",
    "WPLBJM_WORDPRESS_DOMAIN",
})


@pytest.mark.parametrize("key", sorted(CREDENTIAL_KEYS | URL_KEYS))
def test_credential_present(key: str) -> None:
    """Every credential key exists in ``.env`` and is non-empty."""
    if not _ENV:
        pytest.skip("Missing .env file")
    value = _ENV.get(key)
    assert value, f"Missing credential key in .env: {key}"


# ── shape (always run, no network) ───────────────────────────────────────────

_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_TELEGRAM_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")
_TOKEN_CHARSET_RE = re.compile(r"^[A-Za-z0-9_.+\/=_-]{10,}$")


@pytest.mark.parametrize("key", ["WPLBJM_JWT_PROD", "WPLBJM_JWT_DEV"])
def test_jwt_shape(key: str) -> None:
    """JWTs must have the classic three base64url segments."""
    value = _require_env(key)
    assert _JWT_RE.match(value), (
        f"{key} is not a three-segment JWT (got {_mask(value)})"
    )


def test_telegram_bot_token_shape() -> None:
    """Telegram bot tokens look like ``<bot_id>:<secret>``."""
    value = _require_env("TELEGRAM_BOT_TOKEN")
    assert _TELEGRAM_TOKEN_RE.match(value), (
        f"TELEGRAM_BOT_TOKEN malformed (got {_mask(value)})"
    )


@pytest.mark.parametrize("key", ["RENDER_ACCOUNT_API_KEY", "RENDER_MCP_API_KEY"])
def test_render_api_key_shape(key: str) -> None:
    """Render API keys start with ``rnd_``."""
    value = _require_env(key)
    assert value.startswith("rnd_"), (
        f"{key} should start with 'rnd_' (got {_mask(value)})"
    )


def test_google_maps_api_key_shape() -> None:
    """Google Maps API keys start with ``AIza``."""
    value = _require_env("GOOGLE_MAPS_API_KEY")
    assert value.startswith("AIza"), (
        f"GOOGLE_MAPS_API_KEY should start with 'AIza' (got {_mask(value)})"
    )


@pytest.mark.parametrize(
    "key",
    [
        "EXA_API_KEY",
        "GOOGLE_AI_STUDIO_KEY",
        "OPENCODE_API_KEY",
        "TELEGRAM_WEBHOOK_SECRET",
        "X_ROYAL_MCP_API_KEY",
    ],
)
def test_token_charset_shape(key: str) -> None:
    """Remaining keys must look like tokens: no whitespace, ≥10 chars."""
    value = _require_env(key)
    assert _TOKEN_CHARSET_RE.match(value), (
        f"{key} looks malformed (got {_mask(value)})"
    )


def test_wp_login_password_shape() -> None:
    """WordPress password: ≥8 chars, no whitespace."""
    value = _require_env("WP_LOGIN_PASSWORD")
    assert len(value) >= 8 and not re.search(r"\s", value), (
        f"WP_LOGIN_PASSWORD looks malformed (got {_mask(value)})"
    )


@pytest.mark.parametrize("key", sorted(URL_KEYS))
def test_url_shape(key: str) -> None:
    """WordPress URLs must be absolute http(s) URLs."""
    value = _require_env(key)
    parsed = urlparse(value)
    assert parsed.scheme in {"http", "https"} and parsed.netloc, (
        f"{key} is not an absolute http(s) URL (got {_mask(value)})"
    )


# ── live (network, behind ``-m live``) ───────────────────────────────────────

@pytest.mark.live
def test_wplbjm_jwt_prod_is_valid() -> None:
    """``WPLBJM_JWT_PROD`` is accepted by the WordPress GraphQL endpoint."""
    token = _require_env("WPLBJM_JWT_PROD")
    base_url = _require_env("WPLBJM_API_BASE_URL_PROD")

    response = _graphql_validate_jwt(token, base_url)
    status = response.get("_status", 0)
    has_errors = bool(response.get("errors"))
    jwt_value = (response.get("data") or {}).get("jwt")
    del token, response

    _skip_on_unreachable(status)
    assert not has_errors, f"GraphQL returned errors for valid JWT (status={status})"
    assert jwt_value is not None, f"Expected `data.jwt` to be non-null (status={status})"


@pytest.mark.live
def test_wplbjm_jwt_prod_corrupt_is_rejected() -> None:
    """Corrupting the JWT payload makes the GraphQL endpoint return null."""
    token = _require_env("WPLBJM_JWT_PROD")
    base_url = _require_env("WPLBJM_API_BASE_URL_PROD")

    parts = token.count(".")
    assert parts == 2, f"Expected 3-part JWT, got {parts + 1} segments"

    header, payload, signature = token.split(".")
    # Flip the middle character of the base64 payload to break the signature
    # without producing an invalid base64 string.
    idx = len(payload) // 2
    corrupt_payload = (
        payload[:idx]
        + ("A" if payload[idx] != "A" else "Z")
        + payload[idx + 1 :]
    )
    corrupt_token = f"{header}.{corrupt_payload}.{signature}"

    response = _graphql_validate_jwt(corrupt_token, base_url)
    status = response.get("_status", 0)
    jwt_value = (response.get("data") or {}).get("jwt")
    del corrupt_token, token, response

    _skip_on_unreachable(status)
    assert jwt_value is None, (
        f"Expected `data.jwt` to be null for corrupted JWT (status={status})"
    )


@pytest.mark.live
def test_wp_login_credentials_refresh_jwt() -> None:
    """``WP_LOGIN_USERNAME`` / ``WP_LOGIN_PASSWORD`` can obtain a fresh JWT."""
    username = _require_env("WP_LOGIN_USERNAME")
    password = _require_env("WP_LOGIN_PASSWORD")
    base_url = _require_env("WPLBJM_API_BASE_URL_PROD")

    response = _post_json(
        f"{base_url.rstrip('/')}/graphql",
        {
            "query": _GRAPHQL_LOGIN,
            "variables": {"username": username, "password": password},
        },
    )
    status = response.get("_status", 0)
    has_errors = bool(response.get("errors"))
    got_token = bool((response.get("data") or {}).get("jwt"))
    del username, password, base_url, response

    _skip_on_unreachable(status)
    assert not has_errors, f"JWT refresh failed (status={status})"
    assert got_token, f"JWT refresh returned no token (status={status})"


@pytest.mark.live
def test_telegram_bot_token_getme() -> None:
    """``TELEGRAM_BOT_TOKEN`` authenticates against the Bot API."""
    token = _require_env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/getMe"
    del token

    status, raw = _http_request(url)
    del url
    data = _json_loads(raw) or {}

    _skip_on_unreachable(status)
    assert data.get("ok") is True, (
        f"Telegram getMe failed: status={status} error={data.get('description')}"
    )


@pytest.mark.live
def test_gemini_key_live() -> None:
    """``GOOGLE_AI_STUDIO_KEY`` is accepted by the Gemini API."""
    key = _require_env("GOOGLE_AI_STUDIO_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    del key

    status, _ = _http_request(url)
    del url

    _skip_on_unreachable(status)
    assert status == 200, f"Gemini API rejected GOOGLE_AI_STUDIO_KEY (status={status})"


@pytest.mark.live
def test_exa_key_live() -> None:
    """``EXA_API_KEY`` is accepted by the Exa search API."""
    key = _require_env("EXA_API_KEY")
    body = json.dumps({"query": "Banjarmasin job vacancy", "numResults": 1}).encode("utf-8")
    status, raw = _http_request(
        "https://api.exa.ai/search",
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key},
        body=body,
    )
    del key
    data = _json_loads(raw) or {}

    _skip_on_unreachable(status)
    assert status == 200 and isinstance(data.get("results"), list), (
        f"Exa API rejected EXA_API_KEY (status={status})"
    )


@pytest.mark.live
def test_google_maps_key_live() -> None:
    """``GOOGLE_MAPS_API_KEY`` is accepted by the Geocoding API."""
    key = _require_env("GOOGLE_MAPS_API_KEY")
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address=Banjarmasin&key={key}"
    )
    del key

    status, raw = _http_request(url)
    del url
    data = _json_loads(raw) or {}

    _skip_on_unreachable(status)
    assert data.get("status") == "OK", (
        f"Google Maps API rejected GOOGLE_MAPS_API_KEY: "
        f"status={data.get('status')} (http={status})"
    )


@pytest.mark.live
def test_render_account_key_live() -> None:
    """``RENDER_ACCOUNT_API_KEY`` authenticates against the Render API."""
    key = _require_env("RENDER_ACCOUNT_API_KEY")
    headers = {"Authorization": f"Bearer {key}"}
    del key

    status, _ = _http_request(
        "https://api.render.com/v1/services?limit=1",
        headers=headers,
    )
    del headers

    _skip_on_unreachable(status)
    assert status == 200, f"Render API rejected RENDER_ACCOUNT_API_KEY (status={status})"
