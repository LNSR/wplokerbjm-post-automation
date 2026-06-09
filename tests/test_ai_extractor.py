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


def test_extractor_skips_text_vision_without_independent_ocr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    text_vision_called = False
    direct_called = False

    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setattr(extractor, "local_ocr_text", lambda path: None)

    def unexpected_text_vision(path: Path) -> str:
        nonlocal text_vision_called
        text_vision_called = True
        return "stale text"

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
        "analyze_image_with_opencode_vision",
        unexpected_text_vision,
    )
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
        "extract_payload_with_opencode_direct_image",
        fake_direct,
    )

    payload = extractor.extract_payload_from_image(image, {})

    assert payload == {"title": "Sales to Sampit"}
    assert text_vision_called is False
    assert direct_called is True


def test_text_vision_uses_independent_ocr_for_identity_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "flyer.jpg"
    image.write_bytes(b"image")
    captured: list[str] = []

    monkeypatch.setenv("AI_PROVIDER", "opencode")
    monkeypatch.setenv("ALLOW_DIRECT_IMAGE_FALLBACK", "0")
    monkeypatch.setattr(
        extractor,
        "local_ocr_text",
        lambda path: "SALES TO SAMPIT BEHAESTEX",
    )
    monkeypatch.setattr(
        extractor,
        "analyze_image_with_opencode_vision",
        lambda path: "PT Garam recruitment",
    )
    monkeypatch.setattr(
        extractor,
        "opencode_attempts",
        lambda model=None: [
            OpenCodeAttempt(
                provider="zen",
                model="text-model",
                endpoint_style="chat",
            )
        ],
    )

    def fake_text_extract(
        image_path: Path,
        options: dict[str, object],
        attempt: OpenCodeAttempt,
        vision_text: str,
        *,
        evidence_text: str,
        custom_instruction: str | None = None,
    ) -> dict[str, str]:
        captured.append(evidence_text)
        raise AgentError("model title does not match the current flyer OCR")

    monkeypatch.setattr(
        extractor,
        "extract_payload_with_opencode",
        fake_text_extract,
    )

    with pytest.raises(AgentError, match="model title does not match"):
        extractor.extract_payload_from_image(image, {})

    assert captured == ["SALES TO SAMPIT BEHAESTEX"]


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
