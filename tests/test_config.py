from __future__ import annotations

from pathlib import Path

import pytest

from automation.config import (
    env_value,
    public_url_from_env,
    validate_runtime_environment,
)
from automation.models import AgentError


def test_env_value_missing_raises_agent_error() -> None:
    with pytest.raises(AgentError, match="Missing required environment variable"):
        env_value("MISSING_FOR_TEST")


def test_public_url_prefers_explicit_url() -> None:
    env = {
        "PUBLIC_BASE_URL": "https://custom.example.test/",
        "RENDER_EXTERNAL_URL": "https://render.example.test",
    }

    assert public_url_from_env(env) == "https://custom.example.test"


def test_public_url_uses_render_hostname() -> None:
    assert public_url_from_env({"RENDER_EXTERNAL_HOSTNAME": "app.onrender.com"}) == (
        "https://app.onrender.com"
    )


def test_validate_runtime_environment_accepts_valid_env(valid_env: dict[str, str]) -> None:
    settings = validate_runtime_environment(environ=valid_env, root=Path.cwd())

    assert settings.ai_provider == "opencode"
    assert settings.telegram_username == "maulana_test"
    assert settings.public_base_url == "https://bot.example.test"


def test_validate_runtime_environment_requires_public_url(
    valid_env: dict[str, str],
) -> None:
    valid_env.pop("PUBLIC_BASE_URL")

    with pytest.raises(AgentError, match="PUBLIC_BASE_URL"):
        validate_runtime_environment(environ=valid_env, root=Path.cwd())


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("WPLBJM_API_BASE_URL_PROD", "localhost", "wordpress_base_url"),
        ("WPLBJM_JWT_PROD", "not-a-jwt", "wordpress_jwt"),
        ("TELEGRAM_USERNAME", "bad user", "telegram_username"),
        ("TELEGRAM_BOT_TOKEN", "bad-token", "telegram_bot_token"),
        ("TELEGRAM_WEBHOOK_SECRET", "too-short", "telegram_webhook_secret"),
        ("OPENCODE_MODEL_CHAIN", "zen:model:bad", "opencode_model_chain"),
        ("TELEGRAM_BULK_COMMAND_TTL_SECONDS", "0", "bulk_command_ttl_seconds"),
    ],
)
def test_validate_runtime_environment_rejects_invalid_values(
    valid_env: dict[str, str],
    key: str,
    value: str,
    message: str,
) -> None:
    valid_env[key] = value

    with pytest.raises(AgentError, match=message):
        validate_runtime_environment(environ=valid_env, root=Path.cwd())


def test_validate_runtime_environment_requires_ai_key(
    valid_env: dict[str, str],
) -> None:
    valid_env.pop("OPENCODE_API_KEY")

    with pytest.raises(AgentError, match="OpenCode requires"):
        validate_runtime_environment(environ=valid_env, root=Path.cwd())


def test_validate_runtime_environment_requires_existing_skill_path(
    valid_env: dict[str, str],
    tmp_path: Path,
) -> None:
    valid_env["SKILL_MD_PATH"] = str(tmp_path / "missing.md")

    with pytest.raises(AgentError, match="SKILL_MD_PATH file not found"):
        validate_runtime_environment(environ=valid_env, root=Path.cwd())
