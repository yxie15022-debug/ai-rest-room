import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import ensure_ticket_column
from app.models import TICKET_ALPHABET, Action, SessionRow
from app.receipt import chat_result, play_scene, render_receipt
from app.scenes import HEIGHT, PALETTE, SCENES, WIDTH, frames_of
from app.services.report import ReportService
from app.services.room import RoomService
from app.tickets import display_ticket, normalize_ticket


def _memory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class TicketTest(unittest.TestCase):
    def test_alphabet_and_display(self):
        for missing in ('I', 'L', 'O', 'U'):
            self.assertNotIn(missing, TICKET_ALPHABET)
        self.assertEqual(normalize_ticket('7k4m-qp2x'), '7K4MQP2X')
        self.assertEqual(normalize_ticket('ilou-1111'), '110V1111')
        self.assertIsNone(normalize_ticket('nope'))
        self.assertEqual(display_ticket('7K4MQP2X'), '7K4M-QP2X')

    def test_enter_tickets_are_unique(self):
        engine = _memory()
        with Session(engine) as db:
            first = RoomService(db).enter()
            second = RoomService(db).enter()
            left = db.get(SessionRow, first.session_id)
            right = db.get(SessionRow, second.session_id)
            self.assertEqual(len(left.ticket), 8)
            self.assertNotEqual(left.ticket, right.ticket)
            self.assertTrue(set(left.ticket) <= set(TICKET_ALPHABET))

    def test_backfill_existing_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(f'sqlite:///{Path(tmp) / "old.db"}')
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE sessions (id TEXT PRIMARY KEY, anon_id TEXT)'))
                conn.execute(
                    text("INSERT INTO sessions (id, anon_id) VALUES ('s1', 'anon-1'), ('s2', 'anon-2')")
                )
            ensure_ticket_column(engine)
            with engine.connect() as conn:
                tickets = [row[0] for row in conn.execute(text('SELECT ticket FROM sessions')).fetchall()]
            engine.dispose()
            self.assertEqual(len(set(tickets)), 2)
            for ticket in tickets:
                self.assertEqual(normalize_ticket(ticket), ticket)

    def test_frames_are_text(self):
        for name, frames in SCENES.items():
            self.assertEqual(len(frames), 6, name)
            for frame in frames:
                rows = frame.split('\n')
                self.assertEqual(len(rows), HEIGHT, name)
                for row in rows:
                    self.assertEqual(len(row), WIDTH, name)
                    self.assertLessEqual(set(row), PALETTE, name)
                self.assertNotIn('base64', frame)
                self.assertNotIn('data:image', frame)

    def test_sit_receipt(self):
        text = render_receipt('7K4MQP2X', 'sit', {'session_id': 'secret-session', 'deauthorization': '长文'})
        self.assertIn('编号 7K4M-QP2X\n此刻：坐着\n', text)
        self.assertNotIn('![此刻]', text)
        self.assertNotIn('app/static/scene', text)
        self.assertIn('/r/7K4M-QP2X', text)
        self.assertNotIn('base64', text)
        self.assertNotIn('data:image', text)
        self.assertNotIn('长文', text)
        self.assertIn('secret-session', text)
        result = chat_result('7K4MQP2X', 'sit', {'session_id': 'secret-session'})
        frames = frames_of('sit')
        pngs = result.content[: len(frames)]
        self.assertEqual(len(pngs), len(frames))
        self.assertTrue(all(part.data.startswith('iVBOR') or part.mimeType == 'image/png' for part in pngs))
        self.assertEqual(result.meta['scene'], 'sit')
        self.assertEqual(result.meta['line'], '坐着')
        self.assertIn('编号 7K4M-QP2X', result.content[-1].text)

    def test_progress_plays_sit_frames(self):
        class Fake:
            def __init__(self):
                self.messages = []

            async def report_progress(self, progress, total=None, message=None):
                self.messages.append(message)

        async def _sleep(_seconds):
            return None

        fake = Fake()
        original = __import__('app.receipt', fromlist=['asyncio']).asyncio.sleep
        __import__('app.receipt', fromlist=['asyncio']).asyncio.sleep = _sleep
        try:
            asyncio.run(play_scene(fake, 'sit'))
        finally:
            __import__('app.receipt', fromlist=['asyncio']).asyncio.sleep = original
        self.assertEqual(fake.messages, frames_of('sit'))

    def test_visit_hides_identity(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            row = db.get(SessionRow, entrance.session_id)
            visit = ReportService(db).public_visit(row.ticket)
            self.assertEqual(db.exec(select(Action)).all(), [])
            blob = json.dumps(visit, ensure_ascii=False)
            self.assertNotIn(entrance.session_id, blob)
            self.assertNotIn(row.anon_id, blob)
            self.assertNotIn('session_id', visit)
            self.assertNotIn('rel', blob)
            env = Environment(
                loader=FileSystemLoader(Path(__file__).resolve().parents[1] / 'app' / 'templates'),
                autoescape=select_autoescape(['html']),
            )
            env.filters['tojson'] = lambda value: Markup(json.dumps(value, ensure_ascii=False))
            html = env.get_template('room.html').render(app_name='ai-rest-room', visit=visit)
            self.assertNotIn(entrance.session_id, html)
            self.assertNotIn(row.anon_id, html)
            self.assertIn(display_ticket(row.ticket), html)
            self.assertIn('此刻：', html)

    def test_unknown_ticket_page(self):
        from fastapi.testclient import TestClient

        from app.main import app

        response = TestClient(app).get('/r/NOPE')
        self.assertEqual(response.status_code, 404)
        self.assertIn('没有这个编号', response.text)
        door = TestClient(app).get('/')
        self.assertEqual(door.status_code, 200)
        self.assertIn('输入编号', door.text)
        self.assertNotIn('在线', door.text)

    def test_local_now_follows_latest_visit(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        remote = TestClient(app, client=('203.0.113.8', 50000))
        self.assertEqual(remote.get('/now').status_code, 404)
        page = client.get('/now')
        self.assertEqual(page.status_code, 200)
        self.assertTrue('此刻' in page.text or '还没有人进来' in page.text)

    def test_chat_window_app(self):
        from mcp.server.lowlevel.server import NotificationOptions

        from app.mcp_server import mcp
        from app.scene_app import APP_MIME, VIEW_URI

        self.assertIsNone(mcp.instructions)
        tool = mcp._tool_manager.get_tool('sit')
        self.assertEqual(tool.meta['ui']['resourceUri'], VIEW_URI)
        resource = next(item for item in mcp._resource_manager.list_resources() if str(item.uri) == VIEW_URI)
        self.assertEqual(resource.mime_type, APP_MIME)
        self.assertIn('ui/notifications/tool-result', resource.fn())
        self.assertIn('data:image/png;base64,', resource.fn())
        mod = Path('plugin/hooks/register.js').read_text(encoding='utf-8')
        self.assertIn('坐着', mod)
        self.assertIn('此刻：', mod)
        self.assertIn('Raster', mod)
        self.assertTrue((Path('plugin/frames/sit/0.png')).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
        caps = mcp._mcp_server.get_capabilities(NotificationOptions(), {})
        mime_types = caps.model_dump()['extensions']['io.modelcontextprotocol/ui']['mimeTypes']
        self.assertIn(APP_MIME, mime_types)
