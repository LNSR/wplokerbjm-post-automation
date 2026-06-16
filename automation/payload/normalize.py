from __future__ import annotations

import ast
import re
from datetime import date
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


URL_RE = re.compile(
    r"(?<![\"'=@])\b(https?://[^\s<]+|www\.[^\s<]+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s<]*)?)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"(?<![\w@.+-])([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})(?![\w@.-])")
PHONE_RE = re.compile(r"(?<!\d)(\+?62|0)[\d\s-]{8,}\d")
BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
P_WRAPPER_RE = re.compile(r"^<p>(.*)</p>$", re.IGNORECASE | re.DOTALL)


def compact_phone(value: str) -> str:
    phone = re.sub(r"[^\d+]", "", value.strip())
    if phone.startswith("0"):
        return "62" + phone[1:]
    if phone.startswith("+62"):
        return "62" + phone[3:]
    return phone.lstrip("+")


def normalize_phone_list(value: Any) -> str:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[;,]", str(value))

    normalized: list[str] = []
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        compact = compact_phone(raw)
        if not compact:
            continue
        normalized.append(f"+{compact}" if compact.startswith("62") else compact)
    return ", ".join(dict.fromkeys(normalized))


def safe_anchor(href: str, label: str) -> str:
    return f'<a rel="noopener nofollow noreferrer" href="{href}">{label}</a>'


def split_terms(value: Any, *, taxonomy: str) -> list[str]:
    if isinstance(value, list):
        raw_parts = [str(item) for item in value]
    else:
        raw_parts = [part.strip() for part in str(value).split(",")]

    parts: list[str] = []
    for part in raw_parts:
        if taxonomy == "gender":
            parts.extend(
                piece.strip() for piece in re.split(r"\s*/\s*", part) if piece.strip()
            )
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

    taxonomies = options.get("taxonomies")
    if not isinstance(taxonomies, dict):
        taxonomies = {}
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


def normalize_social_media(
    value: Any, warnings: list[str]
) -> list[dict[str, str]] | None:
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
        clean: dict[str, str] = {}
        for key, item_value in row.items():
            val = str(item_value).strip()
            if key not in SOCIAL_MEDIA_KEYS or not val:
                continue
            if key == "WhatsApp":
                compact = compact_phone(val)
                val = f"+{compact}" if compact.startswith("62") else (compact or val)
            elif val.startswith("@"):
                val = val[1:]
            if " " in val:
                warnings.append(
                    f"Omitted {key} with spaces — frontend cannot render as link"
                )
                continue
            clean[key] = val
        skipped = sorted(set(map(str, row.keys())) - SOCIAL_MEDIA_KEYS)
        if skipped:
            warnings.append(f"Omitted unknown social_media keys: {', '.join(skipped)}")
        if clean:
            clean_rows.append(clean)

    return clean_rows or None


def normalize_wysiwyg(value: Any, *, bullet_lists: bool = True) -> str:
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"<\s*ol(\s[^>]*)?>", "<ul>", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*ol\s*>", "</ul>", text, flags=re.IGNORECASE)
    inner_match = P_WRAPPER_RE.match(text)
    inner = inner_match.group(1).strip() if inner_match else text
    candidate = inner.replace("&nbsp;", " ").strip()

    if bullet_lists and candidate.startswith("[") and candidate.endswith("]"):
        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            items = [
                str(item).strip("'\" ") for item in parsed if str(item).strip("'\" ")
            ]
            if items:
                return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"

    if bullet_lists and BR_RE.search(candidate):
        parts = [
            part.strip(" -•\t")
            for part in BR_RE.split(candidate)
            if part.strip(" -•\t")
        ]
        if len(parts) >= 2:
            return "<ul>" + "".join(f"<li>{part}</li>" for part in parts) + "</ul>"

    if "<" in text and ">" in text:
        return text
    return f"<p>{text}</p>"


def normalize_anchor_rel(html: str) -> str:
    return re.sub(
        r"<a\s+(?![^>]*\brel=)",
        '<a rel="noopener nofollow noreferrer" ',
        html,
        flags=re.IGNORECASE,
    )


def linkify_plain_contacts(html: str) -> str:
    if "<a " in html.casefold():
        return normalize_anchor_rel(html)

    linked = URL_RE.sub(
        lambda match: safe_anchor(
            (
                match.group(1)
                if match.group(1).startswith("http")
                else f"https://{match.group(1)}"
            ),
            "Website Karir" if len(match.group(1)) > 32 else match.group(1),
        ),
        html,
    )
    linked = EMAIL_RE.sub(
        lambda match: safe_anchor(f"mailto:{match.group(1)}", match.group(1)),
        linked,
    )
    if re.search(r"\b(WA|WhatsApp)\b", html, flags=re.IGNORECASE):
        linked = PHONE_RE.sub(
            lambda match: safe_anchor(
                f"https://wa.me/{compact_phone(match.group(0))}",
                match.group(0).strip(),
            ),
            linked,
        )
    return linked


def normalize_cara_melamar(value: Any, normalized: dict[str, Any]) -> str:
    html = linkify_plain_contacts(normalize_wysiwyg(value, bullet_lists=False))
    if "<a " in html.casefold():
        return html

    contacts: list[str] = []
    for field in ("situs_kontak", "email_kontak", "nomor_kontak"):
        contact = str(normalized.get(field, "")).strip()
        if contact:
            contacts.extend(part.strip() for part in contact.split(",") if part.strip())
    if not contacts:
        return html

    contact_html: list[str] = []
    for contact in contacts:
        if "@" in contact and not contact.startswith("http"):
            contact_html.append(safe_anchor(f"mailto:{contact}", contact))
        elif contact.startswith(("http://", "https://", "www.")):
            href = contact if contact.startswith("http") else f"https://{contact}"
            contact_html.append(safe_anchor(href, "Website Karir"))
        elif re.search(r"(\+?62|0)\d", contact):
            contact_html.append(
                safe_anchor(f"https://wa.me/{compact_phone(contact)}", contact)
            )
    if not contact_html:
        return html
    return html.replace("</p>", f" {' / '.join(contact_html)}</p>", 1)


def normalize_scalar(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return ", ".join(
            str(item).strip() for item in value.values() if str(item).strip()
        )
    return str(value).strip()


def normalize_title_case(title: str) -> str:
    """Convert job title to Title Case, preserving known acronyms.

    Each word is capitalised (first letter uppercase, rest lowercase).
    Known acronyms (AI, PT, CV, etc.) are kept uppercase regardless of
    input case.
    """
    KNOWN_UPPER: set[str] = {
        "AI", "PT", "CV", "IT", "HRD",
        "SD", "SMP", "SMK", "SMA", "MI", "MTs", "MA",
        "D3", "D4", "S1", "S2", "S3", "SI", "TI",
    }
    words = title.split()
    result: list[str] = []
    for word in words:
        clean = word.strip("()[]{}.,;:!?\"'")
        upper = clean.upper()
        if upper in KNOWN_UPPER:
            result.append(upper)
        elif clean:
            result.append(clean[:1].upper() + clean[1:].lower())
        else:
            result.append(word)
    return " ".join(result)


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
    title = normalize_title_case(title)
    if not title.lower().endswith(TITLE_SUFFIX.lower()):
        title += TITLE_SUFFIX
    normalized["title"] = title

    normalized.pop("perusahaan", None)
    normalized["status_pekerjaan"] = int(normalized.get("status_pekerjaan") or 0)
    _deadline = normalized.get("deadline")
    if _deadline:
        try:
            _dl = date.fromisoformat(str(_deadline))
            if 0 <= (_dl - date.today()).days <= 14:
                normalized["status_pekerjaan"] = 2
        except (ValueError, TypeError):
            pass
    normalized.setdefault("gender", "Pria/Wanita")

    if source:
        normalized["source"] = source

    for field in {"email_kontak", "nomor_kontak", "situs_kontak"}:
        if field in normalized:
            if field == "nomor_kontak":
                normalized[field] = normalize_phone_list(normalized[field])
            else:
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
            if field == "cara_melamar":
                normalized[field] = normalize_cara_melamar(
                    normalized[field], normalized
                )
            else:
                normalized[field] = normalize_wysiwyg(
                    normalized[field], bullet_lists=True
                )

    for taxonomy in CONTROLLED_TAXONOMIES:
        if taxonomy not in normalized:
            continue
        value = normalize_taxonomy_value(
            taxonomy, normalized[taxonomy], options, warnings
        )
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
        raise AgentError(
            f"Normalized payload failed strict validation: {validation_error_summary(error)}"
        ) from error
