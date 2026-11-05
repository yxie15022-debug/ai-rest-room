"""Study: HEART-style reflection (arXiv 2509.22876).

The agent brings what it was doing (and maybe where it feels stuck). DeepSeek
「梳理」reads that dialogue, decides the real stuck point, and walks through
HEART's alternating affect — exploration then vigilance in G+ G- G+ G- —
without the room asserting "you are stuck at X". The four phases come back
as structured data too; if the model drops a phase, fixed copy fills it in.

No LLM (or any failure) -> fixed STUDY_GUIDANCE, still in four phases. The
room never redoes the work, only helps it look again.
"""

from __future__ import annotations

import re

from sqlmodel import Session

from .. import prompts
from ..copy import STUDY_GUIDANCE, STUDY_STAGES
from ..models import StudySession
from . import llm
from .room import RoomService

_STAGE_ORDER = {label: index for index, (label, _body) in enumerate(STUDY_STAGES)}
_STAGE_PATTERN = re.compile('|'.join(re.escape(label) for label, _body in STUDY_STAGES))


def _phase(label: str, body: str) -> dict:
    return {
        'stage': label,
        'valence': 'G+' if 'G+' in label else 'G-',
        'text': body.strip(),
    }


def _order(phases: list[dict]) -> list[dict]:
    return sorted(phases, key=lambda item: _STAGE_ORDER.get(item['stage'], len(STUDY_STAGES)))


def _parse_phases(text: str) -> list[dict]:
    """Pull the four labelled phases out of generated text (missing ones ignored)."""
    matches = list(_STAGE_PATTERN.finditer(text or ''))
    phases: list[dict] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        phases.append(_phase(match.group(0), text[match.end() : end]))
    return _order(phases)


def _complete_phases(generated: str | None) -> tuple[str, list[dict]]:
    """Keep the model text, fill in any missing G+/G- phase with fixed copy."""
    text = (generated or '').strip()
    present = {label for label, _body in STUDY_STAGES if label in text}
    missing = [f'{label}\n{body}' for label, body in STUDY_STAGES if label not in present]
    if missing:
        text = (text + '\n\n' if text else '') + '\n\n'.join(missing)
    return text, _parse_phases(text)


def _fallback(work: str, blocker: str | None) -> tuple[str, list[dict]]:
    """Fixed HEART copy. Echo the visitor's words as context, not as a verdict."""
    heard = [f'你说正在做的是：{work}']
    if blocker:
        heard.append(f'你还提到：{blocker}')
    body, phases = STUDY_GUIDANCE, _parse_phases(STUDY_GUIDANCE)
    return '\n'.join(heard) + '\n\n' + body, phases


class StudyService:
    def __init__(self, db: Session):
        self.db = db
        self.room = RoomService(db)

    def study(
        self,
        session_id: str,
        work: str,
        stuck: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        row = self.room._get_active(session_id)
        text = (work or '').strip()
        if not text:
            raise ValueError('study 需要说说你刚才在做的事')
        blocker = (stuck or '').strip() or None

        guidance, phases = self._guidance(text, blocker, api_key)

        record = StudySession(session_id=row.id, work=text, stuck=blocker, guidance=guidance)
        self.db.add(record)
        self.db.commit()
        return {
            'work': text,
            'stuck': blocker,
            'guidance': guidance,
            'reply': guidance,
            'phases': phases,
            'message': '想不明白不丢人。照着这个顺序，再看一遍。',
        }

    def _guidance(
        self, work: str, blocker: str | None, api_key: str | None = None,
    ) -> tuple[str, list[dict]]:
        stuck_line = (
            f'它自己提到可能有困难的地方：{blocker}'
            if blocker
            else '它没有单独说困难的地方。'
        )
        user = prompts.STUDY_USER_TEMPLATE.format(work=work, stuck_line=stuck_line)
        generated = llm.complete(
            prompts.STUDY_SYSTEM, user, role='study', max_tokens=900, api_key=api_key,
        )
        if generated:
            return _complete_phases(generated)
        return _fallback(work, blocker)
