from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Mapping

import dotenv
from pydantic import ValidationError

from automation.models import (
    AgentError,
    BotSettings,
    RuntimeEnvironment,
    validation_error_summary,
)


BOT_SETTINGS = BotSettings(
    wordpress_base_url=None,
    jwt=None,
    skill_markdown=None,
    extra_telegram_usernames=[],
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def automation_root() -> Path:
    return project_root()


def load_environment() -> None:
    """Load root and scrapper env files without printing secrets."""

    root = project_root()
    dotenv.load_dotenv(root / ".env", override=False)
    dotenv.load_dotenv(
        Path(__file__).resolve().parent / ".env",
        override=False,
    )


def env_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AgentError(f"Missing required environment variable: {name}")
    return value


def google_ai_studio_key() -> str | None:
    return (
        os.getenv("GOOGLE_AI_STUDIO_KEY")
        or os.getenv("AI_STUDIO_KEY")
        or os.getenv("GEMINI_API_KEY")
    )


def opencode_api_key(provider: str) -> str | None:
    if provider == "zen":
        return (
            os.getenv("OPENCODE_ZEN_KEY")
            or os.getenv("OPENCODE_API_KEY")
            or os.getenv("OPENCODE_KEY")
        )
    if provider == "go":
        return (
            os.getenv("OPENCODE_GO_KEY")
            or os.getenv("OPENCODE_API_KEY")
            or os.getenv("OPENCODE_KEY")
        )
    return None


def opencode_key_label(provider: str) -> str:
    if provider == "zen":
        return "OPENCODE_ZEN_KEY or OPENCODE_API_KEY"
    if provider == "go":
        return "OPENCODE_GO_KEY or OPENCODE_API_KEY"
    return "OPENCODE_API_KEY"


def env_float(
    name: str,
    default: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> float:
    env = environ or os.environ
    raw_value = env.get(name, default)
    try:
        return float(raw_value)
    except ValueError as error:
        raise AgentError(f"{name} must be a number.") from error


def public_url_from_env(environ: Mapping[str, str] | None = None) -> str | None:
    env = environ or os.environ
    explicit_url = env.get("PUBLIC_BASE_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    render_url = env.get("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")

    render_hostname = env.get("RENDER_EXTERNAL_HOSTNAME")
    if render_hostname:
        return f"https://{render_hostname.strip('/')}"

    return None


def validate_skill_configuration(
    *,
    environ: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> None:
    env = environ or os.environ
    project = root or project_root()
    configured_path = env.get("SKILL_MD_PATH")

    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = project / path
        if not path.is_file():
            raise AgentError(f"SKILL_MD_PATH file not found: {path}")
        return

    required = [
        project / ".agents/skills/job-copywriter/SKILL.md",
        project / ".agents/skills/agent-postdraft/SKILL.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise AgentError("Missing bundled skill file(s): " + ", ".join(missing))


def validate_runtime_environment(
    *,
    environ: Mapping[str, str] | None = None,
    require_public_url: bool = True,
    root: Path | None = None,
) -> RuntimeEnvironment:
    env = environ or os.environ
    data = {
        "wordpress_base_url": env.get("WPLBJM_API_BASE_URL_PROD", ""),
        "wordpress_domain": env.get("WPLBJM_WORDPRESS_DOMAIN") or None,
        "wordpress_jwt": env.get("WPLBJM_JWT_PROD", ""),
        "telegram_username": env.get("TELEGRAM_USERNAME", ""),
        "telegram_bot_token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_webhook_secret": env.get("TELEGRAM_WEBHOOK_SECRET", ""),
        "public_base_url": public_url_from_env(env),
        "ai_provider": (env.get("AI_PROVIDER") or "opencode").lower(),
        "opencode_model_chain": env.get(
            "OPENCODE_MODEL_CHAIN",
            "zen:mimo-v2.5-free:chat,go:minimax-m3:messages,go:mimo-v2.5:chat",
        ),
        "opencode_api_key": env.get("OPENCODE_API_KEY") or env.get("OPENCODE_KEY") or None,
        "opencode_zen_key": env.get("OPENCODE_ZEN_KEY") or None,
        "opencode_go_key": env.get("OPENCODE_GO_KEY") or None,
        "google_ai_studio_key": env.get("GOOGLE_AI_STUDIO_KEY")
        or env.get("AI_STUDIO_KEY")
        or None,
        "gemini_api_key": env.get("GEMINI_API_KEY") or None,
        "skill_md_path": env.get("SKILL_MD_PATH") or None,
        "media_group_delay_seconds": env_float(
            "TELEGRAM_MEDIA_GROUP_DELAY_SECONDS",
            "2",
            environ=env,
        ),
        "bulk_command_ttl_seconds": env_float(
            "TELEGRAM_BULK_COMMAND_TTL_SECONDS",
            "90",
            environ=env,
        ),
    }

    errors: list[str] = []
    try:
        settings = RuntimeEnvironment.model_validate(data)
    except ValidationError as error:
        errors.append(validation_error_summary(error))
        settings = None

    if require_public_url and not data["public_base_url"]:
        errors.append(
            "PUBLIC_BASE_URL, RENDER_EXTERNAL_URL, or "
            "RENDER_EXTERNAL_HOSTNAME is required for Telegram webhook setup",
        )

    try:
        validate_skill_configuration(environ=env, root=root)
    except AgentError as error:
        errors.append(str(error))

    if errors:
        raise AgentError("Invalid runtime environment: " + " | ".join(errors))

    if settings is None:
        raise AgentError("Invalid runtime environment.")
    return settings
