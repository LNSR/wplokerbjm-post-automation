from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)


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


def normalize_telegram_username(value: str) -> str:
    normalized = value.strip().lstrip("@").casefold()
    if not re.fullmatch(r"[a-z0-9_]{5,32}", normalized):
        raise ValueError("must be a valid Telegram username")
    return normalized


def reveal_secret(value: str | SecretStr) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


class WordpressConfig(FrozenStrictModel):
    base_url: StrictStr
    jwt: SecretStr

    def jwt_value(self) -> str:
        return self.jwt.get_secret_value()


class OpenCodeAttempt(FrozenStrictModel):
    provider: Literal["go", "zen"]
    model: StrictStr
    endpoint_style: Literal["chat", "messages"]


class BotSettings(StrictModel):
    wordpress_base_url: StrictStr | None = None
    jwt: StrictStr | None = None
    skill_markdown: StrictStr | None = None
    extra_telegram_usernames: list[StrictStr] = Field(
        default_factory=list,
    )

    @field_validator("extra_telegram_usernames")
    @classmethod
    def validate_extra_telegram_usernames(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        for value in values:
            username = normalize_telegram_username(value)
            if username not in normalized:
                normalized.append(username)
        if len(normalized) > 20:
            raise ValueError("cannot contain more than 20 usernames")
        return normalized


class RuntimeEnvironment(StrictModel):
    wordpress_base_url: StrictStr
    wordpress_domain: StrictStr | None = None
    wordpress_jwt: SecretStr
    telegram_username: StrictStr
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr
    public_base_url: StrictStr | None = None
    ai_provider: Literal["opencode", "gemini"] = "gemini"
    opencode_model_chain: StrictStr
    opencode_copywriter_chain: StrictStr
    opencode_api_key: SecretStr | None = None
    google_ai_studio_key: SecretStr | None = None
    skill_md_path: StrictStr | None = None
    media_group_delay_seconds: StrictFloat
    bulk_command_ttl_seconds: StrictFloat

    @field_validator(
        "wordpress_base_url",
        "wordpress_domain",
        "public_base_url",
    )
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value.rstrip("/")

    @field_validator("wordpress_jwt", mode="before")
    @classmethod
    def validate_wordpress_jwt(cls, value: str | SecretStr) -> str:
        value = reveal_secret(value)
        if len(value) < 20 or value.count(".") != 2:
            raise ValueError("must look like a three-segment JWT")
        return value

    @field_validator("telegram_username")
    @classmethod
    def validate_telegram_username(cls, value: str) -> str:
        return normalize_telegram_username(value)

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def validate_telegram_bot_token(cls, value: str | SecretStr) -> str:
        value = reveal_secret(value)
        if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,64}", value):
            raise ValueError("must match Telegram's bot token format")
        return value

    @field_validator("telegram_webhook_secret", mode="before")
    @classmethod
    def validate_webhook_secret(cls, value: str | SecretStr) -> str:
        value = reveal_secret(value)
        if not 16 <= len(value) <= 256:
            raise ValueError("must contain between 16 and 256 characters")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("may contain only letters, numbers, underscore, and hyphen")
        return value

    @field_validator("media_group_delay_seconds", "bulk_command_ttl_seconds")
    @classmethod
    def validate_positive_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("opencode_model_chain", "opencode_copywriter_chain")
    @classmethod
    def validate_model_chain(cls, value: str) -> str:
        items = [item.strip() for item in value.split(",") if item.strip()]
        if not items:
            raise ValueError("must contain at least one model")
        for item in items:
            parts = item.split(":")
            if len(parts) != 3:
                raise ValueError(
                    "items must use provider:model:endpoint_style",
                )
            provider, model, endpoint_style = parts
            if provider not in {"zen", "go"}:
                raise ValueError(f"unsupported provider: {provider}")
            if not model:
                raise ValueError("model name cannot be empty")
            if endpoint_style not in {"chat", "messages"}:
                raise ValueError(
                    f"unsupported endpoint style: {endpoint_style}",
                )
        return value

    @model_validator(mode="after")
    def validate_ai_credentials(self) -> RuntimeEnvironment:
        if self.opencode_api_key is None:
            raise ValueError(
                "OpenCode requires OPENCODE_API_KEY for copywriter formatting",
            )

        if self.ai_provider == "gemini":
            if self.google_ai_studio_key is None:
                raise ValueError(
                    "Gemini requires GOOGLE_AI_STUDIO_KEY",
                )
            return self
        return self


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
    model_name: StrictStr | None = None
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


class TelegramPostDirective(FrozenStrictModel):
    command: Literal["/post_prod"] = "/post_prod"
    instruction: StrictStr | None = None


class TelegramMediaGroupState(StrictModel):
    chat_id: StrictInt | StrictStr
    media_group_id: StrictStr
    messages: list[dict[StrictStr, Any]] = Field(default_factory=list)
    directive: TelegramPostDirective | None = None


class TelegramChatCommandState(StrictModel):
    directive: TelegramPostDirective
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
