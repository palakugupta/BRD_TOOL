import io
from typing import List, Optional


def ocr_image_bytes(image_bytes: bytes) -> str:
    """
    OCR helper.
    Optional dependency: requires Pillow + pytesseract and a system tesseract install.
    Returns empty string if OCR isn't available.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return ""

    try:
        import pytesseract  # type: ignore
    except Exception:
        return ""

    try:
        img = Image.open(io.BytesIO(image_bytes))
        txt = pytesseract.image_to_string(img) or ""
        return txt.strip()
    except Exception:
        return ""


def ocr_many_images(images: List[bytes], limit: int = 20) -> str:
    texts: List[str] = []
    for b in images[:limit]:
        t = ocr_image_bytes(b)
        if t:
            texts.append(t)
    return "\n\n".join(texts).strip()

