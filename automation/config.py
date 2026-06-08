from __future__ import annotations

import os
from pathlib import Path

import dotenv

from automation.models import AgentError, BotSettings


BOT_SETTINGS = BotSettings(
    wordpress_base_url=None,
    jwt=None,
    skill_markdown=None,
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def automation_root() -> Path:
    return project_root()


def load_environment() -> None:
    """Load root and scrapper env files without printing secrets."""

    root = project_root()
    dotenv.load_dotenv(root / ".env", override=False)
    dotenv.load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def env_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AgentError(f"Missing required environment variable: {name}")
    return value


def google_ai_studio_key() -> str | None:
    return os.getenv("GOOGLE_AI_STUDIO_KEY") or os.getenv("AI_STUDIO_KEY") or os.getenv("GEMINI_API_KEY")


def opencode_api_key(provider: str) -> str | None:
    if provider == "zen":
        return os.getenv("OPENCODE_ZEN_KEY") or os.getenv("OPENCODE_API_KEY") or os.getenv("OPENCODE_KEY")
    if provider == "go":
        return os.getenv("OPENCODE_GO_KEY") or os.getenv("OPENCODE_API_KEY") or os.getenv("OPENCODE_KEY")
    return None


def opencode_key_label(provider: str) -> str:
    if provider == "zen":
        return "OPENCODE_ZEN_KEY or OPENCODE_API_KEY"
    if provider == "go":
        return "OPENCODE_GO_KEY or OPENCODE_API_KEY"
    return "OPENCODE_API_KEY"
