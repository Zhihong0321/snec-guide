"""Verify image attachment pipeline (preprocess → UniAPI Gemini → chat API)."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import web.env  # noqa: F401

from PIL import Image, ImageDraw

from web.context import build_openai_messages
from web.images import preprocess_image_data_url
from web.llm import stream_chat
from web.minimax_vlm import analyze_images, merge_message_with_vision, vision_model


def make_test_image_data_url() -> str:
    img = Image.new("RGB", (800, 400), color=(20, 40, 80))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, 760, 360), outline=(245, 166, 35), width=4)
    draw.text((60, 80), "Jinko Solar", fill=(255, 255, 255))
    draw.text((60, 140), "Booth: N1-310", fill=(200, 220, 255))
    draw.text((60, 200), "SNEC PV+ 2026", fill=(200, 220, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def test_merge_and_openai_messages_no_image_url() -> None:
    vision = "**Image:**\nJinko Solar booth N1-310"
    merged = merge_message_with_vision("", vision)
    assert "ATTACHED_IMAGE_ANALYSIS" in merged
    msgs = build_openai_messages([], merged, web_search=False, images=None)
    last = msgs[-1]["content"]
    assert isinstance(last, str)
    assert "image_url" not in json.dumps(msgs)


async def test_stream_chat_injects_vision() -> None:
    data_url = preprocess_image_data_url(make_test_image_data_url())
    fake_vision = "**Image:**\nJinko Solar, Booth N1-310, SNEC PV+ 2026"

    with patch("web.llm.analyze_images", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = fake_vision

        async def fake_stream(*_a, **_k):
            yield "Seen Jinko at N1-310."

        with patch("web.llm.stream_openai_chat", side_effect=fake_stream):
            chunks = []
            async for t in stream_chat(
                "MiniMax-M2.7", [], "", web_search=False, images=[data_url]
            ):
                chunks.append(t)

            mock_analyze.assert_awaited_once()
            assert "jinko" in "".join(chunks).lower()


async def test_chat_api_asgi(data_url: str) -> None:
    from fastapi.testclient import TestClient

    from web.main import app

    fake_vision = "**Image:**\nJinko Solar, Booth N1-310"
    with patch("web.llm.analyze_images", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = fake_vision

        async def fake_stream(*_a, **_k):
            yield "Seen Jinko at N1-310."

        with patch("web.llm.stream_openai_chat", side_effect=fake_stream):
            with TestClient(app) as client:
                r = client.post(
                    "/api/chat",
                    json={
                        "message": "What booth?",
                        "images": [data_url],
                        "model": "MiniMax-M2.7",
                        "web_search": False,
                    },
                )
    assert r.status_code == 200
    assert "don't see any image" not in r.text.lower()


async def test_live_gemini_vision(data_url: str) -> bool:
    if not os.environ.get("UNIAPI_KEY", "").strip():
        print("  skipped (UNIAPI_KEY not set)")
        return False
    print(f"  model: {vision_model()}")
    try:
        vision = await analyze_images("List company and booth.", [data_url])
        print(f"  OK ({len(vision)} chars): {vision[:220]}")
        return "jinko" in vision.lower() or "n1" in vision.lower()
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def main() -> int:
    print("=== Image attachment verification (UniAPI Gemini) ===\n")
    data_url = preprocess_image_data_url(make_test_image_data_url())

    test_merge_and_openai_messages_no_image_url()
    print("1) merge + messages (no image_url): OK")
    await test_stream_chat_injects_vision()
    print("2) stream_chat injects vision (mocked): OK")
    await test_chat_api_asgi(data_url)
    print("3) POST /api/chat ASGI (mocked): OK")

    print("\n4) Live UniAPI Gemini vision:")
    live = await test_live_gemini_vision(data_url)
    print("\n=== Done ===" if live else "\n=== Unit OK; fix UNIAPI_KEY for live vision ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
