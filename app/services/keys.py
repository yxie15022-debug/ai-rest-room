"""The visitor's own DeepSeek key, kept on their machine.

This is what makes the room usable by anyone who runs it: the repository ships
no key at all, and whoever runs it pastes theirs into `/settings` once. The key
is written to `data/deepseek.json` -- outside the repository's tracked files and
gitignored -- and read back on every call, so nothing has to be restarted.

Order of preference when a call needs a key:

1. a key the caller passed for that one call (`api_key=`), which is never stored
2. the key saved here, which the person running this room uploaded
3. `DEEPSEEK_API_KEY` in `.env`, for a machine configured from the outside

The file is a plain local settings file, not a secret store: it is only as
private as the account running the server. That is the right trade for a
self-hosted toy, and it is stated on the page where the key is entered rather
than hidden.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

FILENAME = 'deepseek.json'


def key_path() -> Path:
    return get_settings().reports_path.parent / FILENAME


def saved_key() -> str | None:
    """The key uploaded through `/settings`, if there is one."""
    path = key_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning('could not read %s: %s', path.name, exc)
        return None
    value = data.get('api_key')
    return value.strip() if isinstance(value, str) and value.strip() else None


def save_key(api_key: str) -> None:
    """Store the key with owner-only permissions where the OS supports it."""
    value = (api_key or '').strip()
    if not value:
        raise ValueError('空的 key 不算数')
    path = key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({'api_key': value}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    # Windows ignores the mode, but POSIX hosts get a file no other user reads.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_key() -> None:
    try:
        key_path().unlink()
    except FileNotFoundError:
        pass


def origin() -> str:
    """Which source is currently supplying a key, for the settings page."""
    if saved_key():
        return 'saved'
    settings = get_settings()
    if settings.llm_enabled:
        return 'env'
    return 'none'


def mask(api_key: str) -> str:
    """Enough of a key to recognise it, never enough to use."""
    value = (api_key or '').strip()
    if len(value) <= 10:
        return '***'
    return f'{value[:6]}…{value[-4:]}'


def describe() -> dict:
    """What the settings page and the door need to say about the current key."""
    settings = get_settings()
    saved = saved_key()
    if saved:
        return {
            'source': 'saved',
            'masked': mask(saved),
            'llm': True,
            'file': FILENAME,
        }
    if settings.llm_enabled:
        return {
            'source': 'env',
            'masked': '（来自 .env）',
            'llm': True,
            'file': FILENAME,
        }
    return {'source': 'none', 'masked': '', 'llm': False, 'file': FILENAME}
