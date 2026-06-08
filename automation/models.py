from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, ValidationError


class AgentError(RuntimeError):
    """Safe user-facing error. Never include secret values in the message."""


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
    )


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
    )


class WordpressConfig(FrozenStrictModel):
    base_url: StrictStr
    jwt: StrictStr


class OpenCodeAttempt(FrozenStrictModel):
    provider: Literal["go", "zen"]
    model: StrictStr
    endpoint_style: Literal["chat", "messages"]


class BotSettings(StrictModel):
    wordpress_base_url: StrictStr | None = None
    jwt: StrictStr | None = None
    skill_markdown: StrictStr | None = None


class NormalizedPayload(StrictModel):
    title: StrictStr
    nama_perusahaan: StrictStr | None = None
    kategori_lowongan: StrictStr | None = None
    lokasi_pekerjaan: StrictStr | None = None
    jenis_pekerjaan: StrictStr | None = None
    gender: StrictStr | None = None
    pendidikan: StrictStr | None = None
    umur_min: StrictInt | None = None
    umur_max: StrictInt | None = None
    pengalaman: StrictInt | None = None
    gaji_minimal: StrictInt | None = None
    gaji_maksimal: StrictInt | None = None
    deadline: StrictStr | None = None
    status_pekerjaan: StrictInt = 0
    tentang_perusahaan: StrictStr | None = None
    deskripsi_pekerjaan: StrictStr | None = None
    persyaratan: StrictStr | None = None
    cara_melamar: StrictStr | None = None
    benefit: StrictStr | None = None
    email_kontak: StrictStr | None = None
    nomor_kontak: StrictStr | None = None
    situs_kontak: StrictStr | None = None
    social_media: list[dict[StrictStr, StrictStr]] | None = None
    source: StrictStr | None = None


class BuildResult(StrictModel):
    mode: Literal["mock_preview", "post_prod"]
    payload: NormalizedPayload
    warnings: list[StrictStr] = Field(default_factory=list)
    http_status: StrictInt | None = None
    wordpress: dict[StrictStr, Any] | None = None


class OpenCodeProbeAttemptResult(StrictModel):
    provider: Literal["go", "zen"]
    model: StrictStr
    endpoint_style: Literal["chat", "messages"]
    ok: StrictBool
    status: StrictInt | None = None
    sample: StrictStr | None = None
    message: Any | None = None


class OpenCodeProbeResult(StrictModel):
    attempts: list[OpenCodeProbeAttemptResult]
    chain: list[OpenCodeAttempt]


class TelegramMediaGroupState(StrictModel):
    chat_id: StrictInt | StrictStr
    media_group_id: StrictStr
    messages: list[dict[StrictStr, Any]] = Field(default_factory=list)
    command: StrictStr | None = None


class TelegramChatCommandState(StrictModel):
    command: StrictStr
    expires_at: StrictFloat


class ExaSearchResult(StrictModel):
    title: StrictStr | None = None
    url: StrictStr
    text: StrictStr | None = None


def validation_error_summary(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors():
        location = ".".join(map(str, item.get("loc", ()))) or "value"
        message = item.get("msg", "invalid value")
        parts.append(f"{location}: {message}")
    return "; ".join(parts)
