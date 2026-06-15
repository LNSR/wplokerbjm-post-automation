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
from automation.ai.qr import qr_context_text
from automation.config import google_ai_studio_key
from automation.models import AgentError
from automation.payload.constants import DEFAULT_GEMINI_MODEL
from automation.web.exa import exa_context_text


def ai_client() -> genai.Client:
    api_key = google_ai_studio_key()
    if not api_key:
        raise AgentError("Missing required environment variable: GOOGLE_AI_STUDIO_KEY")
    return genai.Client(api_key=api_key)


def _inject_qr_and_exa(
    prompt_parts: list[Any],
    image_path: Path,
) -> tuple[bool, int, list[dict[str, Any]]]:
    """Add QR context and Exa web enrichment to prompt parts.

    Returns (exa_enriched, exa_result_count, qr_redirects).
    """
    qr_context, qr_redirects = qr_context_text(image_path)
    if qr_context:
        prompt_parts.append(f"<decoded_qr_codes>\n{qr_context}\n</decoded_qr_codes>")
    web_context = exa_context_text(qr_context)
    exa_count = 0
    if web_context:
        prompt_parts.append(f"<web_search_context>\n{web_context}\n</web_search_context>")
        # Estimate result count from "WEB SEARCH CONTEXT (EXA)" lines
        exa_count = sum(
            1 for line in web_context.split("\n")
            if line.strip().startswith(("1.", "2.", "3.", "4.", "5."))
        )
    return bool(web_context), exa_count, qr_redirects


def extract_payload_with_gemini(
    image_path: Path,
    options: dict[str, Any],
    *,
    model: str | None = None,
    custom_instruction: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (payload, enrichment) where enrichment holds exa_used, exa_count, qr_redirects."""
    client = ai_client()
    prompt_parts: list[Any] = [
        types.Part.from_bytes(
            data=image_path.read_bytes(),
            mime_type=image_mime_type(image_path),
        ),
    ]
    enrichment: dict[str, Any] = {}
    exa_used, exa_count, qr_redirects = _inject_qr_and_exa(prompt_parts, image_path)
    enrichment["exa_used"] = exa_used
    enrichment["exa_count"] = exa_count
    enrichment["qr_redirects"] = qr_redirects
    prompt_parts.append(build_prompt(options, custom_instruction))

    try:
        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            contents=prompt_parts,
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
    return parsed, enrichment


def extract_facts_with_gemini(
    image_path: Path,
    options: dict[str, Any],
    *,
    model: str | None = None,
    custom_instruction: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (raw_facts, enrichment) where enrichment holds exa_used, exa_count, qr_redirects."""
    client = ai_client()
    prompt_parts: list[Any] = [
        types.Part.from_bytes(
            data=image_path.read_bytes(),
            mime_type=image_mime_type(image_path),
        ),
    ]
    enrichment: dict[str, Any] = {}
    exa_used, exa_count, qr_redirects = _inject_qr_and_exa(prompt_parts, image_path)
    enrichment["exa_used"] = exa_used
    enrichment["exa_count"] = exa_count
    enrichment["qr_redirects"] = qr_redirects
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
    return parsed, enrichment
