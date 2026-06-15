from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation import main as main_module
from automation.models import NormalizedPayload, WordpressConfig


def apply_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_check_config_cli_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    valid_env: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    apply_env(monkeypatch, valid_env)

    exit_code = main_module.main(["--check-config"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["ai_provider"] == "gemini"
    assert output["public_base_url"] == "https://bot.example.test"


def test_check_config_cli_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SKILL_MD_PATH", "/missing/SKILL.md")

    exit_code = main_module.main(["--check-config"])

    output = json.loads(capsys.readouterr().err)
    assert exit_code == 1
    assert output["ok"] is False
    assert "Invalid runtime environment" in output["error"]


def test_build_result_preview_does_not_post(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    payload = NormalizedPayload(
        title="Admin | Example | AI posted draft",
        status_pekerjaan=0,
    )

    monkeypatch.setattr(main_module, "load_environment", lambda: None)
    monkeypatch.setattr(
        main_module,
        "wordpress_config",
        lambda: WordpressConfig(base_url="https://wp.test", jwt="aaa.bbb.ccc"),
    )
    monkeypatch.setattr(main_module, "try_ingest_options", lambda config: ({}, None))
    monkeypatch.setattr(
        main_module,
        "extract_payload_from_image",
        lambda image_path, options, model=None, custom_instruction=None, **kwargs: (
            {"title": "Admin | Example"},
            "gemini:gemini-2.5-flash",
            {"exa_used": False, "exa_count": 0, "qr_redirects": []},
        ),
    )
    monkeypatch.setattr(
        main_module,
        "normalize_payload",
        lambda extracted, options, source=None: (payload, []),
    )

    def unexpected_post(*args, **kwargs):
        raise AssertionError("preview mode must not post")

    monkeypatch.setattr(main_module, "post_draft", unexpected_post)

    result = main_module.build_result(image, post=False, model=None)

    assert result.mode == "mock_preview"
    assert result.wordpress is None


def test_build_result_post_calls_wordpress_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    payload = NormalizedPayload(
        title="Admin | Example | AI posted draft",
        status_pekerjaan=0,
    )
    calls: list[Path] = []

    monkeypatch.setattr(main_module, "load_environment", lambda: None)
    monkeypatch.setattr(
        main_module,
        "wordpress_config",
        lambda: WordpressConfig(base_url="https://wp.test", jwt="aaa.bbb.ccc"),
    )
    monkeypatch.setattr(main_module, "try_ingest_options", lambda config: ({}, None))
    monkeypatch.setattr(
        main_module,
        "extract_payload_from_image",
        lambda image_path, options, model=None, custom_instruction=None, **kwargs: (
            {"title": "Admin | Example"},
            "gemini:gemini-2.5-flash",
            {"exa_used": False, "exa_count": 0, "qr_redirects": []},
        ),
    )
    monkeypatch.setattr(
        main_module,
        "normalize_payload",
        lambda extracted, options, source=None: (payload, []),
    )

    def fake_post(config, normalized_payload, image_path):
        calls.append(image_path)
        return 201, {"id": 42, "edit_url": "https://wp.test/edit/42"}

    monkeypatch.setattr(main_module, "post_draft", fake_post)

    result = main_module.build_result(image, post=True, model=None)

    assert calls == [image]
    assert result.mode == "post_prod"
    assert result.http_status == 201
    assert result.wordpress == {
        "id": 42,
        "edit_url": "https://wp.test/edit/42",
    }


def test_build_result_forwards_custom_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    captured: list[str | None] = []
    payload = NormalizedPayload(
        title="Admin | Example | AI posted draft",
        status_pekerjaan=0,
    )

    monkeypatch.setattr(main_module, "load_environment", lambda: None)
    monkeypatch.setattr(
        main_module,
        "wordpress_config",
        lambda: WordpressConfig(
            base_url="https://wp.test",
            jwt="aaa.bbb.ccc",
        ),
    )
    monkeypatch.setattr(main_module, "try_ingest_options", lambda config: ({}, None))

    def fake_extract(
        image_path: Path,
        options: dict[str, object],
        *,
        model: str | None,
        custom_instruction: str | None,
        **kwargs: object,
    ) -> tuple[dict[str, str], str, dict[str, object]]:
        captured.append(custom_instruction)
        return {"title": "Admin | Example"}, "gemini:gemini-2.5-flash", {"exa_used": False, "exa_count": 0, "qr_redirects": []}

    monkeypatch.setattr(
        main_module,
        "extract_payload_from_image",
        fake_extract,
    )
    monkeypatch.setattr(
        main_module,
        "normalize_payload",
        lambda extracted, options, source=None: (payload, []),
    )

    main_module.build_result(
        image,
        post=False,
        model=None,
        custom_instruction="Prefer the QR application URL.",
    )

    assert captured == ["Prefer the QR application URL."]
