"""DeepSeek client (OpenAI-compatible), one role per key.

Roles (welcome / plan / sleep / study / chat) each prefer their own API key.
If that key is empty, they fall back to DEEPSEEK_API_KEY. Empty everywhere
means LLM off — callers always get None and use fixed copy. The room must
keep working with or without keys.

A caller can also hand over a key of its own (`api_key=`), which is how a
visitor brings their own DeepSeek account: the server keeps no key of its own
and every request runs on the caller's. That key is used for that call only --
it is never written to the database, never logged, and never kept in a module
or process global, so one visitor's key cannot leak into another's turn.
"""

from __future__ import annotations

import logging
from typing import Literal

from openai import OpenAI

from ..config import get_settings
from . import keys as keys_store

log = logging.getLogger(__name__)

Role = Literal['welcome', 'plan', 'sleep', 'study', 'chat']


def complete(
    system: str,
    user: str,
    *,
    role: Role,
    max_tokens: int = 600,
    temperature: float = 0.7,
    api_key: str | None = None,
) -> str | None:
    """Return generated text for one role, or None on any failure.

    `api_key` wins over the server's own configuration when given: this is a
    visitor spending their own quota, so the server must not quietly charge
    itself instead.
    """
    settings = get_settings()
    # A key the caller passed for this call wins, then the one the person
    # running this room saved on the settings page, then `.env`.
    key = (
        (api_key or '').strip()
        or keys_store.saved_key()
        or settings.key_for(role)
    )
    if not key:
        return None
    # The key is never put in a message: an LLM failure logs the exception,
    # and some HTTP clients quote the request headers in their errors.
    try:
        client = OpenAI(
            api_key=key,
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
        log.warning('deepseek %s failed, falling back to copy: %s', role, _scrub(exc, key))
        return None


def _scrub(exc: Exception, key: str) -> str:
    """The exception text with the key removed, for the log.

    A bad key can come back from the API echoed in the error body, and this
    line goes to a log file that outlives the request.
    """
    text = str(exc)
    if key and key in text:
        text = text.replace(key, '***')
    return text[:400]
