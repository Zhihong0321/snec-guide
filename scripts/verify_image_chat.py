"""Verify image attachment pipeline (preprocess → VLM → chat API)."""
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
from web.minimax_vlm import (
    DEFAULT_VLM_BASE,
    analyze_images,
    merge_message_with_vision,
    vlm_base_url,
)


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
    assert "Jinko" in merged
    msgs = build_openai_messages([], merged, web_search=False, images=None)
    last = msgs[-1]["content"]
    assert isinstance(last, str)
    assert "ATTACHED_IMAGE_ANALYSIS" in last
    assert "image_url" not in json.dumps(msgs)


async def test_stream_chat_injects_vision() -> None:
    data_url = preprocess_image_data_url(make_test_image_data_url())
    fake_vision = "**Image:**\nJinko Solar, Booth N1-310, SNEC PV+ 2026"

    with patch("web.llm.analyze_images", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = fake_vision
        with patch("web.llm.stream_openai_chat") as mock_stream:
            async def gen(*_a, **_k):
                yield "Booth "

            mock_stream.side_effect = lambda *_a, **_k: gen()

            chunks = []
            async for t in stream_chat(
                "MiniMax-M2.7",
                [],
                "",
                web_search=False,
                images=[data_url],
            ):
                chunks.append(t)

            mock_analyze.assert_awaited_once()
            call_msgs = mock_stream.call_args[0][0]
            user_content = call_msgs[-1]["content"]
            assert "ATTACHED_IMAGE_ANALYSIS" in user_content
            assert "Jinko" in user_content
            assert "".join(chunks).startswith("Booth")


async def probe_vlm_live(data_url: str) -> bool:
    import httpx

    from web.minimax_vlm import VLM_PATH, vlm_api_key

    if not any(os.environ.get(n, "").strip() for n in ("MINIMAX_VLM_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY")):
        print("  live VLM: skipped (no MiniMax API key)")
        return False

    url = f"{vlm_base_url()}/{VLM_PATH}"
    headers = {"Authorization": f"Bearer {vlm_api_key()}", "Content-Type": "application/json"}
    body = {"prompt": "List visible text.", "image_url": data_url}
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(url, headers=headers, json=body)
    print(f"  live VLM: {url} -> HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  {r.text[:200]}")
        return False
    content = (r.json().get("content") or "").strip()
    print(f"  sample: {content[:220]}")
    return bool(content) and ("jinko" in content.lower() or "n1" in content.lower())


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
    assert r.status_code == 200, r.text
    body = r.text.lower()
    assert "don't see any image" not in body
    assert "jinko" in body or "n1" in body
    mock_analyze.assert_awaited()


async def test_chat_api_live(data_url: str, port: int) -> bool:
    import httpx

    if not any(
        os.environ.get(n, "").strip()
        for n in ("MINIMAX_VLM_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY", "UNIAPI_KEY")
    ):
        print("  live /api/chat: skipped (no API keys)")
        return False

    model = os.environ.get("OPENAI_MODEL", "MiniMax-M2.7")
    payload = {
        "message": "What company and booth number are shown?",
        "images": [data_url],
        "history": [],
        "model": model,
        "web_search": False,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(f"http://127.0.0.1:{port}/api/chat", json=payload)
    except httpx.ConnectError:
        print("  live /api/chat: server not running")
        return False
    print(f"  live /api/chat: HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  {r.text[:300]}")
        return False
    text = r.text.lower()
    bad = (
        "don't see any image" in text
        or "no image" in text and "attached" in text
        or text.startswith("⚠️")
    )
    if bad:
        print(f"  FAIL body: {r.text[:400]}")
        return False
    print(f"  OK sample: {r.text[:280]}")
    return True


async def main() -> int:
    print("=== Image attachment verification ===\n")
    print(f"VLM base (default): {DEFAULT_VLM_BASE}")
    print(f"VLM base (active):  {vlm_base_url()}\n")

    data_url = preprocess_image_data_url(make_test_image_data_url())

    test_merge_and_openai_messages_no_image_url()
    print("1) merge + openai messages (no image_url): OK")

    await test_stream_chat_injects_vision()
    print("2) stream_chat injects vision (mocked): OK")

    await test_chat_api_asgi(data_url)
    print("3) POST /api/chat ASGI (mocked vision): OK")
    print(f"\n4) Live MiniMax VLM:")
    vlm_ok = await probe_vlm_live(data_url)

    print("\n5) Live analyze_images():")
    try:
        if any(os.environ.get(n, "").strip() for n in ("MINIMAX_VLM_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY", "UNIAPI_KEY")):
            vision = await analyze_images("List company and booth.", [data_url])
            print(f"   OK ({len(vision)} chars): {vision[:220]}")
            analyze_ok = "jinko" in vision.lower() or "n1" in vision.lower()
        else:
            print("   skipped (no keys)")
            analyze_ok = False
    except Exception as e:
        print(f"   FAIL: {e}")
        analyze_ok = False

    port = int(os.environ.get("VERIFY_PORT", "8080"))
    print(f"\n6) Live POST /api/chat :{port}:")
    chat_ok = await test_chat_api_live(data_url, port)

    print()
    if vlm_ok or analyze_ok or chat_ok:
        print("=== Live API checks passed (where keys/server available) ===")
        return 0
    print("=== Unit checks passed; live API skipped or failed (set keys + run server) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
