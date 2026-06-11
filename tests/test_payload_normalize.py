from __future__ import annotations

import pytest

from automation.models import AgentError, NormalizedPayload
from automation.payload.normalize import normalize_payload


OPTIONS = {
    "taxonomies": {
        "gender": [
            {"name": "Pria", "slug": "pria"},
            {"name": "Wanita", "slug": "wanita"},
        ],
        "lokasi_pekerjaan": [{"name": "Banjarmasin", "slug": "banjarmasin"}],
        "jenis_pekerjaan": [{"name": "Full Time", "slug": "full-time"}],
        "pendidikan": [{"name": "SMA/SMK", "slug": "sma-smk"}],
        "kategori_lowongan": [{"name": "Retail", "slug": "retail"}],
    }
}


def test_normalize_payload_adds_title_suffix_and_default_gender() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Crew Store | Example",
            "nama_perusahaan": "Example",
            "persyaratan": "Jujur dan disiplin",
        },
        OPTIONS,
    )

    assert isinstance(payload, NormalizedPayload)
    assert payload.title == "Crew Store | Example | AI posted draft"
    assert payload.gender == "Pria, Wanita"
    assert payload.persyaratan == "<p>Jujur dan disiplin</p>"
    assert warnings == []


def test_normalize_payload_filters_unknown_terms_and_fields() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Admin",
            "gender": "Pria/Wanita",
            "lokasi_pekerjaan": "Tidak Ada",
            "kualifikasi": "unsupported",
            "umur_min": "0",
            "pengalaman": "abc",
            "social_media": [{"Instagram": "@contoh", "Unknown": "x"}],
        },
        OPTIONS,
    )

    assert payload.gender == "Pria, Wanita"
    assert payload.lokasi_pekerjaan is None
    assert payload.umur_min is None
    assert payload.pengalaman is None
    assert payload.social_media == [{"Instagram": "contoh"}]
    assert "Omitted unsupported field: kualifikasi" in warnings
    assert "Omitted unknown lokasi_pekerjaan term: Tidak Ada" in warnings
    assert "Omitted non-positive numeric placeholder: umur_min" in warnings
    assert "Omitted invalid integer field: pengalaman" in warnings
    assert "Omitted unknown social_media keys: Unknown" in warnings


def test_normalize_payload_requires_title() -> None:
    with pytest.raises(AgentError, match="missing title"):
        normalize_payload({"persyaratan": "Ada"}, OPTIONS)


def test_normalize_payload_linkifies_plain_application_contacts() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Helper",
            "cara_melamar": "Kirim CV via WA 0812-3456-7890 atau example.com/apply",
        },
        OPTIONS,
    )

    assert 'href="https://wa.me/6281234567890"' in str(payload.cara_melamar)
    assert 'href="https://example.com/apply"' in str(payload.cara_melamar)
    assert warnings == []


def test_normalize_payload_adds_links_from_contact_fields() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Admin",
            "cara_melamar": "Kirim lamaran melalui kontak berikut.",
            "email_kontak": "hr@example.com",
            "situs_kontak": "www.example.com/career",
        },
        OPTIONS,
    )

    assert 'href="mailto:hr@example.com"' in str(payload.cara_melamar)
    assert 'href="https://www.example.com/career"' in str(payload.cara_melamar)
    assert warnings == []


def test_normalize_payload_converts_list_repr_and_br_to_list_items() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Bank Staff",
            "persyaratan": "<p>['Penempatan di Banjarmasin', 'Komunikasi baik']</p>",
            "benefit": "THR<br>Jenjang Karir<br>BPJS",
        },
        OPTIONS,
    )

    assert payload.persyaratan == "<ul><li>Penempatan di Banjarmasin</li><li>Komunikasi baik</li></ul>"
    assert payload.benefit == "<ul><li>THR</li><li>Jenjang Karir</li><li>BPJS</li></ul>"
    assert warnings == []


def test_normalize_payload_does_not_bulletize_cara_melamar() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Bank Staff",
            "cara_melamar": "Kirim lamaran<br>via WhatsApp 0812-3456-7890",
        },
        OPTIONS,
    )

    assert "<ul>" not in str(payload.cara_melamar)
    assert 'href="https://wa.me/6281234567890"' in str(payload.cara_melamar)
    assert warnings == []


def test_normalize_social_media_strips_at_and_compacts_whatsapp() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Sales",
            "social_media": "Instagram: @contoh; WhatsApp: +62 812-3456-7890; TikTok: Dekorama Indah",
        },
        OPTIONS,
    )

    assert payload.social_media == [{"Instagram": "contoh", "WhatsApp": "+6281234567890"}]
    assert "Omitted TikTok with spaces — frontend cannot render as link" in warnings


def test_normalize_payload_compacts_nomor_kontak() -> None:
    payload, warnings = normalize_payload(
        {
            "title": "Helper",
            "nomor_kontak": "+62 819 4546 0526, 0812-3456-7890",
        },
        OPTIONS,
    )

    assert payload.nomor_kontak == "+6281945460526, +6281234567890"
    assert warnings == []


def test_normalized_payload_strict_integer_rejects_string() -> None:
    with pytest.raises(Exception):
        NormalizedPayload.model_validate(
            {
                "title": "Example | AI posted draft",
                "status_pekerjaan": "0",
            }
        )
