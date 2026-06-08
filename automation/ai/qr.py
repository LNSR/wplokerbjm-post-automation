from __future__ import annotations

from pathlib import Path


def decode_qr_codes(image_path: Path) -> list[str]:
    try:
        import cv2
        import zxingcpp
    except ImportError:
        return []

    image = cv2.imread(str(image_path.resolve()))
    if image is None:
        return []

    try:
        barcodes = zxingcpp.read_barcodes(image)
    except Exception:
        return []

    values: list[str] = []
    for barcode in barcodes:
        text = str(getattr(barcode, "text", "") or "").strip()
        barcode_format = str(getattr(barcode, "format", "") or "")
        if text and ("qr" in barcode_format.casefold() or not barcode_format):
            values.append(text)

    return list(dict.fromkeys(values))


def qr_context_text(image_path: Path) -> str:
    values = decode_qr_codes(image_path)
    if not values:
        return ""

    lines = ["DECODED QR CODE CONTENT"]
    lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)
