from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def decode_qr_codes(image_path: Path) -> list[str]:
    """Decode QR codes from image using zxingcpp.

    Tries PIL first (common dependency), then falls back to OpenCV (optional).
    """
    try:
        import zxingcpp
    except ImportError:
        return []

    barcodes = None

    # Primary: PIL (nearly always available with Pillow)
    try:
        from PIL import Image
        pil_image = Image.open(image_path)
        barcodes = zxingcpp.read_barcodes(pil_image)
    except Exception:
        pass

    # Fallback: OpenCV (optional heavy dependency)
    if not barcodes:
        try:
            import cv2
            image = cv2.imread(str(image_path.resolve()))
            if image is not None:
                barcodes = zxingcpp.read_barcodes(image)
        except Exception:
            pass

    if not barcodes:
        return []

    values: list[str] = []
    for barcode in barcodes:
        text = str(getattr(barcode, "text", "") or "").strip()
        barcode_format = str(getattr(barcode, "format", "") or "")
        if text and ("qr" in barcode_format.casefold() or not barcode_format):
            values.append(text)

    return list(dict.fromkeys(values))


def follow_qr_redirects(qr_urls: list[str]) -> list[dict[str, Any]]:
    """Follow HTTP redirects for decoded QR URLs.

    Returns list of dicts with original_url, final_url, redirect_count.
    Non-HTTP schemes (whatsapp://, tg://, tel:) are returned as-is.
    """
    results: list[dict[str, Any]] = []
    for url in qr_urls:
        if not url.startswith(("http://", "https://")):
            results.append({
                "original_url": url,
                "final_url": url,
                "redirect_count": 0,
            })
            continue
        try:
            req = Request(url, method="HEAD")
            with urlopen(req, timeout=10) as resp:
                final_url = resp.url
                redirected = 1 if final_url != url else 0
                results.append({
                    "original_url": url,
                    "final_url": final_url,
                    "redirect_count": redirected,
                })
                logger.info("QR redirect: %s -> %s (%d hop(s))", url, final_url, redirected)
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            logger.warning("QR redirect failed for %s: %s", url, exc)
            results.append({
                "original_url": url,
                "final_url": url,
                "redirect_count": 0,
            })
    return results


def qr_context_text(image_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Decode QR codes from image and follow redirects.

    Returns (context_text, redirect_info).
    - context_text: human-readable QR context for AI prompts
    - redirect_info: list of dicts with original/final URL and redirect count
    """
    values = decode_qr_codes(image_path)
    if not values:
        return "", []

    redirect_info = follow_qr_redirects(values)
    lines = ["DECODED QR CODE CONTENT"]
    for i, value in enumerate(values):
        info = redirect_info[i] if i < len(redirect_info) else None
        line = f"- {value}"
        if info and info.get("redirect_count", 0) > 0:
            line += f"\n  Redirect: {info['final_url']}"
        lines.append(line)
    return "\n".join(lines), redirect_info
