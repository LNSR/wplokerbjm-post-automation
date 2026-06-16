"""Smoke-test WPLBJM_JWT_PROD validity via GraphQL.

These tests talk to the live WordPress GraphQL endpoint — they are gated behind
the ``live`` marker (``pytest -m live``) and skip gracefully when the .env is
missing or the site is unreachable.
"""

from __future__ import annotations

import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from dotenv import dotenv_values


# ── helpers ──────────────────────────────────────────────────────────────────

_GRAPHQL_VALIDATE_JWT = """
mutation GetJWT($token: String) {
  jwt(token: $token)
}
""".strip()


def _env_file() -> dict[str, str | None]:
    """Load ``.env`` from the repo root as a plain dict."""
    root = os.environ.get("PYTEST_CURRENT_TEST", "")
    # Walk up from tests/ to project root
    trial = os.getcwd()
    for _ in range(4):
        path = os.path.join(trial, ".env")
        if os.path.isfile(path):
            return dict(dotenv_values(path))
        trial = os.path.dirname(trial)
    return {}


_ENV = _env_file()


def _graphql_validate_jwt(token: str, base_url: str) -> dict:
    """POST a GraphQL mutation that only carries ``token`` and return the
    parsed response dict.  Mirrors ``request_graphql_jwt()`` from
    ``automation.wordpress.auth`` but foregoes ``username`` / ``password``.
    """
    body = json.dumps({
        "query": _GRAPHQL_VALIDATE_JWT,
        "variables": {"token": token},
    }).encode("utf-8")

    url = f"{base_url.rstrip('/')}/graphql"
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )

    ctx = ssl._create_unverified_context()  # allow staging / self-signed certs

    try:
        with urlopen(request, context=ctx, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except URLError as exc:
        pytest.skip(f"WordPress site unreachable: {exc.reason}")


def _require_env(key: str) -> str:
    """Return the .env value for *key* or call ``pytest.skip``."""
    value = _ENV.get(key)
    if not value:
        pytest.skip(f"Missing .env key: {key}")
    return value


# ── positive case ────────────────────────────────────────────────────────────

@pytest.mark.live
def test_wplbjm_jwt_prod_is_valid() -> None:
    """``WPLBJM_JWT_PROD`` is accepted by the WordPress GraphQL endpoint."""
    token = _require_env("WPLBJM_JWT_PROD")
    base_url = _require_env("WPLBJM_API_BASE_URL_PROD")

    response = _graphql_validate_jwt(token, base_url)

    assert "errors" not in response, (
        f"GraphQL returned errors for valid JWT:\n{json.dumps(response, indent=2)}"
    )
    assert response.get("data", {}).get("jwt") is not None, (
        "Expected `data.jwt` to be a non-null token string, got:\n"
        f"{json.dumps(response, indent=2)}"
    )


# ── negative case ────────────────────────────────────────────────────────────

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

    jwt_value = response.get("data", {}).get("jwt")
    assert jwt_value is None, (
        "Expected `data.jwt` to be null for corrupted JWT, got:\n"
        f"{json.dumps(response, indent=2)}"
    )
