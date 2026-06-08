from __future__ import annotations

import sys
from email.message import Message
from pathlib import Path

from automation.ai.qr import decode_qr_codes, qr_context_text
from automation.skills import load_skill_markdown
from automation.telegram.webhook import public_base_url, telegram_webhook_url
from automation.web.exa import exa_context_text, parse_exa_result
from automation.wordpress.auth import jwt_from_headers


def test_qr_decoder_fails_open_without_optional_modules(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setitem(sys.modules, "cv2", None)
    image = tmp_path / "image.jpg"
    image.write_bytes(b"not really an image")

    assert decode_qr_codes(image) == []
    assert qr_context_text(image) == ""


def test_exa_context_without_key_is_empty() -> None:
    assert exa_context_text("PT Example Banjarmasin") == ""


def test_parse_exa_result_accepts_page_shape() -> None:
    result = parse_exa_result(
        {
            "page": {
                "title": "Example Company",
                "url": "https://example.test",
            },
            "highlights": ["Alamat Banjarmasin"],
        }
    )

    assert result is not None
    assert result.title == "Example Company"
    assert result.url == "https://example.test"
    assert result.text == "Alamat Banjarmasin"


def test_jwt_from_headers_extracts_cookie() -> None:
    headers = Message()
    headers.add_header("Set-Cookie", "jwt-token=aaa.bbb.ccc; Path=/; HttpOnly")

    assert jwt_from_headers(headers) == "aaa.bbb.ccc"


def test_public_base_url_uses_render_hostname(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "bot.onrender.com")

    assert public_base_url() == "https://bot.onrender.com"
    assert telegram_webhook_url() == "https://bot.onrender.com/telegram/webhook"


def test_load_skill_markdown_from_configured_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("# Skill\nInstructions", encoding="utf-8")
    monkeypatch.setenv("SKILL_MD_PATH", str(skill))

    content, source = load_skill_markdown()

    assert content == "# Skill\nInstructions"
    assert source == str(skill)
