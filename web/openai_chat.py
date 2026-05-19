"""OpenAI-compatible chat completions (streaming), e.g. MiniMax via OKAI gateway."""
import json
import os
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx

from web.chat_models import openai_api_key

DEFAULT_OPENAI_BASE = "https://www.okaoi.com/v1"


def openai_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE).rstrip("/")


async def stream_openai_chat(messages: list[dict], model: str) -> AsyncIterator[str]:
    base = openai_base_url()
    url = f"{base}/chat/completions"
    host = urlparse(base).netloc or base
    headers = {
        "Authorization": f"Bearer {openai_api_key()}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": True}

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code != 200:
                raw = await response.aread()
                try:
                    msg = json.loads(raw).get("error", {}).get("message", raw.decode())
                except json.JSONDecodeError:
                    msg = raw.decode(errors="replace")
                raise RuntimeError(f"Chat API {host} ({response.status_code}): {msg}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    yield text
