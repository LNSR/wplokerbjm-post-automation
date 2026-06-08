from __future__ import annotations

from automation.ai.prompt import build_prompt


def test_build_prompt_includes_guarded_custom_instruction(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "automation.ai.prompt.load_skill_markdown",
        lambda: ("Use visible flyer facts.", "test"),
    )

    prompt = build_prompt(
        {},
        "Prioritize the decoded QR application link.",
    )

    assert "Prioritize the decoded QR application link." in prompt
    assert "strict JSON contract" in prompt
    assert "must never add unsupported fields or invented facts" in prompt
