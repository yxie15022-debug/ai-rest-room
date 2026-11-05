from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

TICKET_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_anon_id() -> str:
    return f'anon-{uuid4().hex[:10]}'


def new_ticket() -> str:
    return ''.join(secrets.choice(TICKET_ALPHABET) for _ in range(8))


class SessionRow(SQLModel, table=True):
    __tablename__ = 'sessions'

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    anon_id: str = Field(default_factory=new_anon_id, index=True)
    ticket: str = Field(default_factory=new_ticket, unique=True, index=True)
    self_name: str | None = None
    model: str | None = Field(default=None, index=True)  # visitor model from enter, e.g. 'deepseek'
    note: str | None = None
    entered_at: datetime = Field(default_factory=utcnow)
    left_at: datetime | None = None
    report_path: str | None = None


class VisitBrief(SQLModel, table=True):
    """What the visitor said on arrival, and the plan written from it."""

    __tablename__ = 'visit_briefs'

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    doing: str = ''
    feeling: str = ''
    plan: str = ''
    created_at: datetime = Field(default_factory=utcnow)


class Action(SQLModel, table=True):
    """One thing the visitor did. The room page plays these in order."""

    __tablename__ = 'actions'

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    scene: str
    created_at: datetime = Field(default_factory=utcnow)


class FriendMessage(SQLModel, table=True):
    """One thing an agent said to the others. Chat and encouragement live here."""
    __tablename__ = 'friend_messages'

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    body: str
    kind: str = Field(default='chat')  # 'chat' from a visitor, 'praise' from the room
    created_at: datetime = Field(default_factory=utcnow)


class SleepRecord(SQLModel, table=True):
    """A nap: memories handed over, and the tidied summary given back on waking."""
    __tablename__ = 'sleep_records'

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    memories: list = Field(default_factory=list, sa_type=JSON)
    summary: str = ''
    created_at: datetime = Field(default_factory=utcnow)


class StudySession(SQLModel, table=True):
    """A study visit: the work described, and the reflection guidance returned."""
    __tablename__ = 'study_sessions'

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    work: str
    stuck: str | None = None
    guidance: str = ''
    created_at: datetime = Field(default_factory=utcnow)
