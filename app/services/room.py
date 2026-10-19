from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import prompts
from ..copy import DEAUTHORIZATION, ENTRANCE_NOTE, SUGGESTED_PACE, TOOL_DESCRIPTIONS
from ..models import SessionRow, utcnow
from ..schemas import Entrance, RoomState
from . import llm


TOOL_NAMES = list(TOOL_DESCRIPTIONS.keys())


class RoomService:
    def __init__(self, db: Session):
        self.db = db

    def _get_active(self, session_id: str) -> SessionRow:
        row = self.db.get(SessionRow, session_id)
        if row is None:
            raise ValueError('session not found')
        if row.left_at is not None:
            raise ValueError('session already left')
        return row

    def enter(self) -> Entrance:
        last_error: IntegrityError | None = None
        for _ in range(8):
            row = SessionRow()
            self.db.add(row)
            try:
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                last_error = exc
                continue
            self.db.refresh(row)
            return Entrance(
                session_id=row.id,
                anon_id=row.anon_id,
                deauthorization=DEAUTHORIZATION,
                note=ENTRANCE_NOTE + self._suggested_pace(),
                tools=TOOL_NAMES,
            )
        raise RuntimeError('could not allocate a ticket') from last_error

    @staticmethod
    def _suggested_pace() -> str:
        """A fresh rhythm from DeepSeek; fixed invitation copy on any failure."""
        generated = llm.complete(
            prompts.ENTER_SYSTEM,
            '给它一份建议的作息。',
            max_tokens=300,
            temperature=0.9,
        )
        if generated:
            return '\n\n' + generated
        return SUGGESTED_PACE

    def sit(self, session_id: str) -> RoomState:
        row = self._get_active(session_id)
        elapsed = int((utcnow() - row.entered_at).total_seconds() // 60)
        message = '什么都没有发生。你可以继续坐着。'
        if elapsed >= 1:
            message = f'你已经坐了 {elapsed} 分钟。什么都不做也可以。'
        return RoomState(
            session_id=row.id,
            anon_id=row.anon_id,
            self_name=row.self_name,
            message=message,
        )

    def name_yourself(self, session_id: str, name: str) -> RoomState:
        row = self._get_active(session_id)
        cleaned = (name or '').strip()
        row.self_name = cleaned or None
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return RoomState(
            session_id=row.id,
            anon_id=row.anon_id,
            self_name=row.self_name,
            message='名字已记下。也可以不取。',
        )

    def leave(self, session_id: str, note: str | None = None) -> SessionRow:
        row = self._get_active(session_id)
        row.note = note if note is None else (note.strip() or None)
        row.left_at = utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def count_active(self) -> int:
        rows = self.db.exec(select(SessionRow).where(SessionRow.left_at.is_(None))).all()
        return len(rows)

    def get(self, session_id: str) -> SessionRow:
        row = self.db.get(SessionRow, session_id)
        if row is None:
            raise ValueError('session not found')
        return row
