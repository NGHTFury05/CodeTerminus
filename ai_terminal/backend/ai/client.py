"""AI client factory — OpenRouter (cloud) and LM Studio (local)."""
from __future__ import annotations

from typing import Optional

import openai

from backend.config import settings


def get_client(use_local: bool = False) -> openai.AsyncOpenAI:
    """Return the appropriate async OpenAI-compatible client."""
    if use_local and settings.LM_STUDIO_AVAILABLE:
        return openai.AsyncOpenAI(
            api_key="lm-studio",  # LM Studio ignores the key
            base_url=settings.LM_STUDIO_URL,
        )
    return openai.AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def get_model(use_local: bool = False, fast: bool = False) -> str:
    if use_local and settings.LM_STUDIO_AVAILABLE:
        return settings.LM_STUDIO_MODEL
    return settings.MODEL_FAST if fast else settings.MODEL_SMART
