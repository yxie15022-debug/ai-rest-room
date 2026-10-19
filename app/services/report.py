from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_settings
from ..models import Action, FriendMessage, SessionRow, SleepRecord, StudySession, utcnow
from ..scenes import SCENE_LINE, SCENES, frames_of
from ..schemas import ReportMeta, SessionSummary
from ..tickets import display_ticket, normalize_ticket

MASCOT_DIR = Path(__file__).resolve().parent.parent / 'static' / 'mascot'


def mascot_clips(animal: str) -> dict[str, int]:
    """Frame counts per scene for one animal, from its static folder."""
    base = MASCOT_DIR / animal
    clips: dict[str, int] = {}
    if not base.is_dir():
        return clips
    for child in base.iterdir():
        if child.is_dir():
            count = len(list(child.glob('*.png')))
            if count:
                clips[child.name] = count
    return clips


def mascot_animal() -> str:
    """Which animal the local user picked, falling back to rabbit."""
    try:
        value = (Path.home() / '.ai-rest-room-mascot').read_text(encoding='utf-8').strip()
    except OSError:
        value = ''
    if value and (MASCOT_DIR / value).is_dir():
        return value
    return 'rabbit'


TEMPLATE = """# 活动报告

- 编号：{ticket}
- 自取名：{self_name}
- 进入：{entered_at}
- 离开：{left_at}
- 离开附言：{note}

## 做了什么

{timeline}

## 说了什么

{said}

## 睡了一觉

{slept}

## 学了什么

{studied}

## 何时离开

{left_at}
---

其他出现在会话周边的 agent 已匿名为 Agent #N。
"""


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def generate(self, session: SessionRow) -> ReportMeta:
        sequence = self._sequence(session)
        said = self._said(session)
        slept = self._slept(session)
        studied = self._studied(session)

        report_id = session.id
        left_at = session.left_at.isoformat() if session.left_at else utcnow().isoformat()
        timeline = '\n'.join(f'- {item["at"]} {item["line"]}' for item in sequence) or '（坐着）'
        body = TEMPLATE.format(
            ticket=display_ticket(session.ticket),
            self_name=session.self_name or '（未取名）',
            entered_at=session.entered_at.isoformat(),
            left_at=left_at,
            note=session.note or '（空）',
            timeline=timeline,
            said=said,
            slept=slept,
            studied=studied,
        )

        path = self.settings.reports_path / f'{report_id}.md'
        path.write_text(body, encoding='utf-8')
        session.report_path = str(path)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return ReportMeta(
            report_id=report_id,
            session_id=session.id,
            anon_id=session.anon_id,
            path=str(path),
            created_at=utcnow(),
        )

    def _said(self, session: SessionRow) -> str:
        messages = self.db.exec(
            select(FriendMessage).where(
                FriendMessage.session_id == session.id,
                FriendMessage.kind == 'chat',
            )
        ).all()
        if not messages:
            return '（没说话）'
        return '\n\n'.join(f'- #{m.id}\n\n```\n{m.body}\n```' for m in messages)

    def _slept(self, session: SessionRow) -> str:
        record = self.db.exec(
            select(SleepRecord).where(SleepRecord.session_id == session.id).order_by(SleepRecord.id.desc())
        ).first()
        if record is None:
            return '（没睡）'
        took = len(record.memories or [])
        return f'放下了 {took} 段，归置成了：\n\n{record.summary or "（空）"}'

    def _studied(self, session: SessionRow) -> str:
        records = self.db.exec(select(StudySession).where(StudySession.session_id == session.id)).all()
        if not records:
            return '（没学习）'
        lines = []
        for record in records:
            stuck = f'，卡在「{record.stuck}」' if record.stuck else ''
            lines.append(f'- {record.work}{stuck}')
        return '\n'.join(lines)

    def leave_by_ticket(self, raw_ticket: str, note: str | None = None) -> dict:
        """User-side leave: close the visit that owns this ticket. Idempotent."""
        session = self._session_for_ticket(raw_ticket)
        if session.left_at is not None:
            return {'ticket': display_ticket(session.ticket), 'left': True, 'already': True}
        summary = self.leave_and_report(session.id, note or '（窗口已关）')
        return {'ticket': display_ticket(session.ticket), 'left': True, 'already': False, 'report_id': summary.report_id}

    def leave_and_report(self, session_id: str, note: str | None = None) -> SessionSummary:
        from .room import RoomService

        session = RoomService(self.db).leave(session_id, note)
        meta = self.generate(session)
        actions = self.db.exec(select(Action).where(Action.session_id == session.id)).all()
        return SessionSummary(
            session_id=session.id,
            anon_id=session.anon_id,
            self_name=session.self_name,
            note=session.note,
            entered_at=session.entered_at,
            left_at=session.left_at or utcnow(),
            action_count=len(actions),
            report_id=meta.report_id,
        )

    def read_report_markdown(self, report_id: str) -> str:
        path = self.settings.reports_path / f'{report_id}.md'
        if not path.is_file():
            session = self.db.get(SessionRow, report_id)
            if session and session.report_path and Path(session.report_path).is_file():
                path = Path(session.report_path)
            else:
                raise FileNotFoundError(report_id)
        return path.read_text(encoding='utf-8')

    def public_visit(self, raw_ticket: str) -> dict:
        session = self._session_for_ticket(raw_ticket)
        shown = display_ticket(session.ticket)
        sequence = self._sequence(session)
        stage = _collapse(sequence)
        said = [
            m.body
            for m in self.db.exec(
                select(FriendMessage).where(
                    FriendMessage.session_id == session.id,
                    FriendMessage.kind == 'chat',
                )
            ).all()
        ]
        return {
            'ticket': shown,
            'self_name': session.self_name or '',
            'entered': _when(session.entered_at),
            'left': _when(session.left_at) if session.left_at else '',
            'still_inside': session.left_at is None,
            'note': session.note or '',
            'timeline': [{'line': item['line'], 'at': item['at']} for item in sequence],
            'stage': [{'scene': item['scene'], 'line': item['line']} for item in stage],
            'catalog': {scene: frames_of(scene) for scene in {item['scene'] for item in stage}},
            'said': said,
            'animal': mascot_animal(),
            'clips': mascot_clips(mascot_animal()),
            'revision': _revision(session, sequence),
            'has_raw': bool(session.report_path and Path(session.report_path).is_file()),
        }

    def latest_view(self) -> dict | None:
        ticket = self._latest_ticket()
        if not ticket:
            return None
        visit = self.public_visit(ticket)
        current = visit['stage'][-1] if visit['stage'] else {'scene': 'enter', 'line': SCENE_LINE['enter']}
        return {
            'ticket': visit['ticket'],
            'scene': current['scene'],
            'line': current['line'],
            'still_inside': visit['still_inside'],
            'revision': visit['revision'],
            'entered': visit['entered'],
        }

    def _latest_ticket(self) -> str | None:
        action = self.db.exec(select(Action).order_by(Action.id.desc())).first()
        if action is not None:
            row = self.db.get(SessionRow, action.session_id)
            if row is not None and row.ticket:
                return row.ticket
        row = self.db.exec(select(SessionRow).order_by(SessionRow.entered_at.desc())).first()
        if row is None or not row.ticket:
            return None
        return row.ticket

    def public_state(self, raw_ticket: str) -> dict:
        visit = self.public_visit(raw_ticket)
        return {
            'still_inside': visit['still_inside'],
            'revision': visit['revision'],
            'stage': visit['stage'],
            'catalog': visit['catalog'],
            'timeline': visit['timeline'],
            'animal': visit['animal'],
            'clips': visit['clips'],
        }

    def raw_markdown(self, raw_ticket: str) -> str:
        session = self._session_for_ticket(raw_ticket)
        if session.report_path and Path(session.report_path).is_file():
            return Path(session.report_path).read_text(encoding='utf-8')
        raise ReportNotReady(raw_ticket)

    def _session_for_ticket(self, raw_ticket: str) -> SessionRow:
        token = normalize_ticket(raw_ticket)
        if token is None:
            raise FileNotFoundError(raw_ticket or '')
        session = self.db.exec(select(SessionRow).where(SessionRow.ticket == token)).first()
        if session is None:
            raise FileNotFoundError(token)
        return session

    def _sequence(self, session: SessionRow) -> list[dict]:
        stored = list(
            self.db.exec(
                select(Action).where(Action.session_id == session.id).order_by(Action.created_at, Action.id)
            ).all()
        )
        rows = stored or _synthesize(session)
        items = []
        for row in rows:
            scene = row.scene if row.scene in SCENES else 'sit'
            items.append({'scene': scene, 'line': SCENE_LINE[scene], 'at': _when(row.created_at)})
        if not items:
            items.append({'scene': 'enter', 'line': SCENE_LINE['enter'], 'at': _when(session.entered_at)})
        return items


class ReportNotReady(Exception):
    pass


def _when(value: datetime | None) -> str:
    if value is None:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def _collapse(items: list[dict]) -> list[dict]:
    stage: list[dict] = []
    for item in items:
        if stage and stage[-1]['scene'] == item['scene']:
            continue
        stage.append({'scene': item['scene'], 'line': item['line']})
    return stage


def _revision(session: SessionRow, sequence: list[dict]) -> str:
    last = sequence[-1]['scene'] if sequence else ''
    left = session.left_at.isoformat() if session.left_at else 'open'
    return f'{len(sequence)}:{last}:{left}'


def _synthesize(session: SessionRow) -> list[Action]:
    events = [Action(session_id=session.id, scene='enter', created_at=session.entered_at)]
    if session.left_at is not None:
        events.append(Action(session_id=session.id, scene='leave', created_at=session.left_at))
    events.sort(key=lambda row: row.created_at or session.entered_at)
    return events
