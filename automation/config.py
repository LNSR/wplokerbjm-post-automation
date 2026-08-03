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
    return os.getenv("GOOGLE_AI_STUDIO_KEY")


def opencode_api_key(provider: str) -> str | None:
    return os.getenv("OPENCODE_API_KEY")


def opencode_key_label(provider: str) -> str:
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
    """Validate runtime environment using pydantic-settings.
    
    When environ is provided, use it directly for validation.
    Otherwise, BaseSettings will read from os.environ automatically.
    """
    env = environ or os.environ
    
    errors: list[str] = []
    settings = None
    
    try:
        if environ is not None:
            # For testing: temporarily override os.environ
            original_environ = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(environ)
                settings = RuntimeEnvironment() 
            finally:
                # Restore original environment
                os.environ.clear()
                os.environ.update(original_environ)
        else:
            # Production: read from os.environ directly
            settings = RuntimeEnvironment() 
    except ValidationError as error:
        errors.append(validation_error_summary(error))

    if require_public_url and (settings is None or not settings.public_base_url):
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
