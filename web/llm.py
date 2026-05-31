"""Route chat requests to Gemini or OpenAI-compatible providers."""
from typing import AsyncIterator

from web.chat_models import ChatModel, resolve_model
from web.context import build_messages, build_openai_messages
from web.gemini import stream_generate
from web.minimax_vlm import analyze_images, merge_message_with_vision
from web.openai_chat import stream_openai_chat


async def _enrich_turns_with_vision(history: list[dict]) -> list[dict]:
    out: list[dict] = []
    for turn in history:
        imgs = [u for u in (turn.get("images") or []) if (u or "").strip()]
        if turn.get("role") == "user" and imgs:
            vision = await analyze_images(turn.get("content") or "", imgs)
            merged = merge_message_with_vision(turn.get("content") or "", vision)
            out.append({**turn, "content": merged, "images": []})
        else:
            out.append(dict(turn))
    return out


async def stream_chat(
    model_id: str | None,
    history: list[dict],
    user_message: str,
    *,
    web_search: bool = True,
    images: list[str] | None = None,
    user_name: str | None = None,
) -> AsyncIterator[str]:
    model: ChatModel = resolve_model(model_id)
    imgs = [u for u in (images or []) if (u or "").strip()]
    msg = user_message
    hist = history

    if model.supports_images and imgs:
        vision = await analyze_images(msg, imgs)
        msg = merge_message_with_vision(msg, vision)
        imgs = []

    if model.supports_images and any(
        turn.get("images") for turn in history if turn.get("role") == "user"
    ):
        hist = await _enrich_turns_with_vision(history)

    if model.provider == "openai":
        messages = build_openai_messages(
            hist, msg, web_search=web_search, images=imgs or None, user_name=user_name
        )
        async for token in stream_openai_chat(messages, model.id):
            yield token
    else:
        contents = build_messages(hist, msg, web_search=web_search, user_name=user_name)
        async for token in stream_generate(contents, model=model.id):
            yield token
