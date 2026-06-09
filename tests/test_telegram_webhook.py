from __future__ import annotations

from automation.telegram.webhook import register_telegram_webhook


def test_register_telegram_webhook_includes_secret_token(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://bot.example.test")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "valid_secret_12345")

    def fake_telegram_api(method, payload):
        captured["method"] = method
        captured["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr("automation.telegram.webhook.telegram_api", fake_telegram_api)

    assert register_telegram_webhook() == {"ok": True}
    assert captured == {
        "method": "setWebhook",
        "payload": {
            "url": "https://bot.example.test/telegram/webhook",
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
            "secret_token": "valid_secret_12345",
        },
    }
