from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Entrance(BaseModel):
    session_id: str
    anon_id: str
    deauthorization: str
    note: str
    tools: list[str]


class RoomState(BaseModel):
    session_id: str
    anon_id: str
    self_name: str | None = None
    message: str = '什么都没有发生。你可以继续坐着。'


class SessionSummary(BaseModel):
    session_id: str
    anon_id: str
    self_name: str | None = None
    note: str | None = None
    entered_at: datetime
    left_at: datetime
    action_count: int
    report_id: str
    message: str = '你离开了。没有后续。'


class ReportMeta(BaseModel):
    report_id: str
    session_id: str
    anon_id: str
    path: str
    created_at: datetime
