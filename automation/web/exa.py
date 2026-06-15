from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from automation.models import ExaSearchResult

logger = logging.getLogger(__name__)


EXA_SEARCH_ENDPOINT = "https://api.exa.ai/search"


def exa_api_key() -> str | None:
    return os.getenv("EXA_API_KEY")


def exa_enabled() -> bool:
    if os.getenv("DISABLE_WEB_ENRICHMENT", "").lower() in {"1", "true", "yes"}:
        return False
    return bool(exa_api_key())


def compact_query_source(value: str, *, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text[:limit]


def build_validation_query(context: str) -> str:
    source = compact_query_source(context)
    return (
        "Validate Indonesian job vacancy flyer contact details, official website, "
        "application link, company address, and map/listing for this flyer text: "
        f"{source}"
    )


def exa_search(query: str, *, num_results: int = 3) -> list[ExaSearchResult]:
    key = exa_api_key()
    if not key:
        return []

    payload = {
        "query": query,
        "type": os.getenv("EXA_SEARCH_TYPE", "auto"),
        "numResults": num_results,
        "contents": {
            "highlights": {
                "maxCharacters": int(os.getenv("EXA_HIGHLIGHT_CHARACTERS", "600")),
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        EXA_SEARCH_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": key,
        },
    )

    try:
        with urlopen(request, timeout=int(os.getenv("EXA_TIMEOUT_SECONDS", "15"))) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Exa search failed: %s", exc)
        return []

    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        logger.info("Exa search returned no results")
        return []

    results: list[ExaSearchResult] = []
    for item in raw_results:
        parsed = parse_exa_result(item)
        if parsed:
            results.append(parsed)

    logger.info("Exa search returned %d result(s)", len(results))
    return results


def parse_exa_result(item: Any) -> ExaSearchResult | None:
    if not isinstance(item, dict):
        return None

    page = item.get("page") if isinstance(item.get("page"), dict) else item
    url = str(page.get("url") or item.get("url") or "").strip()
    if not url:
        return None

    highlights = item.get("highlights")
    if isinstance(highlights, list):
        text = " ".join(str(part).strip() for part in highlights if str(part).strip())
    else:
        text = str(page.get("text") or page.get("content") or item.get("text") or "").strip()

    return ExaSearchResult(
        title=str(page.get("title") or item.get("title") or "").strip() or None,
        url=url,
        text=text[:800] or None,
    )


def exa_context_text(context: str) -> str:
    if not exa_enabled() or not context.strip():
        return ""

    results = exa_search(build_validation_query(context))
    if not results:
        return ""

    lines = ["WEB SEARCH CONTEXT (EXA)"]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.title or 'Untitled'}")
        lines.append(f"   URL: {result.url}")
        if result.text:
            lines.append(f"   Snippet: {result.text}")
    return "\n".join(lines)
