"""DeepSeek client (OpenAI-compatible).

One job: turn a system + user prompt into text. Every call is best-effort —
on any failure (no key, timeout, network, bad response) it returns None, and
the caller falls back to the deterministic copy. The room must always work,
LLM or not.
"""

from __future__ import annotations

import logging

from openai import OpenAI

from ..config import get_settings

log = logging.getLogger(__name__)


def complete(system: str, user: str, *, max_tokens: int = 600, temperature: float = 0.7) -> str | None:
    """Return generated text, or None on any failure (caller falls back)."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout,
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (response.choices[0].message.content or '').strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - any LLM failure must degrade quietly
        log.warning('deepseek completion failed, falling back to copy: %s', exc)
        return None
