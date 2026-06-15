from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from automation.ai.qr import qr_context_text
from automation.web.exa import exa_context_text


def image_mime_type(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type:
        return mime_type
    if image_path.suffix.lower() == ".webp":
        return "image/webp"
    return "application/octet-stream"


def opencode_direct_image_text(image_path: Path, contract_error: str | None = None) -> str:
    repair = ""
    if contract_error:
        repair = f"""

Your previous response violated the JSON contract:
{contract_error}

Return the same flyer extraction again, but use only the exact allowed snake_case keys from the system contract.
"""

    qr_context, _qr_redirects = qr_context_text(image_path)
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
