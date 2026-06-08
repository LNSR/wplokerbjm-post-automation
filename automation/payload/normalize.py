from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from automation.models import AgentError, NormalizedPayload, validation_error_summary
from automation.payload.constants import (
    ACCEPTED_PAYLOAD_FIELDS,
    CONTROLLED_TAXONOMIES,
    INT_FIELDS,
    SOCIAL_MEDIA_KEYS,
    TITLE_SUFFIX,
    WYSIWYG_FIELDS,
)


def split_terms(value: Any, *, taxonomy: str) -> list[str]:
    if isinstance(value, list):
        raw_parts = [str(item) for item in value]
    else:
        raw_parts = [part.strip() for part in str(value).split(",")]

    parts: list[str] = []
    for part in raw_parts:
        if taxonomy == "gender":
            parts.extend(piece.strip() for piece in re.split(r"\s*/\s*", part) if piece.strip())
        elif part.strip():
            parts.append(part.strip())
    return parts


def normalize_taxonomy_value(
    taxonomy: str,
    value: Any,
    options: dict[str, Any],
    warnings: list[str],
) -> str | None:
    if value in (None, "", []):
        return None

    taxonomies = options.get("taxonomies") if isinstance(options.get("taxonomies"), dict) else {}
    terms = taxonomies.get(taxonomy)
    if not isinstance(terms, list) or not terms:
        warnings.append(f"Omitted {taxonomy}: backend has no available terms.")
        return None

    index: dict[str, str] = {}
    for term in terms:
        if not isinstance(term, dict):
            continue
        for key in ("name", "slug"):
            term_value = term.get(key)
            if term_value:
                index[str(term_value).casefold()] = str(term.get("name") or term_value)

    accepted: list[str] = []
    for part in split_terms(value, taxonomy=taxonomy):
        canonical = index.get(part.casefold())
        if canonical:
            accepted.append(canonical)
        else:
            warnings.append(f"Omitted unknown {taxonomy} term: {part}")

    if not accepted:
        return None
    return ", ".join(dict.fromkeys(accepted))


def normalize_social_media(value: Any, warnings: list[str]) -> list[dict[str, str]] | None:
    if value in (None, "", []):
        return None

    rows: list[dict[str, str]] = []
    if isinstance(value, str):
        row: dict[str, str] = {}
        for item in value.split(";"):
            if ":" not in item:
                continue
            key, item_value = item.split(":", 1)
            key = key.strip()
            if key in SOCIAL_MEDIA_KEYS and item_value.strip():
                row[key] = item_value.strip()
        if row:
            rows.append(row)
    elif isinstance(value, dict):
        rows.append(value)
    elif isinstance(value, list):
        rows.extend(item for item in value if isinstance(item, dict))

    clean_rows: list[dict[str, str]] = []
    for row in rows:
        clean = {
            str(key): str(item_value).strip()
            for key, item_value in row.items()
            if key in SOCIAL_MEDIA_KEYS and str(item_value).strip()
        }
        skipped = sorted(set(map(str, row.keys())) - SOCIAL_MEDIA_KEYS)
        if skipped:
            warnings.append(f"Omitted unknown social_media keys: {', '.join(skipped)}")
        if clean:
            clean_rows.append(clean)

    return clean_rows or None


def normalize_wysiwyg(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"<\s*ol(\s[^>]*)?>", "<ul>", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*ol\s*>", "</ul>", text, flags=re.IGNORECASE)
    if "<" in text and ">" in text:
        return text
    return f"<p>{text}</p>"


def normalize_scalar(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return ", ".join(str(item).strip() for item in value.values() if str(item).strip())
    return str(value).strip()


def normalize_payload(
    payload: dict[str, Any],
    options: dict[str, Any],
    *,
    source: str | None = None,
) -> tuple[NormalizedPayload, list[str]]:
    warnings: list[str] = []
    normalized: dict[str, Any] = {}

    for key, value in payload.items():
        if key == "uncertain_fields":
            continue
        if key not in ACCEPTED_PAYLOAD_FIELDS:
            warnings.append(f"Omitted unsupported field: {key}")
            continue
        if value in (None, "", []):
            continue
        normalized[key] = value

    title = str(normalized.get("title", "")).strip()
    if not title:
        raise AgentError("Extracted payload is missing title.")
    if not title.endswith(TITLE_SUFFIX):
        title += TITLE_SUFFIX
    normalized["title"] = title

    normalized.pop("perusahaan", None)
    normalized["status_pekerjaan"] = int(normalized.get("status_pekerjaan") or 0)
    normalized.setdefault("gender", "Pria/Wanita")

    if source:
        normalized["source"] = source

    for field in {"email_kontak", "nomor_kontak", "situs_kontak"}:
        if field in normalized:
            normalized[field] = normalize_scalar(normalized[field])

    for field in INT_FIELDS:
        if field not in normalized:
            continue
        try:
            normalized[field] = int(normalized[field])
        except (TypeError, ValueError):
            warnings.append(f"Omitted invalid integer field: {field}")
            normalized.pop(field, None)
            continue
        if field != "status_pekerjaan" and normalized[field] <= 0:
            warnings.append(f"Omitted non-positive numeric placeholder: {field}")
            normalized.pop(field, None)

    for field in WYSIWYG_FIELDS:
        if field in normalized:
            normalized[field] = normalize_wysiwyg(normalized[field])

    for taxonomy in CONTROLLED_TAXONOMIES:
        if taxonomy not in normalized:
            continue
        value = normalize_taxonomy_value(taxonomy, normalized[taxonomy], options, warnings)
        if value:
            normalized[taxonomy] = value
        else:
            normalized.pop(taxonomy, None)

    social_media = normalize_social_media(normalized.get("social_media"), warnings)
    if social_media:
        normalized["social_media"] = social_media
    else:
        normalized.pop("social_media", None)

    uncertain = payload.get("uncertain_fields")
    if isinstance(uncertain, list) and uncertain:
        warnings.append("AI uncertain fields: " + ", ".join(map(str, uncertain)))

    try:
        return NormalizedPayload.model_validate(normalized), warnings
    except ValidationError as error:
        raise AgentError(f"Normalized payload failed strict validation: {validation_error_summary(error)}") from error
