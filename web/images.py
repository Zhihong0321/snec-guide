"""Resize chat image attachments to a max dimension (OpenAI vision payloads)."""
import base64
import io
import re
from typing import Sequence

from PIL import Image

MAX_IMAGE_DIM = 1920
MAX_IMAGES_PER_MESSAGE = 4
JPEG_QUALITY = 85

_DATA_URL_RE = re.compile(
    r"^data:(image/[\w+.-]+);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


def preprocess_image_data_url(data_url: str) -> str:
    """Decode a data URL, fit inside MAX_IMAGE_DIM, return JPEG data URL."""
    raw = (data_url or "").strip()
    m = _DATA_URL_RE.match(raw)
    if not m:
        raise ValueError("Invalid image data URL.")
    b64 = m.group(2).replace("\n", "").replace("\r", "")
    try:
        blob = base64.b64decode(b64, validate=True)
    except Exception as e:
        raise ValueError("Invalid base64 image data.") from e
    if len(blob) > 20 * 1024 * 1024:
        raise ValueError("Image too large before resize.")

    with Image.open(io.BytesIO(blob)) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w > MAX_IMAGE_DIM or h > MAX_IMAGE_DIM:
            scale = min(MAX_IMAGE_DIM / w, MAX_IMAGE_DIM / h)
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def preprocess_images(data_urls: Sequence[str]) -> list[str]:
    urls = [u.strip() for u in data_urls if (u or "").strip()]
    if len(urls) > MAX_IMAGES_PER_MESSAGE:
        raise ValueError(f"At most {MAX_IMAGES_PER_MESSAGE} images per message.")
    return [preprocess_image_data_url(u) for u in urls]
