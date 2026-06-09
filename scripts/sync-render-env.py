#!/usr/bin/env python3
"""Sync allowed env vars to a Render service via per-key API calls."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ALLOWLIST = frozenset(
    {
        # From GitHub secrets:
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_USERNAME",
        "TELEGRAM_WEBHOOK_SECRET",
        "WPLBJM_API_BASE_URL_PROD",
        "WPLBJM_JWT_PROD",
        "WP_LOGIN_USERNAME",
        "WP_LOGIN_PASSWORD",
        "EXA_API_KEY",
        "GOOGLE_AI_STUDIO_KEY",
        "OPENCODE_API_KEY",
        # Inline config (non-sensitive, set in workflow env):
        "AI_PROVIDER",
        "OPENCODE_MODEL_CHAIN",
        "EXA_SEARCH_TYPE",
        "DISABLE_WEB_ENRICHMENT",
        "SKILL_MD_PATH",
        "TELEGRAM_MEDIA_GROUP_DELAY_SECONDS",
        "TELEGRAM_BULK_COMMAND_TTL_SECONDS",
        "PUBLIC_BASE_URL",
    }
)

RENDER_API = "https://api.render.com/v1"


def _render_request(url: str, api_key: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, str]:
    """Make an HTTP request to the Render API. Returns (status_code, response_body)."""
    data: bytes | None = json.dumps(body).encode("utf-8") if body else None
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync env vars to Render service")
    parser.add_argument("--dry-run", action="store_true", help="Validate but do not call Render API")
    args = parser.parse_args(argv)

    api_key = os.environ.get("RENDER_ACCOUNT_API_KEY", "")
    sid = os.environ.get("RENDER_SERVICE_ID", "")
    if not api_key or not sid:
        print("ERROR: RENDER_ACCOUNT_API_KEY and RENDER_SERVICE_ID must be set", file=sys.stderr)
        return 1

    # Pre-sync validation: verify API key and service ID are valid
    status, _body = _render_request(f"{RENDER_API}/services/{sid}", api_key)
    if status != 200:
        error = "auth failed" if status in {401, 403} else f"HTTP {status}"
        print(f"ERROR: Render API {error} — check RENDER_ACCOUNT_API_KEY and RENDER_SERVICE_ID", file=sys.stderr)
        return 1
    print("[OK] Pre-sync auth validation — Render API reachable")

    errors = 0
    for key in sorted(ALLOWLIST):
        value = os.environ.get(key, "")
        if args.dry_run:
            print(f"[DRY-RUN] would sync {key}")
            continue

        if value == "":
            print(f"[SKIP] {key} (empty value)")
            continue

        status, _ = _render_request(
            f"{RENDER_API}/services/{sid}/env-vars/{key}",
            api_key,
            method="PUT",
            body={"value": value},
        )
        if status == 200:
            print(f"[OK] {key}")
        else:
            print(f"[FAIL] {key} (HTTP {status})", file=sys.stderr)
            errors += 1

    if errors:
        print(f"ERROR: {errors} env var sync(s) failed", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
