from __future__ import annotations

import argparse
import http.cookies
import http.server
import json
import mimetypes
import os
import re
import ssl
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types


TITLE_SUFFIX = " | AI posted draft"
DEFAULT_MODEL = "gemini-2.5-flash"
SOCIAL_MEDIA_KEYS = {
    "WhatsApp",
    "Instagram",
    "Facebook",
    "X / Twitter",
    "Threads",
    "TikTok",
    "LinkedIn",
    "Youtube",
    "Telegram",
}
CONTROLLED_TAXONOMIES = {
    "kategori_lowongan",
    "lokasi_pekerjaan",
    "jenis_pekerjaan",
    "gender",
    "pendidikan",
}
WYSIWYG_FIELDS = {
    "tentang_perusahaan",
    "deskripsi_pekerjaan",
    "persyaratan",
    "cara_melamar",
    "benefit",
}
ACCEPTED_PAYLOAD_FIELDS = {
    "title",
    "nama_perusahaan",
    "perusahaan",
    "kategori_lowongan",
    "lokasi_pekerjaan",
    "jenis_pekerjaan",
    "gender",
    "pendidikan",
    "umur_min",
    "umur_max",
    "pengalaman",
    "gaji_minimal",
    "gaji_maksimal",
    "deadline",
    "status_pekerjaan",
    "tentang_perusahaan",
    "deskripsi_pekerjaan",
    "persyaratan",
    "cara_melamar",
    "benefit",
    "email_kontak",
    "nomor_kontak",
    "situs_kontak",
    "social_media",
    "source",
}
INT_FIELDS = {
    "umur_min",
    "umur_max",
    "pengalaman",
    "gaji_minimal",
    "gaji_maksimal",
    "status_pekerjaan",
}


class AgentError(RuntimeError):
    """Safe user-facing error. Never include secret values in the message."""


@dataclass(frozen=True)
class WordpressConfig:
    base_url: str
    jwt: str


@dataclass
class BotSettings:
    wordpress_base_url: str | None
    jwt: str | None
    skill_markdown: str | None


BOT_SETTINGS = BotSettings(
    wordpress_base_url=None,
    jwt=None,
    skill_markdown=None,
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def automation_root() -> Path:
    return Path(__file__).resolve().parent


def load_environment() -> None:
    """Load root and scrapper env files without printing secrets."""

    root = project_root()
    dotenv.load_dotenv(root / ".env", override=False)
    dotenv.load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def env_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AgentError(f"Missing required environment variable: {name}")
    return value


def wordpress_config(target: str) -> WordpressConfig:
    env_name = target.upper()
    if env_name not in {"DEV", "PROD"}:
        raise AgentError("target must be DEV or PROD.")

    return WordpressConfig(
        base_url=(BOT_SETTINGS.wordpress_base_url or env_value(f"WPLBJM_API_BASE_URL_{env_name}")).rstrip("/"),
        jwt=BOT_SETTINGS.jwt or env_value(f"WPLBJM_JWT_{env_name}"),
    )


def graphql_base_url() -> str:
    return (BOT_SETTINGS.wordpress_base_url or os.getenv("WPLBJM_WORDPRESS_DOMAIN") or env_value("WPLBJM_API_BASE_URL_PROD")).rstrip("/")


def ai_client() -> genai.Client:
    api_key = os.getenv("AI_STUDIO_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AgentError("Missing required environment variable: AI_STUDIO_KEY or GEMINI_API_KEY")
    return genai.Client(api_key=api_key)


def bundled_skill_paths() -> list[Path]:
    root = automation_root()
    return [
        root / ".agents/skills/job-copywriter/SKILL.md",
        root / ".agents/skills/agent-postdraft/SKILL.md",
    ]


def load_skill_markdown() -> tuple[str, str]:
    if BOT_SETTINGS.skill_markdown:
        return BOT_SETTINGS.skill_markdown, "Telegram upload"

    configured_path = os.getenv("SKILL_MD_PATH")
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = automation_root() / path
        if not path.is_file():
            raise AgentError(f"SKILL_MD_PATH file not found: {path}")
        return path.read_text(encoding="utf-8"), str(path)

    parts: list[str] = []
    paths = bundled_skill_paths()
    for path in paths:
        if not path.is_file():
            raise AgentError(f"Bundled skill file not found: {path}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts), "bundled repository skills"


def request_json(url: str, token: str, *, timeout: int = 30) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json_response(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, parse_json_response(body)
    except URLError as error:
        raise AgentError(f"Request failed: {error.reason}") from error


def request_graphql_jwt(username: str, password: str) -> str:
    mutation = """
mutation GetJWT($username: String, $password: String, $token: String) {
  jwt(username: $username, password: $password, token: $token)
}
""".strip()
    body = json.dumps(
        {
            "query": mutation,
            "variables": {
                "username": username,
                "password": password,
            },
        }
    ).encode("utf-8")
    request = Request(
        f"{graphql_base_url()}/graphql",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            token = jwt_from_headers(response.headers)
            data = parse_json_response(response_body)
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        data = parse_json_response(response_body)
        message = data.get("message") or data.get("errors") or "JWT GraphQL request failed."
        raise AgentError(f"JWT refresh failed ({error.code}): {message}") from error
    except URLError as error:
        raise AgentError(f"JWT refresh failed: {error.reason}") from error

    if token:
        return token

    errors = data.get("errors")
    if errors:
        raise AgentError(f"JWT refresh failed: {errors}")
    raise AgentError("JWT refresh failed: GraphQL did not set jwt-token cookie.")


def jwt_from_headers(headers: Any) -> str | None:
    set_cookies = []
    if hasattr(headers, "get_all"):
        set_cookies = headers.get_all("Set-Cookie") or []
    elif headers.get("Set-Cookie"):
        set_cookies = [headers.get("Set-Cookie")]

    for header in set_cookies:
        cookie = http.cookies.SimpleCookie()
        cookie.load(header)
        morsel = cookie.get("jwt-token")
        if morsel and morsel.value:
            return morsel.value
    return None


def parse_json_response(body: str) -> dict[str, Any]:
    """Recover JSON even when local WordPress appends PHP notices."""

    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(body[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        raise AgentError("Response was not valid JSON.")


def ingest_options(config: WordpressConfig) -> dict[str, Any]:
    status, data = request_json(
        f"{config.base_url}/wp-json/wplokerbjm/v1/lowongan/ingest/options",
        config.jwt,
    )
    if status != 200:
        code = data.get("code", "options_request_failed")
        message = data.get("message", "Unable to load ingest options.")
        raise AgentError(f"Options request failed ({status} {code}): {message}")
    return data


def image_mime_type(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type:
        return mime_type
    if image_path.suffix.lower() == ".webp":
        return "image/webp"
    return "application/octet-stream"


def extraction_schema() -> dict[str, Any]:
    string_fields = [
        "title",
        "nama_perusahaan",
        "perusahaan",
        "kategori_lowongan",
        "lokasi_pekerjaan",
        "jenis_pekerjaan",
        "gender",
        "pendidikan",
        "deadline",
        "tentang_perusahaan",
        "deskripsi_pekerjaan",
        "persyaratan",
        "cara_melamar",
        "benefit",
        "email_kontak",
        "nomor_kontak",
        "situs_kontak",
    ]
    properties: dict[str, Any] = {
        field: {"type": "STRING", "nullable": True} for field in string_fields
    }
    properties.update({field: {"type": "INTEGER", "nullable": True} for field in INT_FIELDS})
    properties["social_media"] = {
        "type": "ARRAY",
        "nullable": True,
        "items": {
            "type": "OBJECT",
            "properties": {key: {"type": "STRING", "nullable": True} for key in SOCIAL_MEDIA_KEYS},
        },
    }
    properties["uncertain_fields"] = {
        "type": "ARRAY",
        "nullable": True,
        "items": {"type": "STRING"},
    }
    return {"type": "OBJECT", "properties": properties}


def build_prompt(options: dict[str, Any]) -> str:
    taxonomies = options.get("taxonomies") if isinstance(options.get("taxonomies"), dict) else {}
    allowed = {
        name: [term.get("name") for term in terms if isinstance(term, dict) and term.get("name")]
        for name, terms in taxonomies.items()
        if name in CONTROLLED_TAXONOMIES and isinstance(terms, list)
    }
    skill_markdown, _ = load_skill_markdown()

    return f"""
You are extracting one Indonesian job vacancy flyer for WPLokerBJM.

Return only JSON matching the provided schema. Do not wrap it in markdown.

Follow these operator-provided skill instructions:
<skill>
{skill_markdown}
</skill>

Rules:
- Extract only facts visible in the flyer. Do not invent company profiles, salary, location, deadline, or contacts.
- Do not include ringkasanPekerjaan.
- title must be short and searchable. Use "Posisi | Perusahaan" when company is visible.
- Append "{TITLE_SUFFIX}" to title.
- If gender is visible, use only the visible requirement: "Pria", "Wanita", or "Pria/Wanita".
- If gender is not visible, set gender to "Pria/Wanita".
- status_pekerjaan must be 0 unless the flyer explicitly says urgent or pinned.
- Omit perusahaan unless explicitly needed as review context. It is reserved by the backend.
- WYSIWYG fields must use simple safe HTML: <p>, <ul>, <li>, and <strong> only.
- Write WYSIWYG fields in natural Indonesian, even if the flyer text is English.
- Contact fields must be plain scalar values, not HTML.
- social_media must be an array of objects using only these keys: {sorted(SOCIAL_MEDIA_KEYS)}.
- Typed fields must be raw integers. Deadline must be YYYY-MM-DD.
- Use only controlled taxonomy terms from this options object. Omit terms that do not exist:
{json.dumps(allowed, ensure_ascii=False, indent=2)}

Output useful fields only. Include uncertain_fields for values that need human review.
""".strip()


def extract_payload_from_image(
    image_path: Path,
    options: dict[str, Any],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    if not image_path.is_file():
        raise AgentError(f"Image file not found: {image_path}")

    client = ai_client()
    try:
        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
            contents=[
                types.Part.from_bytes(
                    data=image_path.read_bytes(),
                    mime_type=image_mime_type(image_path),
                ),
                build_prompt(options),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=extraction_schema(),
            ),
        )
    except genai_errors.APIError as error:
        raise AgentError(f"AI extraction failed: {error}") from error
    except RuntimeError as error:
        raise AgentError(f"AI extraction failed: {error}") from error

    if not response.text:
        raise AgentError("AI extraction returned an empty response.")

    parsed = json.loads(response.text)
    if not isinstance(parsed, dict):
        raise AgentError("AI extraction did not return a JSON object.")
    return parsed


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
    if "<" in text and ">" in text:
        return text
    return f"<p>{text}</p>"


def normalize_payload(
    payload: dict[str, Any],
    options: dict[str, Any],
    *,
    source: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
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

    for field in INT_FIELDS:
        if field not in normalized:
            continue
        try:
            normalized[field] = int(normalized[field])
        except (TypeError, ValueError):
            warnings.append(f"Omitted invalid integer field: {field}")
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

    return normalized, warnings


def encode_multipart(payload: dict[str, Any], image_path: Path) -> tuple[str, bytes]:
    boundary = "----wplbjm" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def add(value: str | bytes) -> None:
        chunks.append(value if isinstance(value, bytes) else value.encode("utf-8"))

    add(f"--{boundary}\r\n")
    add('Content-Disposition: form-data; name="payload"\r\n\r\n')
    add(json.dumps(payload, ensure_ascii=False))
    add("\r\n")

    add(f"--{boundary}\r\n")
    add(f'Content-Disposition: form-data; name="featured_image"; filename="{image_path.name}"\r\n')
    add(f"Content-Type: {image_mime_type(image_path)}\r\n\r\n")
    chunks.append(image_path.read_bytes())
    add("\r\n")

    add(f"--{boundary}--\r\n")
    return boundary, b"".join(chunks)


def post_draft(config: WordpressConfig, payload: dict[str, Any], image_path: Path) -> tuple[int, dict[str, Any]]:
    boundary, body = encode_multipart(payload, image_path)
    request = Request(
        f"{config.base_url}/wp-json/wplokerbjm/v1/lowongan/ingest",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {config.jwt}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )

    try:
        with urlopen(request, context=ssl._create_unverified_context(), timeout=120) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json_response(body_text)
    except HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        return error.code, parse_json_response(body_text)
    except URLError as error:
        raise AgentError(f"Draft post failed: {error.reason}") from error


def telegram_token() -> str:
    return env_value("TELEGRAM_BOT_TOKEN")


def public_base_url() -> str | None:
    explicit_url = os.getenv("PUBLIC_BASE_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")

    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if render_hostname:
        return f"https://{render_hostname.strip('/')}"

    return None


def telegram_webhook_url() -> str | None:
    base_url = public_base_url()
    return f"{base_url}/telegram/webhook" if base_url else None


def allowed_telegram_username() -> str:
    return env_value("TELEGRAM_USERNAME").lstrip("@").casefold()


def telegram_api(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{telegram_token()}/{method}",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = parse_json_response(response.read().decode("utf-8", errors="replace"))
    except HTTPError as error:
        data = parse_json_response(error.read().decode("utf-8", errors="replace"))
        raise AgentError(f"Telegram API failed ({error.code}): {data.get('description', data)}") from error
    except URLError as error:
        raise AgentError(f"Telegram API failed: {error.reason}") from error

    if data.get("ok") is False:
        raise AgentError(f"Telegram API failed: {data.get('description', 'unknown error')}")
    return data


def telegram_send_message(chat_id: int | str, text: str) -> None:
    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": True,
        },
    )


def register_telegram_webhook() -> dict[str, Any] | None:
    webhook_url = telegram_webhook_url()
    if not webhook_url:
        return None

    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message"],
        "drop_pending_updates": False,
    }
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret:
        payload["secret_token"] = secret

    return telegram_api("setWebhook", payload)


def telegram_file_path(file_id: str) -> str:
    data = telegram_api("getFile", {"file_id": file_id})
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    file_path = result.get("file_path")
    if not file_path:
        raise AgentError("Telegram did not return a file_path.")
    return str(file_path)


def download_telegram_file(file_id: str) -> Path:
    remote_path = telegram_file_path(file_id)
    suffix = Path(remote_path).suffix or ".jpg"
    local_path = Path(tempfile.gettempdir()) / f"telegram-flyer-{uuid.uuid4().hex}{suffix}"
    request = Request(f"https://api.telegram.org/file/bot{telegram_token()}/{remote_path}")
    try:
        with urlopen(request, timeout=60) as response:
            local_path.write_bytes(response.read())
    except HTTPError as error:
        raise AgentError(f"Telegram file download failed ({error.code}).") from error
    except URLError as error:
        raise AgentError(f"Telegram file download failed: {error.reason}") from error
    return local_path


def telegram_document(message: dict[str, Any]) -> dict[str, Any] | None:
    document = message.get("document")
    return document if isinstance(document, dict) else None


def skill_document_file_id(message: dict[str, Any]) -> str | None:
    document = telegram_document(message)
    if not document or not document.get("file_id"):
        return None

    filename = str(document.get("file_name") or "")
    mime_type = str(document.get("mime_type") or "")
    is_markdown = filename.casefold().endswith(".md") or mime_type in {
        "text/markdown",
        "text/plain",
    }
    if not is_markdown:
        return None

    file_size = int(document.get("file_size") or 0)
    if file_size > 256 * 1024:
        raise AgentError("SKILL.md upload is too large; maximum size is 256 KB.")
    return str(document["file_id"])


def read_uploaded_skill(message: dict[str, Any]) -> str:
    file_id = skill_document_file_id(message)
    if not file_id:
        raise AgentError("Attach a Markdown SKILL.md file with the /set_skill caption.")

    path = download_telegram_file(file_id)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as error:
        raise AgentError("Uploaded SKILL.md must be UTF-8 text.") from error
    finally:
        path.unlink(missing_ok=True)

    if not content:
        raise AgentError("Uploaded SKILL.md is empty.")
    return content


def first_photo_file_id(message: dict[str, Any]) -> str | None:
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        candidates = [item for item in photos if isinstance(item, dict) and item.get("file_id")]
        if candidates:
            largest = max(candidates, key=lambda item: int(item.get("file_size") or 0))
            return str(largest["file_id"])

    document = telegram_document(message)
    if document:
        mime_type = str(document.get("mime_type") or "")
        if mime_type.startswith("image/") and document.get("file_id"):
            return str(document["file_id"])
    return None


def authorize_update(update: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, int | None]:
    message = update.get("message")
    if not isinstance(message, dict):
        return False, None, None
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    username = str(sender.get("username") or "").casefold()
    return username == allowed_telegram_username(), message, chat_id


def format_preview(result: dict[str, Any]) -> str:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    lines = [
        "Draft payload ready.",
        f"Title: {payload.get('title', '-')}",
        f"Company: {payload.get('nama_perusahaan', '-')}",
        f"Gender: {payload.get('gender', '-')}",
        f"Email: {payload.get('email_kontak', '-')}",
        f"Phone: {payload.get('nomor_kontak', '-')}",
    ]
    warnings = result.get("warnings")
    if warnings:
        lines.append("Warnings: " + "; ".join(map(str, warnings)))
    wordpress = result.get("wordpress") if isinstance(result.get("wordpress"), dict) else None
    if wordpress:
        lines.extend(
            [
                f"HTTP: {result.get('http_status')}",
                f"ID: {wordpress.get('id', wordpress.get('existing_id', '-'))}",
                f"Edit: {wordpress.get('edit_url', '-')}",
            ]
        )
    return "\n".join(lines)


def handle_command(chat_id: int | str, text: str) -> str:
    command, _, rest = text.strip().partition(" ")
    command = command.split("@", 1)[0].lower()
    rest = rest.strip()

    if command in {"/start", "/help"}:
        return (
            "WPLokerBJM bot commands:\n"
            "/set_domain https://wp.example.com\n"
            "/refresh_jwt <wp_username> <wp_password>\n"
            "/set_skill as the caption of an attached SKILL.md file\n"
            "/reset_skill to restore the configured/repository fallback\n"
            "/status\n"
            "Send a flyer image to preview a payload. Add caption /post_dev or /post_prod to post."
        )

    if command == "/set_domain":
        if not rest.startswith(("http://", "https://")):
            return "Usage: /set_domain https://wp.example.com"
        BOT_SETTINGS.wordpress_base_url = rest.rstrip("/")
        return "WordPress domain URL updated for this running bot instance."

    if command in {"/refresh_jwt", "/set_jwt"}:
        username, _, password = rest.partition(" ")
        username = username or os.getenv("WP_LOGIN_USERNAME", "")
        password = password or os.getenv("WP_LOGIN_PASSWORD", "")
        if not username or not password:
            return "Usage: /refresh_jwt <wp_username> <wp_password>, or set WP_LOGIN_USERNAME/WP_LOGIN_PASSWORD env."
        BOT_SETTINGS.jwt = request_graphql_jwt(username, password)
        return "JWT refreshed from GraphQL and stored for this running bot instance."

    if command == "/reset_skill":
        BOT_SETTINGS.skill_markdown = None
        _, source = load_skill_markdown()
        return f"Runtime skill upload cleared. Active fallback: {source}."

    if command == "/status":
        _, skill_source = load_skill_markdown()
        return (
            "Current runtime settings:\n"
            f"WordPress domain: {BOT_SETTINGS.wordpress_base_url or os.getenv('WPLBJM_WORDPRESS_DOMAIN') or os.getenv('WPLBJM_API_BASE_URL_PROD') or 'fallback missing'}\n"
            f"JWT: {'runtime set' if BOT_SETTINGS.jwt else 'env fallback'}\n"
            f"Skill: {skill_source}\n"
            f"Allowed Telegram username: @{allowed_telegram_username()}"
        )

    return "Unknown command. Send /help for options."


def handle_telegram_update(update: dict[str, Any]) -> None:
    authorized, message, chat_id = authorize_update(update)
    if not message or chat_id is None:
        return
    if not authorized:
        telegram_send_message(chat_id, "Unauthorized Telegram username.")
        return

    text = str(message.get("text") or message.get("caption") or "").strip()
    command = text.split()[0].split("@", 1)[0].lower() if text.startswith("/") else ""

    if command == "/set_skill":
        try:
            BOT_SETTINGS.skill_markdown = read_uploaded_skill(message)
            telegram_send_message(
                chat_id,
                "Uploaded SKILL.md is active for this running bot instance.",
            )
        except AgentError as error:
            telegram_send_message(chat_id, f"Failed: {error}")
        return

    if text.startswith("/") and not first_photo_file_id(message):
        telegram_send_message(chat_id, handle_command(chat_id, text))
        return

    file_id = first_photo_file_id(message)
    if not file_id:
        telegram_send_message(chat_id, "Send a flyer image, or /help for commands.")
        return

    should_post = command in {"/post_dev", "/post_prod"}
    target = "PROD" if command == "/post_prod" else "DEV"

    image_path = download_telegram_file(file_id)
    try:
        result = build_result(image_path, target=target, post=should_post, model=None)
        telegram_send_message(chat_id, format_preview(result))
    except AgentError as error:
        telegram_send_message(chat_id, f"Failed: {error}")


class TelegramWebhookHandler(http.server.BaseHTTPRequestHandler):
    server_version = "WPLokerBJMAgent/1.0"

    def do_GET(self) -> None:
        if self.path in {"/", "/healthz"}:
            self.send_json(
                200,
                {
                    "ok": True,
                    "service": "wplokerbjm-post-automation",
                    "public_url": public_base_url(),
                    "telegram_webhook_url": telegram_webhook_url(),
                },
            )
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/telegram/webhook":
            self.send_json(404, {"ok": False, "error": "not_found"})
            return

        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            self.send_json(403, {"ok": False, "error": "forbidden"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            handle_telegram_update(update)
            self.send_json(200, {"ok": True})
        except Exception as error:
            self.send_json(200, {"ok": False, "error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_bot() -> None:
    load_environment()
    port = int(os.getenv("PORT", "8000"))

    webhook_url = telegram_webhook_url()
    if webhook_url:
        try:
            register_telegram_webhook()
            print(f"Telegram webhook registered: {webhook_url}", flush=True)
        except AgentError as error:
            print(f"Telegram webhook registration failed: {error}", file=sys.stderr, flush=True)
    else:
        print(
            "Telegram webhook registration skipped: no PUBLIC_BASE_URL or Render external URL detected.",
            flush=True,
        )

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), TelegramWebhookHandler)
    print(f"Telegram webhook server listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


def build_result(
    image_path: Path,
    *,
    target: str,
    post: bool,
    model: str | None,
) -> dict[str, Any]:
    load_environment()
    config = wordpress_config(target)
    options = ingest_options(config)
    extracted = extract_payload_from_image(image_path, options, model=model)
    payload, warnings = normalize_payload(extracted, options, source=str(image_path.resolve()))

    result: dict[str, Any] = {
        "target": target.upper(),
        "payload": payload,
        "warnings": warnings,
    }

    if post:
        status, response = post_draft(config, payload, image_path)
        result["http_status"] = status
        result["wordpress"] = response

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a WPLokerBJM flyer payload and optionally post it to WordPress.",
    )
    parser.add_argument("image", nargs="?", type=Path, help="Path to the flyer image.")
    parser.add_argument("--target", choices=["DEV", "PROD"], default="DEV")
    parser.add_argument("--model", default=None, help=f"Gemini model. Default: {DEFAULT_MODEL}.")
    parser.add_argument("--post", action="store_true", help="Post multipart draft to WordPress.")
    parser.add_argument("--serve", action="store_true", help="Run Telegram webhook server for Render.")
    args = parser.parse_args(argv)

    if args.serve:
        serve_bot()
        return 0

    if args.image is None:
        parser.error("image is required unless --serve is used.")

    try:
        result = build_result(
            args.image,
            target=args.target,
            post=args.post,
            model=args.model,
        )
    except AgentError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
