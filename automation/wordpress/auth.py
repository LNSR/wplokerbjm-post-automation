from __future__ import annotations

import http.cookies
import json
import os
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.config import BOT_SETTINGS, env_value
from automation.models import AgentError, WordpressConfig
from automation.wordpress.client import parse_json_response


def wordpress_config() -> WordpressConfig:
    return WordpressConfig(
        base_url=(BOT_SETTINGS.wordpress_base_url or env_value("WPLBJM_API_BASE_URL_PROD")).rstrip("/"),
        jwt=BOT_SETTINGS.jwt or env_value("WPLBJM_JWT_PROD"),
    )


def graphql_base_url() -> str:
    return (BOT_SETTINGS.wordpress_base_url or os.getenv("WPLBJM_WORDPRESS_DOMAIN") or env_value("WPLBJM_API_BASE_URL_PROD")).rstrip("/")


def request_graphql_jwt(username: str, password: str) -> str:
    mutation = """
mutation GetJWT($username: String, $password: String, $token: String) {
  jwt(username: $username, password: $password, token: $token)
}
""".strip()
    body = json.dumps(
        {
            "query": mutation,
            "variables": {
                "username": username,
                "password": password,
            },
        }
    ).encode("utf-8")
    request = Request(
        f"{graphql_base_url()}/graphql",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            token = jwt_from_headers(response.headers)
            data = parse_json_response(response_body)
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        data = parse_json_response(response_body)
        message = data.get("message") or data.get("errors") or "JWT GraphQL request failed."
        raise AgentError(f"JWT refresh failed ({error.code}): {message}") from error
    except URLError as error:
        raise AgentError(f"JWT refresh failed: {error.reason}") from error

    if token:
        return token

    errors = data.get("errors")
    if errors:
        raise AgentError(f"JWT refresh failed: {errors}")
    raise AgentError("JWT refresh failed: GraphQL did not set jwt-token cookie.")


def jwt_from_headers(headers: Any) -> str | None:
    set_cookies = []
    if hasattr(headers, "get_all"):
        set_cookies = headers.get_all("Set-Cookie") or []
    elif headers.get("Set-Cookie"):
        set_cookies = [headers.get("Set-Cookie")]

    for header in set_cookies:
        cookie = http.cookies.SimpleCookie()
        cookie.load(header)
        morsel = cookie.get("jwt-token")
        if morsel and morsel.value:
            return morsel.value
    return None
