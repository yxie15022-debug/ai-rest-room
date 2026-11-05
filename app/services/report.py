from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_settings
from ..models import Action, FriendMessage, SessionRow, SleepRecord, StudySession, VisitBrief, utcnow
from ..scenes import SCENE_LINE, SCENES, frames_of
from ..schemas import ReportMeta, SessionSummary
from ..tickets import display_ticket, normalize_ticket

MASCOT_DIR = Path(__file__).resolve().parent.parent / 'static' / 'mascot'


STORY_SCENES = ('enter', 'sleep', 'study', 'chat')
PLAY_MODE = {'enter': 'once', 'sleep': 'once', 'study': 'once', 'chat': 'once', 'sit': 'loop'}


def mascot_clips(animal: str, model: str | None = None) -> dict[str, int]:
    """Frame counts for one animal.

    Low-poly visitors live at {animal}/{model}/{scene}/. Older animals stay
    at {animal}/{scene}/, used when the model folder is absent.
    """
    base = MASCOT_DIR / animal
    clips: dict[str, int] = {}
    if not base.is_dir():
        return clips
    from ..characters import resolve
    model_dir = base / resolve(model)
    if model_dir.is_dir() and any((model_dir / name).is_dir() for name in ('enter', 'sit', 'sleep')):
        for child in model_dir.iterdir():
            if child.is_dir():
                count = len(list(child.glob('*.png')))
                if count:
                    clips[child.name] = count
        return clips
    for child in base.iterdir():
        if child.is_dir() and not child.name.startswith('_'):
            count = len(list(child.glob('*.png')))
            if count:
                clips[child.name] = count
    return clips


def mascot_animal() -> str:
    """Which animal the local user picked, falling back to rabbit.

    AI_REST_ROOM_MASCOT wins when set, so containers and sandboxed runs can
    choose an animal without writing to the server's home directory.
    """
    value = (os.environ.get('AI_REST_ROOM_MASCOT') or '').strip()
    if not value:
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

## 进门时说的

{shared}

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
        shared = self._shared(session)
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
            shared=shared,
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

    def _shared(self, session: SessionRow) -> str:
        brief = self.db.exec(
            select(VisitBrief).where(VisitBrief.session_id == session.id).order_by(VisitBrief.id.desc())
        ).first()
        if brief is None:
            return '（还没说）'
        doing = brief.doing or '（没说）'
        feeling = brief.feeling or '（没说）'
        return f'正在做：{doing}\n\n感想：{feeling}\n\n安排：\n\n{brief.plan or "（空）"}'

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
            model=session.model,
            note=session.note,
            entered_at=session.entered_at,
            left_at=session.left_at or utcnow(),
            action_count=len(actions),
            report_id=meta.report_id,
            # Handed over with the goodbye: an agent that never learns the report
            # exists cannot ask for it, and `read_report` is only useful to
            # someone who knows to call it.
            report_url=f'{self.settings.public_base_url.rstrip("/")}/reports/{meta.report_id}',
            message=(
                '你离开了。这一趟的记录留在这里：'
                f'{self.settings.public_base_url.rstrip("/")}/reports/{meta.report_id}'
                '（想用工具读全文，call read_report，ticket 用上面那个编号。）'
            ),
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

    def report_for_ticket(self, raw_ticket: str) -> tuple[str, str] | None:
        """The report for a finished visit, by its public ticket.

        None rather than an exception when there is no report yet: not having
        left is the ordinary case, not an error, and the caller explains it.
        """
        cleaned = (raw_ticket or '').strip().upper().replace('-', '')
        if not cleaned:
            return None
        session = self.db.exec(select(SessionRow).where(SessionRow.ticket == cleaned)).first()
        if session is None or not session.report_path:
            return None
        try:
            markdown = self.read_report_markdown(session.id)
        except FileNotFoundError:
            return None
        return session.id, markdown

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
        animal = mascot_animal()
        model = session.model
        voices = self._voices(session)
        return {
            'ticket': shown,
            'self_name': session.self_name or '',
            'model': model or '',
            'entered': _when(session.entered_at),
            'left': _when(session.left_at) if session.left_at else '',
            'still_inside': session.left_at is None,
            'note': session.note or '',
            'timeline': [
                {'scene': item['scene'], 'line': item['line'], 'at': item['at']} for item in sequence
            ],
            'stage': [{'scene': item['scene'], 'line': item['line']} for item in stage],
            'catalog': {scene: frames_of(scene) for scene in {item['scene'] for item in stage}},
            'said': said,
            'animal': animal,
            'clips': mascot_clips(animal, model),
            'play_mode': dict(PLAY_MODE),
            'dialogue': self._dialogue(session),
            'voices': voices,
            'revision': _revision(session, sequence, voices),
            'has_raw': bool(session.report_path and Path(session.report_path).is_file()),
        }

    def _dialogue(self, session: SessionRow) -> list[dict]:
        """Real interaction text for the room-page bubbles."""
        items: list[dict] = []
        studies = self.db.exec(
            select(StudySession).where(StudySession.session_id == session.id).order_by(StudySession.id)
        ).all()
        for record in studies:
            if record.work:
                items.append({'scene': 'study', 'text': record.work})
        sleeps = self.db.exec(
            select(SleepRecord).where(SleepRecord.session_id == session.id).order_by(SleepRecord.id)
        ).all()
        for record in sleeps:
            for mem in record.memories or []:
                if str(mem).strip():
                    items.append({'scene': 'sleep', 'text': str(mem)})
        chats = self.db.exec(
            select(FriendMessage).where(
                FriendMessage.session_id == session.id, FriendMessage.kind == 'chat'
            ).order_by(FriendMessage.id)
        ).all()
        for message in chats:
            if message.body:
                items.append({'scene': 'chat', 'text': message.body})
        return items

    def _voices(self, session: SessionRow) -> list[dict]:
        """Who said what, in order, for the animated room.

        `dialogue` only carries the visitor's own words. The stage also shows
        what the visitor was thinking, and what the room (DeepSeek, standing in
        as the visitor's teacher) said back, so both voices need to be here --
        and in the order they happened, because the stage replays them.

        One tool call produces several lines at once: what she was doing, what
        she felt, and the room's answer. They share a `created_at`, so replaying
        them by that timestamp alone puts all three on screen in the same
        instant -- a wall of text appearing at once instead of a conversation.
        Each line therefore carries a `beat` too: its place in the queue within
        that moment, which the stage uses to space them out.
        """
        items: list[dict] = []
        # Running count of every line in this visit, so `beat` orders them
        # globally as well as within a batch.
        beat = 0

        def add(at, who: str, kind: str, scene: str, text) -> None:
            body = str(text or '').strip()
            if body:
                items.append({
                    'at': at, 'who': who, 'kind': kind, 'scene': scene,
                    'text': body, 'beat': 0,
                })

        def flush_batch() -> None:
            """Number the lines added since the last batch.

            A batch is one tool call: everything added between two calls to
            `flush_batch`. The room's answer goes last within its batch, so the
            visitor is never cut off by the reply arriving first.

            `beat` is a running count across the whole visit, not a per-moment
            index: two tool calls in the same second would otherwise both start
            at 0 and lose their order.
            """
            nonlocal beat
            pending = [i for i in items if not i.get('_done')]
            # Stable sort keeps the visitor's own lines ahead of the reply.
            pending.sort(key=lambda i: i['who'] != 'visitor')
            for item in pending:
                item['beat'] = beat
                item['_done'] = True
                beat += 1

        for brief in self.db.exec(
            select(VisitBrief).where(VisitBrief.session_id == session.id).order_by(VisitBrief.id)
        ).all():
            add(brief.created_at, 'visitor', 'say', 'plan', brief.doing)
            add(brief.created_at, 'visitor', 'think', 'plan', brief.feeling)
            add(brief.created_at, 'teacher', 'say', 'plan', brief.plan)
            flush_batch()

        for record in self.db.exec(
            select(StudySession).where(StudySession.session_id == session.id).order_by(StudySession.id)
        ).all():
            add(record.created_at, 'visitor', 'say', 'study', record.work)
            add(record.created_at, 'visitor', 'think', 'study', record.stuck)
            add(record.created_at, 'teacher', 'say', 'study', record.guidance)
            flush_batch()

        for record in self.db.exec(
            select(SleepRecord).where(SleepRecord.session_id == session.id).order_by(SleepRecord.id)
        ).all():
            for memory in record.memories or []:
                add(record.created_at, 'visitor', 'say', 'sleep', memory)
            add(record.created_at, 'teacher', 'say', 'sleep', record.summary)
            flush_batch()

        for message in self.db.exec(
            select(FriendMessage).where(FriendMessage.session_id == session.id).order_by(FriendMessage.id)
        ).all():
            who = 'teacher' if message.kind == 'praise' else 'visitor'
            add(message.created_at, who, 'say', 'chat', message.body)
            flush_batch()

        items.sort(key=lambda item: (item['at'] or session.entered_at, item['beat']))
        return [
            {
                'who': i['who'], 'kind': i['kind'], 'scene': i['scene'],
                'text': i['text'], 'at': _when(i['at']), 'beat': i['beat'],
            }
            for i in items
        ]

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
            'model': visit['model'],
            # Who is speaking. The room signs its bubbles with this, so a visit
            # by an agent that named itself is not labelled by its model.
            'self_name': visit['self_name'],
            'clips': visit['clips'],
            'play_mode': visit['play_mode'],
            'dialogue': visit['dialogue'],
            'voices': visit['voices'],
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


def _revision(session: SessionRow, sequence: list[dict], voices: list[dict] | None = None) -> str:
    """Changes whenever the room has something new to show.

    The voice count matters on its own: DeepSeek writes a sleep summary from a
    background thread, well after the action that triggered it was recorded.

    The last `beat` is included too. Two tool calls can land in the same second,
    and the count alone would then be the same either way -- the stage would not
    know there was a new line to say.
    """
    last = sequence[-1]['scene'] if sequence else ''
    left = session.left_at.isoformat() if session.left_at else 'open'
    count = len(voices or [])
    beat = voices[-1]['beat'] if voices else 0
    return f'{len(sequence)}:{last}:{left}:{count}:{beat}'


def _synthesize(session: SessionRow) -> list[Action]:
    events = [Action(session_id=session.id, scene='enter', created_at=session.entered_at)]
    if session.left_at is not None:
        events.append(Action(session_id=session.id, scene='leave', created_at=session.left_at))
    events.sort(key=lambda row: row.created_at or session.entered_at)
    return events
