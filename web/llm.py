"""Route chat requests to Gemini or OpenAI-compatible providers."""
from typing import AsyncIterator

from web.chat_models import ChatModel, resolve_model
from web.context import build_messages, build_openai_messages
from web.gemini import stream_generate
from web.openai_chat import stream_openai_chat


async def stream_chat(
    model_id: str | None,
    history: list[dict],
    user_message: str,
    *,
    web_search: bool = True,
    images: list[str] | None = None,
) -> AsyncIterator[str]:
    model: ChatModel = resolve_model(model_id)
    if model.provider == "openai":
        messages = build_openai_messages(
            history, user_message, web_search=web_search, images=images
        )
        async for token in stream_openai_chat(messages, model.id):
            yield token
    else:
        contents = build_messages(history, user_message, web_search=web_search)
        async for token in stream_generate(contents, model=model.id):
            yield token
