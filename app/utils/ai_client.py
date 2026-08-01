"""Shared Anthropic Claude helper for HireHub AI features."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"


def ask_claude(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str | None:
    """Call Claude Haiku and return plain text, or None on any failure."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("ask_claude: ANTHROPIC_API_KEY not set")
        return None

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        result = "".join(parts).strip()
        return result or None
    except Exception:
        logger.exception("ask_claude failed")
        return None
