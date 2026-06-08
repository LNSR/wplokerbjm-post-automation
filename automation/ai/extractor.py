from __future__ import annotations

import json
import os
import re
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.ai.gemini import extract_payload_with_gemini
from automation.ai.opencode.client import (
    opencode_chat_body,
    opencode_chat_image_body,
    opencode_endpoint,
    opencode_headers,
    opencode_messages_body,
    opencode_messages_image_body,
    opencode_response_text,
)
from automation.ai.opencode.probe import opencode_attempts
from automation.ai.opencode.vision import analyze_image_with_opencode_vision
from automation.ai.prompt import build_prompt
from automation.config import opencode_api_key, opencode_key_label
from automation.models import AgentError, OpenCodeAttempt
from automation.payload.constants import ACCEPTED_PAYLOAD_FIELDS
from automation.wordpress.client import parse_json_response


def extract_payload_from_image(
    image_path: Path,
    options: dict[str, Any],
    *,
    model: str | None = None,
    custom_instruction: str | None = None,
) -> dict[str, Any]:
    if not image_path.is_file():
        raise AgentError(f"Image file not found: {image_path}")

    if os.getenv("AI_PROVIDER", "opencode").lower() == "gemini":
        return extract_payload_with_gemini(
            image_path,
            options,
            model=model,
            custom_instruction=custom_instruction,
        )

    errors: list[str] = []
    try:
        vision_text = analyze_image_with_opencode_vision(image_path)
    except AgentError as error:
        errors.append(f"opencode-vision: {error}")
    else:
        attempts = opencode_attempts(model)
        for attempt in attempts:
            try:
                return extract_payload_with_opencode(
                    image_path,
                    options,
                    attempt,
                    vision_text,
                    custom_instruction=custom_instruction,
                )
            except AgentError as error:
                errors.append(f"{attempt.provider}/{attempt.model}: {error}")

    if os.getenv("ALLOW_DIRECT_IMAGE_FALLBACK", "1").lower() not in {"0", "false", "no"}:
        for attempt in opencode_attempts(model):
            try:
                return extract_payload_with_opencode_direct_image(
                    image_path,
                    options,
                    attempt,
                    custom_instruction=custom_instruction,
                )
            except AgentError as error:
                errors.append(f"{attempt.provider}/{attempt.model} direct image: {error}")

    if os.getenv("ALLOW_GEMINI_FALLBACK", "").lower() in {"1", "true", "yes"}:
        try:
            return extract_payload_with_gemini(
                image_path,
                options,
                model=None,
                custom_instruction=custom_instruction,
            )
        except AgentError as error:
            errors.append(f"gemini fallback: {error}")

    raise AgentError("AI extraction failed for all providers: " + " | ".join(errors))


def extract_payload_with_opencode(
    image_path: Path,
    options: dict[str, Any],
    attempt: OpenCodeAttempt,
    vision_text: str,
    *,
    custom_instruction: str | None = None,
) -> dict[str, Any]:
    api_key = opencode_api_key(attempt.provider)
    if not api_key:
        raise AgentError(f"Missing API key for OpenCode {attempt.provider}: {opencode_key_label(attempt.provider)}.")

    prompt = build_prompt(options, custom_instruction)
    contract_error: AgentError | None = None
    for repair_attempt in range(2):
        if attempt.endpoint_style == "chat":
            body = opencode_chat_body(
                attempt.model,
                prompt,
                image_path,
                vision_text,
                contract_error=str(contract_error) if contract_error else None,
            )
        elif attempt.endpoint_style == "messages":
            body = opencode_messages_body(
                attempt.model,
                prompt,
                image_path,
                vision_text,
                contract_error=str(contract_error) if contract_error else None,
            )
        else:
            raise AgentError(f"Unsupported endpoint style: {attempt.endpoint_style}")

        request = Request(
            opencode_endpoint(attempt.provider, attempt.endpoint_style),
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=opencode_headers(api_key, attempt.endpoint_style),
        )

        try:
            with urlopen(request, context=ssl._create_unverified_context(), timeout=120) as response:
                data = parse_json_response(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            data = parse_json_response(error.read().decode("utf-8", errors="replace"))
            message = data.get("error") or data.get("message") or data
            raise AgentError(f"HTTP {error.code}: {message}") from error
        except URLError as error:
            raise AgentError(str(error.reason)) from error

        text = opencode_response_text(data, attempt.endpoint_style)
        if not text:
            raise AgentError("empty response text")
        payload = parse_model_json(text)
        try:
            validate_model_contract(payload)
            return payload
        except AgentError as error:
            contract_error = error

    raise contract_error or AgentError("model did not satisfy output contract")


def extract_payload_with_opencode_direct_image(
    image_path: Path,
    options: dict[str, Any],
    attempt: OpenCodeAttempt,
    *,
    custom_instruction: str | None = None,
) -> dict[str, Any]:
    api_key = opencode_api_key(attempt.provider)
    if not api_key:
        raise AgentError(f"Missing API key for OpenCode {attempt.provider}: {opencode_key_label(attempt.provider)}.")

    prompt = build_prompt(options, custom_instruction)
    contract_error: AgentError | None = None
    for repair_attempt in range(2):
        if attempt.endpoint_style == "chat":
            body = opencode_chat_image_body(
                attempt.model,
                prompt,
                image_path,
                contract_error=str(contract_error) if contract_error else None,
            )
        elif attempt.endpoint_style == "messages":
            body = opencode_messages_image_body(
                attempt.model,
                prompt,
                image_path,
                contract_error=str(contract_error) if contract_error else None,
            )
        else:
            raise AgentError(f"Unsupported endpoint style: {attempt.endpoint_style}")

        request = Request(
            opencode_endpoint(attempt.provider, attempt.endpoint_style),
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=opencode_headers(api_key, attempt.endpoint_style),
        )

        try:
            with urlopen(request, context=ssl._create_unverified_context(), timeout=120) as response:
                data = parse_json_response(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            data = parse_json_response(error.read().decode("utf-8", errors="replace"))
            message = data.get("error") or data.get("message") or data
            raise AgentError(f"HTTP {error.code}: {message}") from error
        except URLError as error:
            raise AgentError(str(error.reason)) from error

        text = opencode_response_text(data, attempt.endpoint_style)
        if not text:
            raise AgentError("empty response text")
        payload = parse_model_json(text)
        try:
            validate_model_contract(payload)
            return payload
        except AgentError as error:
            contract_error = error

    raise contract_error or AgentError("model did not satisfy output contract")


def validate_model_contract(payload: dict[str, Any]) -> None:
    unsupported = sorted(
        key for key in payload.keys() if key not in ACCEPTED_PAYLOAD_FIELDS and key != "uncertain_fields"
    )
    if unsupported:
        raise AgentError(
            "model returned unsupported fields: "
            + ", ".join(unsupported)
            + ". Use only the documented WPLokerBJM JSON contract keys."
        )
    status = payload.get("status_pekerjaan")
    if status not in (None, "", 0, 2, 3, "0", "2", "3"):
        raise AgentError("model returned invalid status_pekerjaan; allowed values are 0, 2, or 3")

    for field in ("umur_min", "umur_max", "pengalaman", "gaji_minimal", "gaji_maksimal"):
        if field not in payload or payload[field] in (None, ""):
            continue
        try:
            int(payload[field])
        except (TypeError, ValueError) as error:
            raise AgentError(f"model returned non-integer {field}; omit unknown numeric fields") from error


def parse_model_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AgentError("model response did not contain a JSON object")
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise AgentError("model response JSON was not an object")
    return parsed
