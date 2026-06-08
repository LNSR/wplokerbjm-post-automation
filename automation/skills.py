from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from automation.config import BOT_SETTINGS, automation_root
from automation.models import AgentError
from automation.telegram.files import download_telegram_file, skill_document_file_id


def bundled_skill_paths() -> list[Path]:
    root = automation_root()
    return [
        root / ".agents/skills/job-copywriter/SKILL.md",
        root / ".agents/skills/agent-postdraft/SKILL.md",
    ]


def load_skill_markdown() -> tuple[str, str]:
    if BOT_SETTINGS.skill_markdown:
        return BOT_SETTINGS.skill_markdown, "Telegram upload"

    configured_path = os.getenv("SKILL_MD_PATH")
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = automation_root() / path
        if not path.is_file():
            raise AgentError(f"SKILL_MD_PATH file not found: {path}")
        return path.read_text(encoding="utf-8"), str(path)

    parts: list[str] = []
    paths = bundled_skill_paths()
    for path in paths:
        if not path.is_file():
            raise AgentError(f"Bundled skill file not found: {path}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts), "bundled repository skills"


def read_uploaded_skill(message: dict[str, Any]) -> str:
    file_id = skill_document_file_id(message)
    if not file_id:
        raise AgentError("Attach a Markdown SKILL.md file with the /set_skill caption.")

    path = download_telegram_file(file_id)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as error:
        raise AgentError("Uploaded SKILL.md must be UTF-8 text.") from error
    finally:
        path.unlink(missing_ok=True)

    if not content:
        raise AgentError("Uploaded SKILL.md is empty.")
    return content
