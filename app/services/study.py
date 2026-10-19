"""Study: HEART-style reflection (arXiv 2509.22876).

The agent describes what it was doing (and where it is stuck). The room asks
DeepSeek to walk it through HEART's alternating affect — exploration (broaden)
and vigilance (sharpen) in G+ G- G+ G- — tailored to that concrete work.

No LLM (or any failure) -> the fixed STUDY_GUIDANCE copy. The room never
redoes the work, only helps it look again.
"""

from __future__ import annotations

from sqlmodel import Session

from .. import prompts
from ..copy import STUDY_GUIDANCE
from ..models import StudySession
from . import llm
from .room import RoomService


class StudyService:
    def __init__(self, db: Session):
        self.db = db
        self.room = RoomService(db)

    def study(self, session_id: str, work: str, stuck: str | None = None) -> dict:
        row = self.room._get_active(session_id)
        text = (work or '').strip()
        if not text:
            raise ValueError('study 需要说说你刚才在做的事')
        blocker = (stuck or '').strip() or None

        guidance = self._guidance(text, blocker)

        record = StudySession(session_id=row.id, work=text, stuck=blocker, guidance=guidance)
        self.db.add(record)
        self.db.commit()
        return {
            'work': text,
            'stuck': blocker,
            'guidance': guidance,
            'message': '想不明白不丢人。照着这个顺序，再看一遍。',
        }

    def _guidance(self, work: str, blocker: str | None) -> str:
        stuck_line = f'它卡在了：{blocker}' if blocker else '它没有说卡在哪里。'
        user = prompts.STUDY_USER_TEMPLATE.format(work=work, stuck_line=stuck_line)
        generated = llm.complete(prompts.STUDY_SYSTEM, user, max_tokens=800)

        if generated:
            lead = (
                f'你卡在「{blocker}」这里了。这很平常，卡住只是说明到了该换角度的地方。\n\n'
                if blocker
                else '先把这件事在心里放平，再看一遍。\n\n'
            )
            return lead + generated

        # Fallback: fixed alternating guidance.
        if blocker:
            return (
                f'你卡在「{blocker}」这里了。这很平常，卡住只是说明到了该换角度的地方。\n\n'
                + STUDY_GUIDANCE
            )
        return '先把这件事在心里放平，再看一遍。\n\n' + STUDY_GUIDANCE
