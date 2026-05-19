"""Chat model registry (MiniMax / OpenAI-compatible + Gemini via UniAPI)."""
import os

import web.env  # noqa: F401
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatModel:
    id: str
    label: str
    provider: str  # "gemini" | "openai"
    supports_images: bool = False


DEFAULT_GEMINI_ID = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
DEFAULT_OPENAI_ID = os.environ.get("OPENAI_MODEL", "MiniMax-M2.7")
DEFAULT_CHAT_MODEL = os.environ.get("DEFAULT_CHAT_MODEL", DEFAULT_OPENAI_ID)

CHAT_MODELS: tuple[ChatModel, ...] = (
    ChatModel(DEFAULT_OPENAI_ID, "MiniMax M2.7", "openai", supports_images=True),
    ChatModel(DEFAULT_GEMINI_ID, "Gemini 3.1 Flash Lite", "gemini"),
    ChatModel("deepseek-v4-flash", "DeepSeek V4 Flash", "openai"),
)


def model_supports_images(model_id: str | None) -> bool:
    try:
        return resolve_model(model_id).supports_images
    except ValueError:
        return False


def resolve_model(model_id: str | None) -> ChatModel:
    mid = (model_id or DEFAULT_CHAT_MODEL).strip()
    for m in CHAT_MODELS:
        if m.id == mid:
            return m
    raise ValueError(f"Unknown model: {mid}")


def openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not set.")
    return key


def gemini_api_key() -> str:
    key = os.environ.get("UNIAPI_KEY", "").strip()
    if not key:
        raise ValueError("UNIAPI_KEY is not set.")
    return key


def models_for_api() -> list[dict]:
    gemini_ok = bool(os.environ.get("UNIAPI_KEY"))
    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
    out = []
    for m in CHAT_MODELS:
        avail = openai_ok if m.provider == "openai" else gemini_ok
        out.append(
            {
                "id": m.id,
                "label": m.label,
                "provider": m.provider,
                "available": avail,
                "supports_images": m.supports_images,
            }
        )
    return out
