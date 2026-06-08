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
    assert payload.social_media == [{"Instagram": "@contoh"}]
    assert "Omitted unsupported field: kualifikasi" in warnings
    assert "Omitted unknown lokasi_pekerjaan term: Tidak Ada" in warnings
    assert "Omitted non-positive numeric placeholder: umur_min" in warnings
    assert "Omitted invalid integer field: pengalaman" in warnings
    assert "Omitted unknown social_media keys: Unknown" in warnings


def test_normalize_payload_requires_title() -> None:
    with pytest.raises(AgentError, match="missing title"):
        normalize_payload({"persyaratan": "Ada"}, OPTIONS)


def test_normalized_payload_strict_integer_rejects_string() -> None:
    with pytest.raises(Exception):
        NormalizedPayload.model_validate(
            {
                "title": "Example | AI posted draft",
                "status_pekerjaan": "0",
            }
        )
