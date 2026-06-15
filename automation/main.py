from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automation.ai.extractor import extract_payload_from_image
from automation.ai.opencode.probe import probe_opencode
from automation.config import load_environment, validate_runtime_environment
from automation.models import AgentError, BuildResult
from automation.payload.constants import DEFAULT_OPENCODE_CHAIN
from automation.payload.normalize import normalize_payload
from automation.wordpress.auth import wordpress_config
from automation.wordpress.ingest import ingest_options, post_draft


def build_result(
    image_path: Path,
    *,
    post: bool,
    model: str | None,
    custom_instruction: str | None = None,
    fallback_chain: str | None = None,
) -> BuildResult:
    load_environment()
    config = wordpress_config()
    options = ingest_options(config)
    extracted, resolved_model, enrichment = extract_payload_from_image(
        image_path,
        options,
        model=model,
        custom_instruction=custom_instruction,
        fallback_chain=fallback_chain,
    )
    payload, warnings = normalize_payload(
        extracted,
        options,
        source=str(image_path.resolve()),
    )

    result_data = {
        "mode": "post_prod" if post else "mock_preview",
        "payload": payload,
        "warnings": warnings,
        "model_name": resolved_model,
        "exa_enriched": enrichment.get("exa_used", False),
        "exa_result_count": enrichment.get("exa_count", 0),
        "qr_redirects": enrichment.get("qr_redirects", []),
    }

    if post:
        status, response = post_draft(config, payload, image_path)
        result_data["http_status"] = status
        result_data["wordpress"] = response

    return BuildResult.model_validate(result_data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a WPLokerBJM flyer payload and optionally post it "
            "to WordPress."
        ),
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        help="Path to the flyer image.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "AI model override. Use model, provider:model, or "
            "provider:model:endpoint_style. "
            f"Default chain: {DEFAULT_OPENCODE_CHAIN}."
        ),
    )
    parser.add_argument(
        "--post-prod",
        action="store_true",
        help="Post multipart draft to production WordPress.",
    )
    parser.add_argument(
        "--probe-opencode",
        action="store_true",
        help="Check Zen/Go API key access without posting.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run Telegram webhook server for Render.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate runtime environment variables and skill paths.",
    )
    args = parser.parse_args(argv)

    if args.serve:
        from automation.telegram.server import serve_bot

        serve_bot()
        return 0

    if args.probe_opencode:
        load_environment()
        print(
            json.dumps(
                probe_opencode().model_dump(exclude_none=True),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.check_config:
        load_environment()
        try:
            settings = validate_runtime_environment(require_public_url=True)
        except AgentError as error:
            print(
                json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1
        print(
            json.dumps(
                {
                    "ok": True,
                    "ai_provider": settings.ai_provider,
                    "wordpress_base_url": settings.wordpress_base_url,
                    "telegram_username": settings.telegram_username,
                    "public_base_url": settings.public_base_url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.image is None:
        parser.error(
            "image is required unless --serve, --probe-opencode, "
            "or --check-config is used."
        )

    try:
        result = build_result(
            args.image,
            post=args.post_prod,
            model=args.model,
        )
    except AgentError as error:
        print(
            json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            result.model_dump(exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
