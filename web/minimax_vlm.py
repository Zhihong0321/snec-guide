"""Image analysis via UniAPI Gemini (injected into MiniMax chat as text)."""
import json
import os
import re
from typing import Sequence

import httpx

from web.chat_models import gemini_api_key
from web.gemini import UNIAPI_BASE

_DATA_URL_RE = re.compile(
    r"^data:(image/[\w+.-]+);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)

VISION_PROMPT = """Describe this image in detail for an SNEC PV+ trade show visitor.
Include all readable text (company names, booth numbers, halls, dates, slogans),
logos/brands, products (modules, inverters, ESS, etc.), and booth/event layout.
Be factual; do not invent details that are not visible."""


def vision_model() -> str:
    return (
        os.environ.get("IMAGE_VISION_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or "gemini-3.1-flash-lite"
    ).strip()


def _parse_data_url(data_url: str) -> tuple[str, str]:
    m = _DATA_URL_RE.match((data_url or "").strip())
    if not m:
        raise ValueError("Invalid image data URL.")
    mime = m.group(1).lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    b64 = m.group(2).replace("\n", "").replace("\r", "")
    return mime, b64


async def _gemini_vision(prompt: str, image_data_urls: Sequence[str]) -> str:
    parts: list[dict] = [{"text": prompt}]
    for url in image_data_urls:
        mime, b64 = _parse_data_url(url)
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})

    model = vision_model()
    api_url = f"{UNIAPI_BASE}/gemini/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": gemini_api_key(),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            api_url,
            headers=headers,
            json={"contents": [{"role": "user", "parts": parts}]},
        )
        if response.status_code != 200:
            try:
                msg = response.json().get("error", {}).get("message", response.text)
            except json.JSONDecodeError:
                msg = response.text
            raise RuntimeError(f"UniAPI Gemini vision ({response.status_code}): {msg}")

        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("UniAPI Gemini vision: no candidates in response")
        out_parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in out_parts).strip()
        if not text:
            raise RuntimeError("UniAPI Gemini vision: empty text in response")
        return text


async def analyze_images(prompt: str, image_data_urls: Sequence[str]) -> str:
    """Describe images with UniAPI Gemini; text is passed to the chat model."""
    urls = [u.strip() for u in image_data_urls if (u or "").strip()]
    if not urls:
        return ""

    user_prompt = (prompt or "").strip() or VISION_PROMPT
    blocks: list[str] = []

    for i, url in enumerate(urls, start=1):
        one_prompt = user_prompt if len(urls) == 1 else f"{user_prompt}\n(Image {i} of {len(urls)}.)"
        desc = await _gemini_vision(one_prompt, [url])
        label = f"Image {i}" if len(urls) > 1 else "Image"
        blocks.append(f"**{label}:**\n{desc}")

    return "\n\n".join(blocks)


def merge_message_with_vision(user_message: str, vision_block: str) -> str:
    text = (user_message or "").strip()
    if not vision_block.strip():
        return text
    if text:
        return f"{text}\n\n=== ATTACHED_IMAGE_ANALYSIS ===\n{vision_block.strip()}"
    return f"=== ATTACHED_IMAGE_ANALYSIS ===\n{vision_block.strip()}"
