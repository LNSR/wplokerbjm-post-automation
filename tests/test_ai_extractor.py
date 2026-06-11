from __future__ import annotations

from pathlib import Path

import pytest

from automation.ai import extractor
from automation.ai.extractor import (
    sanitize_payload_against_evidence,
    validate_identity_evidence,
)
from automation.models import AgentError, OpenCodeAttempt


def test_identity_evidence_accepts_visible_role_and_company() -> None:
    validate_identity_evidence(
        {
            "title": "Medical Representative | Dexa Group",
            "nama_perusahaan": "Dexa Group",
        },
        "WE ARE HIRING Medical Representative (MR) dexa group Banjarmasin",
    )


def test_identity_evidence_rejects_cross_request_payload() -> None:
    with pytest.raises(AgentError, match="model title does not match"):
        validate_identity_evidence(
            {
                "title": "Front Desk Supervisor",
                "nama_perusahaan": "Udara Bali",
            },
            "SALES TO SAMPIT BEHAESTEX Kualifikasi pengalaman sales",
        )


def test_identity_evidence_rejects_wrong_company() -> None:
    with pytest.raises(AgentError, match="model company does not match"):
        validate_identity_evidence(
            {
                "title": "Medical Representative",
                "nama_perusahaan": "PT Garam",
            },
            "Medical Representative (MR) dexa group Banjarmasin",
        )


def test_extractor_runs_two_stage_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    seen_raw: dict[str, object] | None = None

    def fake_raw(
        image_path: Path,
        options: dict[str, object],
        *,
        model: str | None = None,
        custom_instruction: str | None = None,
    ) -> tuple[dict[str, object], str]:
        return {"title": "Sales to Sampit", "company": "Example"}, "opencode:go/kimi-k2.6"

    def fake_copywriter(
        raw_facts: dict[str, object],
        options: dict[str, object],
        *,
        custom_instruction: str | None = None,
    ) -> tuple[dict[str, str], str]:
        nonlocal seen_raw
        seen_raw = raw_facts
        return {"title": "Sales to Sampit", "nama_perusahaan": "Example"}, "zen/mimo-v2.5-free"

    monkeypatch.setattr(extractor, "extract_raw_facts_from_image", fake_raw)
    monkeypatch.setattr(extractor, "format_payload_with_copywriter", fake_copywriter)

    payload, resolved = extractor.extract_payload_from_image(image, {})

    assert payload == {"title": "Sales to Sampit", "nama_perusahaan": "Example"}
    assert resolved == "opencode:go/kimi-k2.6 → copywriter:zen/mimo-v2.5-free"
    assert seen_raw == {"title": "Sales to Sampit", "company": "Example"}


def test_raw_extractor_uses_opencode_direct_image_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    direct_called = False

    monkeypatch.setenv("AI_PROVIDER", "opencode")

    def fake_direct(
        image_path: Path,
        options: dict[str, object],
        attempt: OpenCodeAttempt,
        *,
        evidence_text: str | None = None,
        custom_instruction: str | None = None,
    ) -> dict[str, str]:
        nonlocal direct_called
        direct_called = True
        return {"title": "Sales to Sampit"}

    monkeypatch.setattr(
        extractor,
        "opencode_attempts",
        lambda model=None: [
            OpenCodeAttempt(
                provider="zen",
                model="vision-model",
                endpoint_style="chat",
            )
        ],
    )
    monkeypatch.setattr(
        extractor,
        "extract_facts_with_opencode_direct_image",
        fake_direct,
    )

    payload, resolved = extractor.extract_raw_facts_from_image(image, {})

    assert payload == {"title": "Sales to Sampit"}
    assert resolved == "opencode:zen/vision-model"
    assert direct_called is True


def test_gemini_failure_falls_back_to_ordered_opencode_direct_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(
        extractor,
        "extract_facts_with_gemini",
        lambda *args, **kwargs: (_ for _ in ()).throw(AgentError("rate limited")),
    )
    monkeypatch.setattr(
        extractor,
        "opencode_attempts",
        lambda model=None: [
            OpenCodeAttempt(
                provider="zen",
                model="mimo-v2.5-free",
                endpoint_style="chat",
            )
        ],
    )

    def fake_direct(
        image_path: Path,
        options: dict[str, object],
        attempt: OpenCodeAttempt,
        *,
        evidence_text: str | None = None,
        custom_instruction: str | None = None,
    ) -> dict[str, str]:
        return {"title": "Sales to Sampit"}

    monkeypatch.setattr(
        extractor,
        "extract_facts_with_opencode_direct_image",
        fake_direct,
    )

    payload, resolved = extractor.extract_raw_facts_from_image(image, {})

    assert payload == {"title": "Sales to Sampit"}
    assert resolved == "gemini:gemini-test → opencode:zen/mimo-v2.5-free"


def test_sanitize_payload_removes_generic_ai_description() -> None:
    payload: dict[str, object] = {
        "title": "Mobile App Developer",
        "nama_perusahaan": "PT Ravencode Digital Kreasi",
        "deskripsi_pekerjaan": (
            "<p>Posisi ini bertanggung jawab untuk mengembangkan aplikasi "
            "mobile.</p>"
        ),
        "persyaratan": "<p>Berpengalaman dalam pengembangan aplikasi mobile.</p>",
        "cara_melamar": (
            "<p>Lamaran dapat dikirimkan melalui tautan berikut: "
            "QR Code Pendaftaran.</p>"
        ),
        "situs_kontak": "https://ravencode.id/",
    }

    sanitize_payload_against_evidence(
        payload,
        "Mobile App Developer PT Ravencode Digital Kreasi",
    )

    assert "deskripsi_pekerjaan" not in payload
    assert "persyaratan" not in payload
    assert "cara_melamar" not in payload
    assert "situs_kontak" not in payload
    assert payload["uncertain_fields"] == [
        "deskripsi_pekerjaan:omitted_generic_ai_text",
        "persyaratan:omitted_not_visible_in_ocr",
        "cara_melamar:omitted_generic_ai_text",
        "situs_kontak:omitted_contact_not_visible",
    ]


def test_sanitize_payload_keeps_visible_requirements_and_contact() -> None:
    payload: dict[str, object] = {
        "title": "Medical Representative",
        "nama_perusahaan": "Dexa Group",
        "persyaratan": (
            "<ul><li>Pendidikan minimal D3 semua jurusan</li>"
            "<li>Memiliki SIM C</li></ul>"
        ),
        "cara_melamar": "<p>Daftar pada spark.dexagroup.com</p>",
        "situs_kontak": "spark.dexagroup.com",
    }

    sanitize_payload_against_evidence(
        payload,
        (
            "Medical Representative Dexa Group Pendidikan minimal D3 semua "
            "jurusan Memiliki SIM C Daftarkan diri pada spark.dexagroup.com"
        ),
    )

    assert "persyaratan" in payload
    assert "cara_melamar" in payload
    assert payload["situs_kontak"] == "spark.dexagroup.com"
    assert "uncertain_fields" not in payload
