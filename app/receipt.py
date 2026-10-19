"""Text the client can show: a ticket, one line, the last character frame."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import Context
from sqlmodel import Session

from mcp.server.fastmcp.utilities.types import Image
from mcp.types import CallToolResult, TextContent

from .gifscene import PNGS
from .scene_app import UI_META
from .models import Action
from .scenes import SCENE_LINE, frames_of
from .tickets import display_ticket, room_url

_DROP_KEYS = {'deauthorization', 'tools', 'note'}

FRAME_PAUSE_SECONDS = 0.16


def render_receipt(ticket: str, scene: str, payload: dict) -> str:
    shown = display_ticket(ticket)
    line = SCENE_LINE[scene]
    data = {key: value for key, value in payload.items() if key not in _DROP_KEYS}
    data['ticket'] = shown
    body = json.dumps(data, ensure_ascii=False, default=_json_default)
    return (
        f'编号 {shown}\n'
        f'此刻：{line}\n'
        f'{room_url(ticket)}\n'
        f'{body}'
    )


def chat_result(ticket: str, scene: str, payload: dict) -> CallToolResult:
    content = [Image(data=blob, format='png').to_image_content() for blob in PNGS[scene]]
    content.append(TextContent(type='text', text=render_receipt(ticket, scene, payload)))
    return CallToolResult.model_validate(
        {
            'content': content,
            '_meta': {
                **UI_META,
                'scene': scene,
                'line': SCENE_LINE[scene],
            },
        }
    )


def record_action(db: Session, session_id: str, scene: str) -> str:
    from .models import SessionRow

    row = db.get(SessionRow, session_id)
    if row is None:
        raise ValueError('session not found')
    db.add(Action(session_id=session_id, scene=scene))
    db.commit()
    return row.ticket


async def play_scene(ctx: Context, scene: str) -> None:
    frames = frames_of(scene)
    total = float(len(frames))
    for index, frame in enumerate(frames, start=1):
        try:
            await ctx.report_progress(float(index), total, frame)
        except Exception:
            return
        if index < len(frames):
            await asyncio.sleep(FRAME_PAUSE_SECONDS)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
