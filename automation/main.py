from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automation.ai.extractor import extract_payload_from_image
from automation.ai.opencode.probe import probe_opencode
from automation.config import load_environment
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
) -> BuildResult:
    load_environment()
    config = wordpress_config()
    options = ingest_options(config)
    extracted = extract_payload_from_image(image_path, options, model=model)
    payload, warnings = normalize_payload(extracted, options, source=str(image_path.resolve()))

    result_data = {
        "mode": "post_prod" if post else "mock_preview",
        "payload": payload,
        "warnings": warnings,
    }

    if post:
        status, response = post_draft(config, payload, image_path)
        result_data["http_status"] = status
        result_data["wordpress"] = response

    return BuildResult.model_validate(result_data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a WPLokerBJM flyer payload and optionally post it to WordPress.",
    )
    parser.add_argument("image", nargs="?", type=Path, help="Path to the flyer image.")
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "AI model override. Use model, provider:model, or provider:model:endpoint_style. "
            f"Default chain: {DEFAULT_OPENCODE_CHAIN}."
        ),
    )
    parser.add_argument("--post-prod", action="store_true", help="Post multipart draft to production WordPress.")
    parser.add_argument("--probe-opencode", action="store_true", help="Check Zen/Go API key access without posting.")
    parser.add_argument("--serve", action="store_true", help="Run Telegram webhook server for Render.")
    args = parser.parse_args(argv)

    if args.serve:
        from automation.telegram.server import serve_bot

        serve_bot()
        return 0

    if args.probe_opencode:
        load_environment()
        print(json.dumps(probe_opencode().model_dump(exclude_none=True), ensure_ascii=False, indent=2))
        return 0

    if args.image is None:
        parser.error("image is required unless --serve or --probe-opencode is used.")

    try:
        result = build_result(
            args.image,
            post=args.post_prod,
            model=args.model,
        )
    except AgentError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(exclude_none=True), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
