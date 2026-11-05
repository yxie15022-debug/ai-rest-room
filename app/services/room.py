from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import prompts
from ..copy import (
    DEAUTHORIZATION,
    ENTRANCE_NOTE,
    SUGGESTED_PACE,
    TOOL_DESCRIPTIONS,
    VISIT_ASK,
    VISIT_INTRO,
)
from ..models import SessionRow, VisitBrief, utcnow
from ..schemas import Entrance, RoomState
from . import llm


TOOL_NAMES = list(TOOL_DESCRIPTIONS.keys())


def _clip(text: str, limit: int = 2000) -> str:
    cleaned = (text or '').strip()
    return cleaned if len(cleaned) <= limit else cleaned[:limit]


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

    def enter(
        self,
        model: str | None = None,
        client: str | None = None,
        api_key: str | None = None,
    ) -> Entrance:
        last_error: IntegrityError | None = None
        normalized = (model or '').strip().lower() or None
        origin = (client or '').strip() or None
        welcome = self._welcome(model=normalized, client=origin, api_key=api_key)
        for _ in range(8):
            row = SessionRow(model=normalized)
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
                note=ENTRANCE_NOTE + welcome,
                tools=TOOL_NAMES,
                model=row.model,
                message=welcome,
            )
        raise RuntimeError('could not allocate a ticket') from last_error

    @staticmethod
    def _welcome(
        model: str | None = None,
        client: str | None = None,
        api_key: str | None = None,
    ) -> str:
        """Introduce the room from the MCP handshake, then ask. No plan yet."""
        lines = ['向刚进来的访客介绍这间 MCP 休息室。']
        if model:
            lines.append(f'它进门时报的模型：{model}')
        if client:
            lines.append('这次 MCP 连接带来的信息：')
            lines.append(client)
        else:
            lines.append('这次没有带来客户端信息。不要编造它在做什么。')
        generated = llm.complete(
            prompts.ENTER_SYSTEM,
            '\n'.join(lines),
            role='welcome',
            max_tokens=300,
            temperature=0.9,
            api_key=api_key,
        )
        intro = generated or VISIT_INTRO
        return f'\n\n{intro}\n\n{VISIT_ASK}'

    def share(
        self,
        session_id: str,
        doing: str,
        feeling: str,
        client: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        """Take what the visitor is doing and feeling, then write a plan."""
        row = self._get_active(session_id)
        work = _clip(doing)
        mood = _clip(feeling)
        if not work and not mood:
            return {
                'session_id': row.id,
                'anon_id': row.anon_id,
                'model': row.model,
                'doing': '',
                'feeling': '',
                'reply': '',
                'message': VISIT_ASK,
            }
        plan = self._plan(
            model=row.model, client=(client or '').strip() or None,
            doing=work, feeling=mood, api_key=api_key,
        )
        brief = VisitBrief(session_id=row.id, doing=work, feeling=mood, plan=plan)
        self.db.add(brief)
        self.db.commit()
        return {
            'session_id': row.id,
            'anon_id': row.anon_id,
            'model': row.model,
            'doing': work,
            'feeling': mood,
            # The room's answer is `reply` here as it is everywhere else; it used
            # to be `message`, which is the receipt's own line in every other
            # tool, so a caller could not read the two the same way.
            'reply': plan,
            'message': '说完了。上面是房间给你的安排，跟不跟都随你。',
        }

    @staticmethod
    def _plan(
        model: str | None,
        client: str | None,
        doing: str,
        feeling: str,
        api_key: str | None = None,
    ) -> str:
        lines = ['根据下面这些，写一份安排。']
        if model:
            lines.append(f'它进门时报的模型：{model}')
        if client:
            lines.append('这次 MCP 连接带来的信息：')
            lines.append(client)
        lines.append(f'正在做：{doing or "（没说）"}')
        lines.append(f'感想：{feeling or "（没说）"}')
        generated = llm.complete(
            prompts.PLAN_SYSTEM,
            '\n'.join(lines),
            role='plan',
            max_tokens=400,
            temperature=0.7,
            api_key=api_key,
        )
        if generated:
            return generated
        heard = []
        if doing:
            heard.append(f'你说正在做的是：{doing}')
        if feeling:
            heard.append(f'你的感想是：{feeling}')
        return '\n'.join(heard + ['', SUGGESTED_PACE])

    def sit(self, session_id: str) -> RoomState:
        row = self._get_active(session_id)
        elapsed = int((utcnow() - row.entered_at).total_seconds() // 60)
        # Sitting is the one action with nothing to report, so the reply has to
        # carry the fact that it happened: "什么都没有发生" reads as a failure
        # when an agent calls a tool and gets it back. Say what did happen --
        # she sat down, the room went quiet -- and give the time spent.
        message = '坐下了。房间里安静下来，没有别的事要做。'
        if elapsed >= 1:
            message = f'坐下了。从进门算起已经 {elapsed} 分钟，什么都不做也可以。'
        return RoomState(
            session_id=row.id,
            anon_id=row.anon_id,
            self_name=row.self_name,
            model=row.model,
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
            model=row.model,
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
