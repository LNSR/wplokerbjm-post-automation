from __future__ import annotations

import http.server
import json
import os
import sys
from typing import Any

from automation.config import load_environment
from automation.models import AgentError
from automation.telegram.handlers import handle_telegram_update
from automation.telegram.webhook import register_telegram_webhook, telegram_webhook_url, public_base_url


class TelegramWebhookHandler(http.server.BaseHTTPRequestHandler):
    server_version = "WPLokerBJMAgent/1.0"

    def do_GET(self) -> None:
        if self.path in {"/", "/healthz"}:
            self.send_json(
                200,
                {
                    "ok": True,
                    "service": "wplokerbjm-post-automation",
                    "public_url": public_base_url(),
                    "telegram_webhook_url": telegram_webhook_url(),
                },
            )
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/telegram/webhook":
            self.send_json(404, {"ok": False, "error": "not_found"})
            return

        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            handle_telegram_update(update)
            self.send_json(200, {"ok": True})
        except Exception as error:
            self.send_json(200, {"ok": False, "error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_bot() -> None:
    load_environment()
    port = int(os.getenv("PORT", "8000"))

    webhook_url = telegram_webhook_url()
    if webhook_url:
        try:
            register_telegram_webhook()
            print(f"Telegram webhook registered: {webhook_url}", flush=True)
        except AgentError as error:
            print(f"Telegram webhook registration failed: {error}", file=sys.stderr, flush=True)
    else:
        print(
            "Telegram webhook registration skipped: no PUBLIC_BASE_URL or Render external URL detected.",
            flush=True,
        )

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), TelegramWebhookHandler)
    print(f"Telegram webhook server listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
