from __future__ import annotations

from pathlib import Path

import pytest

from automation.config import BOT_SETTINGS


ENV_KEYS = {
    "AI_PROVIDER",
    "DISABLE_WEB_ENRICHMENT",
    "EXA_API_KEY",
    "EXA_SEARCH_TYPE",
    "GOOGLE_AI_STUDIO_KEY",
    "OPENCODE_API_KEY",
    "OPENCODE_COPYWRITER_CHAIN",
    "OPENCODE_MODEL_CHAIN",
    "PUBLIC_BASE_URL",
    "RENDER_EXTERNAL_HOSTNAME",
    "RENDER_EXTERNAL_URL",
    "SKILL_MD_PATH",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BULK_COMMAND_TTL_SECONDS",
    "TELEGRAM_MEDIA_GROUP_DELAY_SECONDS",
    "TELEGRAM_USERNAME",
    "TELEGRAM_WEBHOOK_SECRET",
    "WPLBJM_API_BASE_URL_PROD",
    "WPLBJM_JWT_PROD",
    "WP_LOGIN_PASSWORD",
    "WP_LOGIN_USERNAME",
}


@pytest.fixture(autouse=True)
def clean_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    BOT_SETTINGS.wordpress_base_url = None
    BOT_SETTINGS.jwt = None
    BOT_SETTINGS.skill_markdown = None
    BOT_SETTINGS.extra_telegram_usernames = []


@pytest.fixture
def valid_env(tmp_path: Path) -> dict[str, str]:
    skill = tmp_path / "SKILL.md"
    skill.write_text("# Test Skill\n", encoding="utf-8")
    return {
        "WPLBJM_API_BASE_URL_PROD": "https://wp.example.test",
        "WPLBJM_JWT_PROD": "eyJ0eXAiOiJKV1Qi.e30.signaturevalue",
        "TELEGRAM_USERNAME": "maulana_test",
        "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
        "TELEGRAM_WEBHOOK_SECRET": "valid_secret_12345",
        "PUBLIC_BASE_URL": "https://bot.example.test",
        "AI_PROVIDER": "gemini",
        "OPENCODE_MODEL_CHAIN": "zen:mimo-v2.5-free:chat,go:kimi-k2.5:chat,go:minimax-m3:messages",
        "OPENCODE_COPYWRITER_CHAIN": "zen:mimo-v2.5-free:chat",
        "OPENCODE_API_KEY": "opencode-test-key-123456",
        "GOOGLE_AI_STUDIO_KEY": "gemini-test-key-123456",
        "TELEGRAM_MEDIA_GROUP_DELAY_SECONDS": "2",
        "TELEGRAM_BULK_COMMAND_TTL_SECONDS": "90",
        "SKILL_MD_PATH": str(skill),
    }
