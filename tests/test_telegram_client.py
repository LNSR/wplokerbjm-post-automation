from __future__ import annotations

from automation.telegram.client import telegram_api


class FakeResponse:
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok": true, "result": true}'


def test_telegram_api_uses_bot_token(monkeypatch) -> None:
    captured = {}
    token = "123456789:abcdefghijklmnopqrstuvwxyzABCDE"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("automation.telegram.client.urlopen", fake_urlopen)

    assert telegram_api("getMe") == {"ok": True, "result": True}
    assert captured == {
        "url": f"https://api.telegram.org/bot{token}/getMe",
        "timeout": 30,
    }
