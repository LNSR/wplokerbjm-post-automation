from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from automation.ai.opencode.vision import image_mime_type
from automation.ai.prompt import build_prompt, build_raw_facts_prompt, extraction_schema, raw_facts_schema
from automation.config import google_ai_studio_key
from automation.models import AgentError
from automation.payload.constants import DEFAULT_GEMINI_MODEL


def ai_client() -> genai.Client:
    api_key = google_ai_studio_key()
    if not api_key:
        raise AgentError("Missing required environment variable: GOOGLE_AI_STUDIO_KEY")
    return genai.Client(api_key=api_key)


def _build_prompt_parts(
    image_path: Path,
    qr_context_text_value: str,
    web_context_text_value: str,
) -> list[Any]:
    """Build base prompt parts with image, QR, and web context."""
    prompt_parts: list[Any] = [
        types.Part.from_bytes(
            data=image_path.read_bytes(),
            mime_type=image_mime_type(image_path),
        ),
    ]
    if qr_context_text_value:
        prompt_parts.append(f"<decoded_qr_codes>\n{qr_context_text_value}\n</decoded_qr_codes>")
    if web_context_text_value:
        prompt_parts.append(f"<web_search_context>\n{web_context_text_value}\n</web_search_context>")
    return prompt_parts

def extract_facts_with_gemini(
    image_path: Path,
    options: dict[str, Any],
    qr_context_text_value: str = "",
    web_context_text_value: str = "",
    *,
    model: str | None = None,
    custom_instruction: str | None = None,
) -> dict[str, Any]:
    """Return raw facts using Gemini two-stage (facts) extraction.

    QR and web context are injected by the caller (extractor), not extracted here.
    """
    client = ai_client()
    prompt_parts = _build_prompt_parts(image_path, qr_context_text_value, web_context_text_value)
    prompt_parts.append(build_raw_facts_prompt(options, custom_instruction))

    try:
        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            contents=prompt_parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=raw_facts_schema(),
            ),
        )
    except genai_errors.APIError as error:
        raise AgentError(f"AI fact extraction failed: {error}") from error
    except RuntimeError as error:
        raise AgentError(f"AI fact extraction failed: {error}") from error

    if not response.text:
        raise AgentError("AI fact extraction returned an empty response.")

    parsed = json.loads(response.text)
    if not isinstance(parsed, dict):
        raise AgentError("AI fact extraction did not return a JSON object.")
    return parsed
