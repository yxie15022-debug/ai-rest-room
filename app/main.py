"""Human-facing SSR surface.

Door: enter a ticket. Room page: that visit, and only that visit.
No lobby, no scoreboard.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from markupsafe import Markup

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from .config import get_settings
from .db import create_db_and_tables, get_session
from .security import RestRoomSecurityMiddleware, build_cors_kwargs
from .gifscene import GIFS
from .services.report import ReportNotReady, ReportService
from .tickets import display_ticket, normalize_ticket

settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))


def _tojson(value) -> Markup:
    return Markup(json.dumps(value, ensure_ascii=False).replace('<', '\\u003c'))


templates.env.filters['tojson'] = _tojson

@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.settings = settings

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


@app.get('/mascot/{animal}/{scene}/{index}')
def mascot_frame(animal: str, scene: str, index: int):
    base = (MASCOT_DIR / animal / scene).resolve()
    root = MASCOT_DIR.resolve()
    if not str(base).startswith(str(root)) or not base.is_dir():
        raise HTTPException(status_code=404, detail='没有这一幕')
    frames = sorted(base.glob('*.png'))
    if index < 0 or index >= len(frames):
        raise HTTPException(status_code=404, detail='没有这一帧')
    return FileResponse(frames[index], media_type='image/png')


@app.get('/r/{ticket}/state')
def room_state(ticket: str, db: Session = Depends(get_session)):
    try:
        return ReportService(db).public_state(ticket)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='没有这个编号') from exc


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
