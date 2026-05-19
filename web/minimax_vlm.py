"""MiniMax vision via dedicated VLM endpoint (not chat/completions image_url)."""
import json
import os
import re
from typing import Sequence

import httpx

from web.chat_models import gemini_api_key
from web.gemini import UNIAPI_BASE
# OKAI (www.okaoi.com) chat gateway does not expose /coding_plan/vlm — use official MiniMax host.
DEFAULT_VLM_BASE = "https://api.minimax.io/v1"

_DATA_URL_RE = re.compile(
    r"^data:(image/[\w+.-]+);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)

VLM_PROMPT = """Describe this image in detail for an SNEC PV+ trade show visitor.
Include all readable text (company names, booth numbers, halls, dates, slogans),
logos/brands, products (modules, inverters, ESS, etc.), and booth/event layout.
Be factual; do not invent details that are not visible."""

VLM_PATH = os.environ.get("MINIMAX_VLM_PATH", "coding_plan/vlm").strip().strip("/")


def vlm_base_url() -> str:
    return os.environ.get("MINIMAX_VLM_BASE_URL", DEFAULT_VLM_BASE).rstrip("/")


def vlm_api_key() -> str:
    for name in ("MINIMAX_VLM_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
    raise ValueError(
        "Image analysis requires MINIMAX_VLM_API_KEY, MINIMAX_API_KEY, or OPENAI_API_KEY."
    )


def _parse_data_url(data_url: str) -> tuple[str, str]:
    m = _DATA_URL_RE.match((data_url or "").strip())
    if not m:
        raise ValueError("Invalid image data URL.")
    mime = m.group(1).lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    b64 = m.group(2).replace("\n", "").replace("\r", "")
    return mime, b64


async def _minimax_vlm_one(prompt: str, image_data_url: str) -> str:
    url = f"{vlm_base_url()}/{VLM_PATH}"
    headers = {
        "Authorization": f"Bearer {vlm_api_key()}",
        "Content-Type": "application/json",
    }
    body = {"prompt": prompt, "image_url": image_data_url.strip()}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code != 200:
            try:
                err = response.json()
                msg = err.get("error", {}).get("message") or err.get("base_resp", {}).get(
                    "status_msg"
                ) or response.text
            except json.JSONDecodeError:
                msg = response.text
            raise RuntimeError(f"MiniMax VLM ({response.status_code}): {msg}")

        data = response.json()
        text = (data.get("content") or "").strip()
        if not text:
            base_resp = data.get("base_resp") or {}
            code = base_resp.get("status_code")
            msg = base_resp.get("status_msg") or "empty VLM response"
            raise RuntimeError(f"MiniMax VLM: {msg} ({code})")
        return text


async def _gemini_vision(prompt: str, image_data_urls: Sequence[str]) -> str:
    parts: list[dict] = [{"text": prompt}]
    for url in image_data_urls:
        mime, b64 = _parse_data_url(url)
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})

    model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
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
            raise RuntimeError(f"Gemini vision ({response.status_code}): {msg}")

        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini vision: no candidates in response")
        out_parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in out_parts).strip()
        if not text:
            raise RuntimeError("Gemini vision: empty text in response")
        return text


async def analyze_images(prompt: str, image_data_urls: Sequence[str]) -> str:
    """Return a text description of one or more images (VLM, with Gemini fallback)."""
    urls = [u.strip() for u in image_data_urls if (u or "").strip()]
    if not urls:
        return ""

    user_prompt = (prompt or "").strip() or VLM_PROMPT
    blocks: list[str] = []

    for i, url in enumerate(urls, start=1):
        one_prompt = user_prompt if len(urls) == 1 else f"{user_prompt}\n(Image {i} of {len(urls)}.)"
        try:
            desc = await _minimax_vlm_one(one_prompt, url)
        except Exception as minimax_err:
            uniapi = os.environ.get("UNIAPI_KEY", "").strip()
            if not uniapi:
                raise minimax_err
            try:
                desc = await _gemini_vision(one_prompt, [url])
            except Exception as gemini_err:
                raise RuntimeError(
                    f"MiniMax VLM failed ({minimax_err}); Gemini fallback failed ({gemini_err})"
                ) from gemini_err
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
