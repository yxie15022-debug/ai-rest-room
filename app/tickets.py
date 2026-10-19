"""Human lookup codes. Separate from the session id and the wall's anon id."""

from __future__ import annotations

from .config import get_settings
from .models import TICKET_ALPHABET

_CONFUSABLES = {'I': '1', 'L': '1', 'O': '0', 'U': 'V'}


def normalize_ticket(value: str | None) -> str | None:
    chars: list[str] = []
    for ch in (value or '').upper():
        if ch in '- \t':
            continue
        ch = _CONFUSABLES.get(ch, ch)
        chars.append(ch)
    token = ''.join(chars)
    if len(token) != 8 or any(ch not in TICKET_ALPHABET for ch in token):
        return None
    return token


def display_ticket(ticket: str) -> str:
    raw = normalize_ticket(ticket) or (ticket or '')
    if len(raw) != 8:
        return raw
    return f'{raw[:4]}-{raw[4:]}'


def room_url(ticket: str) -> str:
    base = get_settings().public_base_url.rstrip('/')
    return f'{base}/r/{display_ticket(ticket)}'
