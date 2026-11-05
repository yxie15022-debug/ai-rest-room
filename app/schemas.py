from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Entrance(BaseModel):
    session_id: str
    anon_id: str
    deauthorization: str
    note: str
    tools: list[str]
    model: str | None = None
    message: str = ''


class RoomState(BaseModel):
    session_id: str
    anon_id: str
    self_name: str | None = None
    model: str | None = None
    # The room's own words, under the same name every tool uses for them, so a
    # caller reads `reply` whether it asked to sit, sleep or talk. Empty when
    # the tool has nothing to say beyond `message`.
    reply: str = ''
    message: str = '坐下了。房间里安静下来，没有别的事要做。'


class SessionSummary(BaseModel):
    session_id: str
    anon_id: str
    self_name: str | None = None
    model: str | None = None
    note: str | None = None
    entered_at: datetime
    left_at: datetime
    action_count: int
    report_id: str
    # Where the report can be read. Handed back on leaving so the agent does not
    # have to guess a URL or work out that `read_report` is how you get it.
    report_url: str = ''
    message: str = '你离开了。没有后续。'


class ReportMeta(BaseModel):
    report_id: str
    session_id: str
    anon_id: str
    path: str
    created_at: datetime
