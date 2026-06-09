from __future__ import annotations

import http.client
import http.server
import json
import threading
from collections.abc import Iterator

import pytest

from automation.models import AgentError
from automation.telegram.server import TelegramWebhookHandler, webhook_error_payload


class ThreadingTestServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


@pytest.fixture
def webhook_server() -> Iterator[tuple[str, int]]:
    server = ThreadingTestServer(("127.0.0.1", 0), TelegramWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request_json(
    webhook_server: tuple[str, int],
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    host, port = webhook_server
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        response_body = response.read().decode("utf-8")
        return response.status, json.loads(response_body)
    finally:
        conn.close()


def test_webhook_error_payload_does_not_echo_agent_error_message() -> None:
    payload = webhook_error_payload(
        AgentError("secret token 123456:DO_NOT_LEAK should not be echoed"),
    )

    assert payload == {"ok": False, "error": "request_failed"}


def test_webhook_error_payload_hides_unexpected_exception_details() -> None:
    payload = webhook_error_payload(
        RuntimeError("jwt=aaa.bbb.ccc should not leak"),
    )

    assert payload == {"ok": False, "error": "internal_error"}


@pytest.mark.parametrize("path", ["/", "/healthz"])
def test_health_endpoints_return_webhook_metadata(
    monkeypatch: pytest.MonkeyPatch,
    webhook_server: tuple[str, int],
    path: str,
) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://bot.example.test/")

    status, payload = request_json(webhook_server, "GET", path)

    assert status == 200
    assert payload == {
        "ok": True,
        "service": "wplokerbjm-post-automation",
        "public_url": "https://bot.example.test",
        "telegram_webhook_url": "https://bot.example.test/telegram/webhook",
    }


def test_unknown_endpoint_returns_not_found(webhook_server: tuple[str, int]) -> None:
    status, payload = request_json(webhook_server, "GET", "/missing")

    assert status == 404
    assert payload == {"ok": False, "error": "not_found"}


def test_non_webhook_post_returns_not_found(webhook_server: tuple[str, int]) -> None:
    status, payload = request_json(webhook_server, "POST", "/missing", payload={})

    assert status == 404
    assert payload == {"ok": False, "error": "not_found"}


def test_webhook_rejects_invalid_secret_header(
    monkeypatch: pytest.MonkeyPatch,
    webhook_server: tuple[str, int],
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "valid_secret_12345")

    status, payload = request_json(
        webhook_server,
        "POST",
        "/telegram/webhook",
        payload={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
    )

    assert status == 403
    assert payload == {"ok": False, "error": "forbidden"}


def test_webhook_accepts_valid_secret_header(
    monkeypatch: pytest.MonkeyPatch,
    webhook_server: tuple[str, int],
) -> None:
    handled = []
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "valid_secret_12345")

    def fake_handle_telegram_update(update: dict[str, object]) -> None:
        handled.append(update)

    monkeypatch.setattr(
        "automation.telegram.server.handle_telegram_update",
        fake_handle_telegram_update,
    )

    status, payload = request_json(
        webhook_server,
        "POST",
        "/telegram/webhook",
        payload={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "valid_secret_12345"},
    )

    assert status == 200
    assert payload == {"ok": True}
    assert handled == [{"update_id": 1}]


def test_webhook_returns_sanitized_handler_error(
    monkeypatch: pytest.MonkeyPatch,
    webhook_server: tuple[str, int],
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "valid_secret_12345")

    def fake_handle_telegram_update(update: dict[str, object]) -> None:
        raise AgentError("telegram token should not leak")

    monkeypatch.setattr(
        "automation.telegram.server.handle_telegram_update",
        fake_handle_telegram_update,
    )

    status, payload = request_json(
        webhook_server,
        "POST",
        "/telegram/webhook",
        payload={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "valid_secret_12345"},
    )

    assert status == 200
    assert payload == {"ok": False, "error": "request_failed"}
