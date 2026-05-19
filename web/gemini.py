"""UniAPI Gemini streaming client."""
import json
import os
from typing import AsyncIterator

import httpx

from web.chat_models import gemini_api_key

UNIAPI_BASE = os.environ.get("UNIAPI_BASE_URL", "https://api.uniapi.io").rstrip("/")


def stream_url(model: str) -> str:
    return f"{UNIAPI_BASE}/gemini/v1beta/models/{model}:streamGenerateContent?alt=sse"


def _extract_text(payload: dict) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return ""


async def stream_generate(contents: list[dict], model: str) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            stream_url(model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gemini_api_key(),
            },
            json={"contents": contents},
        ) as response:
            if response.status_code != 200:
                raw = await response.aread()
                try:
                    msg = json.loads(raw).get("error", {}).get("message", raw.decode())
                except json.JSONDecodeError:
                    msg = raw.decode(errors="replace")
                raise RuntimeError(f"UniAPI ({response.status_code}): {msg}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    text = _extract_text(json.loads(data))
                except json.JSONDecodeError:
                    continue
                if text:
                    yield text
