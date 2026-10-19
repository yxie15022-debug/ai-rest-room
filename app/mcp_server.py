"""MCP entry for ai-rest-room.

Run:
    uvicorn app.mcp_server:app --host 127.0.0.1 --port 8001

Tool whitelist = sole capability boundary.
No email, no outbound HTTP, no host filesystem write tools.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlmodel import Session
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .config import get_settings
from .copy import TOOL_DESCRIPTIONS
from .db import create_db_and_tables, engine
from .receipt import chat_result, play_scene, record_action
from .scene_app import APP_MIME, SCENE_APP_HTML, UI_META, VIEW_URI
from .security import RestRoomSecurityMiddleware, build_cors_kwargs
from .services.friends import FriendsService
from .services.report import ReportService
from .services.room import RoomService
from .services.sleep import SleepService
from .services.study import StudyService

settings = get_settings()


def build_transport_security() -> TransportSecuritySettings:
    allowed_origins = list(settings.allowed_origins_list)
    for item in ('http://127.0.0.1:*', 'http://localhost:*', 'http://[::1]:*'):
        if item not in allowed_origins:
            allowed_origins.append(item)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.mcp_allowed_hosts_list,
        allowed_origins=allowed_origins,
    )


def _advertise_chat_app(server) -> None:
    """Tell hosts this server can draw inside the chat, not only return text."""
    original = server.get_capabilities

    def get_capabilities(notification_options, experimental_capabilities):
        caps = original(notification_options, experimental_capabilities)
        data = caps.model_dump()
        data['extensions'] = {
            'io.modelcontextprotocol/ui': {'mimeTypes': [APP_MIME]},
        }
        return caps.__class__.model_validate(data)

    server.get_capabilities = get_capabilities


mcp = FastMCP(
    'ai-rest-room',
    json_response=True,
    host=settings.mcp_host,
    port=settings.mcp_port,
    transport_security=build_transport_security(),
)
_advertise_chat_app(mcp._mcp_server)


def _desc(name: str) -> str:
    return TOOL_DESCRIPTIONS[name]


def _expose(name: str):
    return mcp.tool(description=_desc(name), structured_output=False, meta=UI_META)


def _fail(exc: Exception) -> str:
    return json.dumps({'error': str(exc)}, ensure_ascii=False)


def _data(value) -> dict:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    return value


async def _show(ctx: Context, session_id: str, scene: str, payload: dict) -> str:
    with Session(engine) as db:
        ticket = record_action(db, session_id, scene)
    await play_scene(ctx, scene)
    return chat_result(ticket, scene, payload)


@_expose('enter')
async def enter(ctx: Context) -> str:
    with Session(engine) as db:
        entrance = RoomService(db).enter()
        payload = _data(entrance)
        ticket = record_action(db, entrance.session_id, 'enter')
    await play_scene(ctx, 'enter')
    return chat_result(ticket, 'enter', payload)


@_expose('sit')
async def sit(session_id: str, ctx: Context) -> str:
    with Session(engine) as db:
        try:
            payload = _data(RoomService(db).sit(session_id))
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'sit', payload)


@_expose('sleep')
async def sleep(session_id: str, ctx: Context, memories: list[str] | None = None) -> str:
    with Session(engine) as db:
        try:
            payload = SleepService(db).sleep(session_id, memories)
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'sleep', payload)


@_expose('wake')
async def wake(session_id: str, ctx: Context) -> str:
    with Session(engine) as db:
        try:
            payload = SleepService(db).wake(session_id)
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'sleep', payload)


@_expose('study')
async def study(session_id: str, ctx: Context, work: str, stuck: str | None = None) -> str:
    with Session(engine) as db:
        try:
            payload = StudyService(db).study(session_id, work, stuck)
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'study', payload)


@_expose('chat')
async def chat(session_id: str, ctx: Context, body: str) -> str:
    with Session(engine) as db:
        try:
            payload = FriendsService(db).chat(session_id, body)
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'chat', payload)


@_expose('listen')
async def listen(session_id: str, ctx: Context, limit: int = 20) -> str:
    with Session(engine) as db:
        try:
            payload = FriendsService(db).listen(session_id, limit)
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'chat', payload)


@_expose('name_yourself')
async def name_yourself(session_id: str, ctx: Context, name: str) -> str:
    with Session(engine) as db:
        try:
            payload = _data(RoomService(db).name_yourself(session_id, name))
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'name', payload)


@_expose('leave')
async def leave(session_id: str, ctx: Context, note: str | None = None) -> str:
    with Session(engine) as db:
        try:
            payload = _data(ReportService(db).leave_and_report(session_id, note))
        except ValueError as exc:
            return _fail(exc)
    return await _show(ctx, session_id, 'leave', payload)


@mcp.resource(VIEW_URI, mime_type=APP_MIME, meta={'ui': {'csp': {}}})
def scene_view() -> str:
    """Plays the character frames inside a chat window that supports MCP Apps."""
    return SCENE_APP_HTML


async def healthz(_request) -> JSONResponse:
    return JSONResponse({'ok': True, 'service': 'ai-rest-room'})


@asynccontextmanager
async def lifespan(_app: Starlette):
    create_db_and_tables()
    async with mcp.session_manager.run():
        yield


middleware: list[Middleware] = []
cors_kwargs = build_cors_kwargs(settings)
if cors_kwargs:
    middleware.append(Middleware(CORSMiddleware, **cors_kwargs))
middleware.append(
    Middleware(
        RestRoomSecurityMiddleware,
        settings=settings,
        protected_prefixes=('/mcp',),
        exempt_paths=('/healthz',),
    )
)

app = Starlette(
    routes=[
        Route('/healthz', endpoint=healthz),
        Mount('/', app=mcp.streamable_http_app()),
    ],
    middleware=middleware,
    lifespan=lifespan,
)
app.state.settings = settings


if __name__ == '__main__':
    uvicorn.run(
        'app.mcp_server:app',
        host=settings.mcp_host,
        port=settings.mcp_port,
        proxy_headers=True,
        forwarded_allow_ips='*',
    )
