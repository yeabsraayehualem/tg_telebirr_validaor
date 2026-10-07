from __future__ import annotations

import re
from io import BytesIO

import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter


class ScreenshotError(Exception):
    pass


def _read_text(image: Image.Image) -> str:
    grey = ImageOps.grayscale(image)
    grey = ImageEnhance.Contrast(grey).enhance(1.8)
    texts = []
    for config in ("--psm 6", "--psm 11"):
        texts.append(pytesseract.image_to_string(grey, config=config))
    # Telebirr's screenshot places the transaction number in a two-column row.
    width, height = image.size
    row = image.crop((0, int(height * 0.54), width, int(height * 0.66)))
    row = row.resize((row.width * 2, row.height * 2))
    row = ImageOps.grayscale(row).filter(ImageFilter.SHARPEN)
    row = ImageEnhance.Contrast(row).enhance(2.0)
    for config in ("--psm 6", "--psm 7", "--psm 11"):
        texts.append(pytesseract.image_to_string(row, config=config))
    return "\n".join(texts)


def _valid_reference(value: str) -> bool:
    value = value.strip("-").upper()
    return 7 <= len(value) <= 24 and any(c.isalpha() for c in value) and any(c.isdigit() for c in value)


def _candidate_values(text: str) -> list[str]:
    candidates = []
    for match in re.finditer(r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])", text, re.I):
        value = match.group(0).strip("-").upper()
        if _valid_reference(value) and value not in candidates:
            candidates.append(value)
    return candidates


def _reference_after_label(text: str) -> str | None:
    # OCR sometimes confuses similar characters in the field label.
    label = re.search(r"trans[a-z0-9]{5,12}\s*(?:num[a-z0-9]{0,6}|no\.?|#)", text, re.I)
    if label:
        nearby = text[label.end():label.end() + 140]
        candidates = _candidate_values(nearby)
        if candidates:
            return candidates[0]
        # Some OCR modes insert spaces between characters in the reference.
        spaced = re.search(r"(?<![A-Z0-9])((?:[A-Z0-9][ \t]*){7,24})(?![A-Z0-9])", nearby, re.I)
        if spaced:
            value = re.sub(r"[^A-Z0-9-]", "", spaced.group(1).upper())
            if _valid_reference(value):
                return value
    # The final online receipt lookup verifies this candidate. This fallback
    # handles OCR that fails to recognize the clear printed field label.
    candidates = _candidate_values(text)
    return candidates[0] if len(candidates) == 1 else None


def extract_reference(data: bytes) -> str:
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise ScreenshotError("I couldn't read that image. Send a clear receipt screenshot.") from exc
    if image.width < 1200:
        image = image.resize((image.width * 2, image.height * 2))
    try:
        text = _read_text(image)
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise ScreenshotError(
            "Screenshot reading isn't available. Install Tesseract OCR, or type the transaction reference instead."
        ) from exc
    reference = _reference_after_label(text)
    if not reference:
        raise ScreenshotError(
            "I couldn't isolate a transaction reference from that screenshot. Please type it or resend the image as a file."
        )
    return reference
