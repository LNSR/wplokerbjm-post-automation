from __future__ import annotations

import base64
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path

from opencode_vision import ocr as vision_ocr

from automation.config import google_ai_studio_key
from automation.models import AgentError
from automation.ai.qr import qr_context_text
from automation.web.exa import exa_context_text


def local_ocr_text(image_path: Path) -> str | None:
    executable = shutil.which("tesseract")
    if not executable:
        return None

    languages = subprocess.run(
        [executable, "--list-langs"],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    available = {
        line.strip()
        for line in languages.stdout.splitlines()[1:]
        if line.strip()
    }
    language = next(
        (candidate for candidate in ("ind", "eng", "afr") if candidate in available),
        None,
    )
    if language is None:
        return None

    result = subprocess.run(
        [executable, str(image_path.resolve()), "stdout", "-l", language],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    text = result.stdout.strip()
    return text if result.returncode == 0 and text else None


def image_mime_type(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type:
        return mime_type
    if image_path.suffix.lower() == ".webp":
        return "image/webp"
    return "application/octet-stream"


def analyze_image_with_opencode_vision(image_path: Path) -> str:
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
    fallback_key = google_ai_studio_key()
    if not google_key and fallback_key:
        os.environ["GOOGLE_API_KEY"] = fallback_key
        os.environ["GOOGLE_GENERATIVE_AI_API_KEY"] = fallback_key

    mode = os.getenv("OPENCODE_VISION_MODE", "analyze").strip().lower()
    if mode == "ocr":
        result = vision_ocr.extract_text(str(image_path.resolve()))
    elif mode == "describe":
        result = vision_ocr.describe_image(
            str(image_path.resolve()),
            "Describe this Indonesian job vacancy flyer and transcribe all visible text exactly.",
        )
    else:
        result = analyze_image_with_vision_parts(image_path)

    error = result.get("error") if isinstance(result, dict) else None
    if error:
        raise AgentError(f"opencode-vision failed: {error}")

    text = result.get("text") if isinstance(result, dict) else None
    if not text or not str(text).strip():
        raise AgentError("opencode-vision returned empty text")

    parts = [str(text).strip()]
    qr_context = qr_context_text(image_path)
    if qr_context:
        parts.append(qr_context)
    web_context = exa_context_text("\n\n".join(parts))
    if web_context:
        parts.append(web_context)
    return "\n\n".join(parts)


def analyze_image_with_vision_parts(image_path: Path) -> dict[str, str]:
    path = str(image_path.resolve())
    description = vision_ocr.describe_image(
        path,
        "Describe this Indonesian job vacancy flyer. Transcribe all visible text exactly. Do not infer missing facts.",
    )
    ocr_text = vision_ocr.extract_text(path)

    parts: list[str] = []
    errors: list[str] = []

    if isinstance(description, dict) and description.get("text"):
        parts.append("VISUAL DESCRIPTION\n" + str(description["text"]).strip())
    elif isinstance(description, dict) and description.get("error"):
        errors.append("describe: " + str(description["error"]))

    if isinstance(ocr_text, dict) and ocr_text.get("text"):
        parts.append("TEXT CONTENT\n" + str(ocr_text["text"]).strip())
    elif isinstance(ocr_text, dict) and ocr_text.get("error"):
        errors.append("ocr: " + str(ocr_text["error"]))

    qr_context = qr_context_text(image_path)
    if qr_context:
        parts.append(qr_context)
    web_context = exa_context_text("\n\n".join(parts))
    if web_context:
        parts.append(web_context)

    if not parts:
        detail = "; ".join(errors) if errors else "no provider text returned"
        return {"error": f"opencode-vision provider produced no text ({detail})"}

    return {"text": "\n\n".join(parts)}


def opencode_user_text(image_path: Path, vision_text: str, contract_error: str | None = None) -> str:
    repair = ""
    if contract_error:
        repair = f"""

Your previous response violated the JSON contract:
{contract_error}

Return the same flyer extraction again, but use only the exact allowed snake_case keys from the system contract.
"""

    return f"""
Extract the job vacancy flyer from this opencode-vision result into the required JSON object.

Image path: {image_path.resolve()}

<opencode_vision_result>
{vision_text}
</opencode_vision_result>
{repair}
""".strip()


def opencode_direct_image_text(image_path: Path, contract_error: str | None = None) -> str:
    repair = ""
    if contract_error:
        repair = f"""

Your previous response violated the JSON contract:
{contract_error}

Return the same flyer extraction again, but use only the exact allowed snake_case keys from the system contract.
"""

    qr_context = qr_context_text(image_path)
    web_context = exa_context_text(qr_context)
    qr_section = f"""

<decoded_qr_codes>
{qr_context}
</decoded_qr_codes>
""" if qr_context else ""
    web_section = f"""

<web_search_context>
{web_context}
</web_search_context>
""" if web_context else ""

    return f"""
Extract the job vacancy flyer from the attached image into the required JSON object.

Image path: {image_path.resolve()}
{qr_section}
{web_section}
{repair}
""".strip()


def data_url_for_image(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{image_mime_type(image_path)};base64,{encoded}"
