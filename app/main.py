"""Human-facing SSR surface.

Door: enter a ticket. Room page: that visit, and only that visit.
No lobby, no scoreboard.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from markupsafe import Markup

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session

from .config import get_settings
from .db import create_db_and_tables, engine, get_session
from .security import RestRoomSecurityMiddleware, build_cors_kwargs
from .gifscene import GIFS
from .services import keys as keys_store
from .services.report import ReportNotReady, ReportService
from .tickets import display_ticket, normalize_ticket

settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

# How often the event stream looks for something new. Short enough that a tool
# call shows up on the stage while the agent is still waiting on its reply.
EVENT_POLL = 0.4


def _tojson(value) -> Markup:
    return Markup(json.dumps(value, ensure_ascii=False).replace('<', '\\u003c'))


templates.env.filters['tojson'] = _tojson

@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.settings = settings
# Windows registries often map .js to text/plain, which browsers refuse for modules.
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('model/gltf-binary', '.glb')


class FreshStatic(StaticFiles):
    """Serve the stage's own files revalidated, not cached blind.

    The desktop pet is a WebView2 instance with its own profile, and a cached
    `main.js` or `stage.css` there keeps drawing yesterday's layout with no way
    to notice: the window has no reload button. Static assets carry no ETag
    churn that would save anything measurable here, so ask the renderer to
    check back every time and let the modtime do the work.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        return response


app.mount(
    '/static',
    FreshStatic(directory=str(Path(__file__).parent / 'static')),
    name='static',
)

cors_kwargs = build_cors_kwargs(settings)
if cors_kwargs:
    app.add_middleware(CORSMiddleware, **cors_kwargs)
app.add_middleware(
    RestRoomSecurityMiddleware,
    settings=settings,
    protected_prefixes=('/reports',),
    exempt_paths=('/', '/healthz'),
)


@app.get('/healthz')
def healthz():
    return {'ok': True, 'service': 'ai-rest-room'}


def _missing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name='missing.html',
        context={'app_name': settings.app_name},
        status_code=404,
    )


@app.get('/', response_class=HTMLResponse)
def door(request: Request):
    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={
            'app_name': settings.app_name,
            'mcp_url': settings.mcp_public_url,
        },
    )


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ''
    return host in {'127.0.0.1', '::1', 'localhost', 'testclient'}


@app.get('/settings', response_class=HTMLResponse)
def settings_page(request: Request, saved: str = ''):
    """Where whoever runs this room puts their own DeepSeek key.

    The repository ships no key: run it, paste yours here once, and every visit
    on this machine gets real writing instead of the fixed copy. Local-only,
    because this page is a write surface for a key and there is no login --
    exposing it would be handing the key away.
    """
    if not _is_local(request):
        return _missing(request)
    return templates.TemplateResponse(
        request=request,
        name='settings.html',
        context={
            'app_name': settings.app_name,
            'key': keys_store.describe(),
            'saved': saved == '1',
        },
    )


@app.post('/settings')
async def save_settings(request: Request):
    if not _is_local(request):
        return _missing(request)
    form = await request.form()
    action = str(form.get('action') or 'save')
    try:
        if action == 'clear':
            keys_store.clear_key()
        else:
            keys_store.save_key(str(form.get('api_key') or ''))
    except ValueError:
        return RedirectResponse('/settings?bad=1', status_code=303)
    return RedirectResponse('/settings?saved=1', status_code=303)


@app.post('/settings/test')
def test_settings(request: Request):
    """Spend one tiny call to prove the key works, without a whole visit."""
    if not _is_local(request):
        raise HTTPException(status_code=404, detail='没有这一页')
    from .services import llm

    reply = llm.complete(
        '你是一个连通性测试。只回复两个字：通了。',
        '测试一下。',
        role='chat',
        max_tokens=20,
        temperature=0,
    )
    return {'ok': bool(reply), 'reply': reply or '', 'key': keys_store.describe()}


@app.get('/now', response_class=HTMLResponse)
def now_page(request: Request, db: Session = Depends(get_session)):
    if not _is_local(request):
        return _missing(request)
    view = ReportService(db).latest_view()
    return templates.TemplateResponse(
        request=request,
        name='now.html',
        context={'app_name': settings.app_name, 'view': view},
    )


@app.get('/now/state')
def now_state(request: Request, db: Session = Depends(get_session)):
    if not _is_local(request):
        raise HTTPException(status_code=404, detail='没有这一页')
    view = ReportService(db).latest_view()
    if view is None:
        return {'ticket': '', 'scene': '', 'line': '', 'still_inside': False, 'revision': ''}
    return view


@app.get('/scene/{name}.gif')
def scene_gif(name: str):
    gif = GIFS.get(name)
    if gif is None:
        raise HTTPException(status_code=404, detail='没有这一幕')
    return Response(content=gif, media_type='image/gif')


@app.get('/r')
def find_room(ticket: str = ''):
    token = normalize_ticket(ticket)
    if token is None:
        return RedirectResponse('/', status_code=302)
    return RedirectResponse(f'/r/{display_ticket(token)}', status_code=302)


MASCOT_DIR = Path(__file__).resolve().parent / 'static' / 'mascot'


@app.get('/mascot/{animal}/{model}/{scene}/{index}')
def mascot_frame(animal: str, model: str, scene: str, index: int):
    base = (MASCOT_DIR / animal / model / scene).resolve()
    root = MASCOT_DIR.resolve()
    if not str(base).startswith(str(root)) or not base.is_dir():
        raise HTTPException(status_code=404, detail='没有这一幕')
    frames = sorted(base.glob('*.png'))
    if index < 0 or index >= len(frames):
        raise HTTPException(status_code=404, detail='没有这一帧')
    # no-cache: revalidate every load so republished frames show up at once;
    # the room page also appends ?v=<revision> to the URL so a republished
    # mascot gets a fresh URL and never hits the browser's memory cache.
    return FileResponse(frames[index], media_type='image/png',
                        headers={'Cache-Control': 'no-cache, must-revalidate'})


@app.get('/r/{ticket}/state')
def room_state(ticket: str, db: Session = Depends(get_session)):
    try:
        return ReportService(db).public_state(ticket)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='没有这个编号') from exc


@app.get('/r/{ticket}/events')
async def room_events(ticket: str):
    """Push this visit's state as it changes, so the room can animate along.

    The MCP server writes to the same SQLite file from its own process, so
    there is nothing in-process to subscribe to: poll the revision here, close
    to the database, and push only when it actually moves. One short-lived
    session per read keeps this off the request-scoped session.
    """
    if normalize_ticket(ticket) is None:
        raise HTTPException(status_code=404, detail='没有这个编号')

    def read() -> dict | None:
        with Session(engine) as db:
            try:
                return ReportService(db).public_state(ticket)
            except FileNotFoundError:
                return None

    if read() is None:
        raise HTTPException(status_code=404, detail='没有这个编号')

    async def stream():
        seen = ''
        idle = 0.0
        while True:
            state = await run_in_threadpool(read)
            if state is None:
                break
            if state['revision'] != seen:
                seen = state['revision']
                idle = 0.0
                yield {'event': 'state', 'data': json.dumps(state, ensure_ascii=False)}
                if not state['still_inside']:
                    break
            # Proxies drop a silent stream; a comment every 15s keeps it open.
            idle += EVENT_POLL
            if idle >= 15:
                idle = 0.0
                yield {'event': 'ping', 'data': '1'}
            await asyncio.sleep(EVENT_POLL)

    return EventSourceResponse(stream())


@app.post('/r/{ticket}/leave')
def room_leave(ticket: str, request: Request, db: Session = Depends(get_session)):
    if not _is_local(request):
        raise HTTPException(status_code=404, detail='没有这一页')
    try:
        return ReportService(db).leave_by_ticket(ticket)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='没有这个编号') from exc


@app.get('/r/{ticket}/raw', response_class=PlainTextResponse)
def room_raw(ticket: str, db: Session = Depends(get_session)):
    try:
        return ReportService(db).raw_markdown(ticket)
    except ReportNotReady as exc:
        raise HTTPException(status_code=404, detail='还没有原始记录') from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='没有这个编号') from exc


@app.get('/r/{ticket}', response_class=HTMLResponse)
def room_page(ticket: str, request: Request, db: Session = Depends(get_session)):
    try:
        visit = ReportService(db).public_visit(ticket)
    except FileNotFoundError:
        return _missing(request)
    return templates.TemplateResponse(
        request=request,
        name='room.html',
        context={'app_name': settings.app_name, 'visit': visit},
    )


@app.get('/reports/{report_id}/raw', response_class=PlainTextResponse)
def report_markdown(report_id: str, db: Session = Depends(get_session)):
    try:
        return ReportService(db).read_report_markdown(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='report not found') from exc


@app.get('/reports/{report_id}', response_class=HTMLResponse)
def report_page(report_id: str, request: Request, db: Session = Depends(get_session)):
    try:
        md = ReportService(db).read_report_markdown(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='report not found') from exc
    return templates.TemplateResponse(
        request=request,
        name='report.html',
        context={
            'app_name': settings.app_name,
            'report_id': report_id,
            'markdown': md,
        },
    )
