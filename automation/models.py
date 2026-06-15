from __future__ import annotations

import os
import re
from enum import Enum
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
from pydantic_settings import BaseSettings, SettingsConfigDict

from automation.payload.constants import (
    DEFAULT_COPYWRITER_CHAIN,
    DEFAULT_OPENCODE_CHAIN,
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


class RuntimeEnvironment(BaseSettings):
    model_config = SettingsConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
    )

    wordpress_base_url: StrictStr = Field(validation_alias="WPLBJM_API_BASE_URL_PROD")
    wordpress_domain: StrictStr | None = Field(
        default=None,
        validation_alias="WPLBJM_API_BASE_URL_PROD",
    )
    wordpress_jwt: SecretStr = Field(validation_alias="WPLBJM_JWT_PROD")
    telegram_username: StrictStr
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr
    public_base_url: StrictStr | None = None
    ai_provider: Literal["opencode", "gemini"] = "gemini"
    opencode_model_chain: StrictStr = Field(default=DEFAULT_OPENCODE_CHAIN)
    opencode_copywriter_chain: StrictStr = Field(default=DEFAULT_COPYWRITER_CHAIN)
    opencode_api_key: SecretStr | None = None
    google_ai_studio_key: SecretStr | None = None
    skill_md_path: StrictStr | None = None
    media_group_delay_seconds: StrictFloat = Field(
        default=2.0,
        validation_alias="TELEGRAM_MEDIA_GROUP_DELAY_SECONDS",
    )
    bulk_command_ttl_seconds: StrictFloat = Field(
        default=90.0,
        validation_alias="TELEGRAM_BULK_COMMAND_TTL_SECONDS",
    )

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
            raise ValueError(
                "may contain only letters, numbers, underscore, and hyphen"
            )
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
    def set_public_base_url(self) -> RuntimeEnvironment:
        """Set public_base_url from environment if not explicitly provided."""
        if self.public_base_url is None:
            # Check multiple env vars in priority order
            if url := os.environ.get("PUBLIC_BASE_URL"):
                self.public_base_url = url
            elif url := os.environ.get("RENDER_EXTERNAL_URL"):
                self.public_base_url = url
            elif hostname := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
                self.public_base_url = f"https://{hostname}"
        return self

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
    source: StrictStr | None = None  # featured_image


class BuildResult(StrictModel):
    mode: Literal["mock_preview", "post_prod"]
    payload: NormalizedPayload
    warnings: list[StrictStr] = Field(default_factory=list)
    model_name: StrictStr | None = None
    http_status: StrictInt | None = None
    wordpress: dict[StrictStr, Any] | None = None
    exa_enriched: StrictBool = False
    exa_result_count: StrictInt = 0
    qr_redirects: list[dict[StrictStr, Any]] = Field(default_factory=list)


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


class Command(Enum):
    START = "/start"
    HELP = "/help"
    SET_DOMAIN = "/set_domain"
    REFRESH_JWT = "/refresh_jwt"
    SET_SKILL = "/set_skill"
    RESET_SKILL = "/reset_skill"
    ADD_USERS = "/add_users"
    RM_USERS = "/rm_users"
    RESET_USERS = "/reset_users"
    SET_MODEL = "/set_model"
    CURRENT_MODEL = "/current_model"
    SET_FALLBACK_MODEL = "/set_fallback_model"
    CURRENT_FALLBACK_MODEL = "/current_fallback_model"
    STATUS = "/status"
    POST_PROD = "/post_prod"


class TelegramPostDirective(FrozenStrictModel):
    command: Command = Command.POST_PROD
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
