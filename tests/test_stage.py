"""The desktop pet: its art, its scenes, how it finds a visit, and its window."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import pet
from app.main import app
from app.models import SessionRow
from app.services.report import ReportService
from app.services.room import RoomService

ROOT = Path(__file__).resolve().parents[1]
ANIM = ROOT / 'app' / 'static' / 'anim'
MANIFEST = json.loads((ANIM / 'stage.json').read_text(encoding='utf-8'))
MODELS = (
    'default', 'deepseek', 'qwen', 'grok', 'gpt',
    'claude', 'gemini', 'kimi', 'glm', 'doubao',
)


def _memory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class StageArtTest(unittest.TestCase):
    def test_every_model_has_its_own_sprites(self):
        self.assertEqual(sorted(MANIFEST['cast']), sorted(MODELS))
        for model in MODELS:
            poses = MANIFEST['cast'][model]['poses']
            self.assertIn('stand', poses, model)
            self.assertIn('sit', poses, model)
            for pose, size in poses.items():
                png = ANIM / 'cast' / model / f'{pose}.png'
                self.assertTrue(png.is_file(), png)
                self.assertEqual(len(size), 2, f'{model}/{pose}')

    def test_sitting_is_shorter_than_standing(self):
        """A pose drawn in its own square must be scaled against the standing art."""
        for model in MODELS:
            poses = MANIFEST['cast'][model]['poses']
            self.assertLess(poses['sit'][1], poses['stand'][1], model)

    def test_every_model_can_lie_down(self):
        """`sleep` poses a lying sprite, so a model without one just stands by the bed.

        Fitted by length rather than height: her body runs across the frame, so
        the number that has to match between models is how long she is.
        """
        lengths = set()
        for model in MODELS:
            poses = MANIFEST['cast'][model]['poses']
            self.assertIn('sleep', poses, model)
            png = ANIM / 'cast' / model / 'sleep.png'
            self.assertTrue(png.is_file(), png)
            w, h = poses['sleep']
            self.assertGreater(w, h, f'{model}/sleep should be wider than tall')
            lengths.add(w)
        self.assertEqual(len(lengths), 1, lengths)

    def test_rig_lands_under_the_skirt(self):
        """Chibi proportions put the hem low; the split has to stay centred.

        These are the two numbers the walk cycle is built on: cut above the hem
        and the legs tear out of the skirt, cut off-centre and one leg carries
        half the other one with it.
        """
        for model in MODELS:
            rig = MANIFEST['cast'][model]['rig']
            self.assertTrue(0.75 <= rig['hem'] <= 0.86, (model, rig['hem']))
            self.assertTrue(0.44 <= rig['split'] <= 0.54, (model, rig['split']))
            self.assertEqual(rig['size'], MANIFEST['cast'][model]['poses']['stand'])

    def test_room_is_one_still_cutaway_box(self):
        """Nothing in the room moves, so there is no door leaf to ship."""
        self.assertEqual(MANIFEST['room'], {'size': [925, 902]})
        self.assertTrue((ANIM / 'room' / 'bg.png').is_file())
        self.assertFalse((ANIM / 'room' / 'door.png').exists())

    def test_the_room_is_cut_out_of_its_page(self):
        """The pet window is clipped to this shape, so the shape has to be here.

        Corners clear, walls solid, and a hard edge between them: a rim of
        half-transparent pixels would survive the clip as a grey fringe.
        """
        from PIL import Image

        alpha = Image.open(ANIM / 'room' / 'bg.png').convert('RGBA').getchannel('A')
        w, h = alpha.size
        for corner in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
            self.assertEqual(alpha.getpixel(corner), 0, corner)
        self.assertEqual(alpha.getpixel((w // 2, h // 2)), 255)
        counts = alpha.histogram()
        self.assertGreater(counts[0] + counts[255], 0.99 * w * h)

    def test_the_floor_corners_sit_inside_the_room(self):
        """The stage walks people over a quad measured off this very art."""
        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        w, h = MANIFEST['room']['size']
        for name in ('back', 'right', 'left', 'front'):
            match = re.search(rf'\n  {name}: \[(-?\d+), (-?\d+)\]', stage)
            self.assertIsNotNone(match, name)
            x, y = int(match.group(1)), int(match.group(2))
            self.assertTrue(0 <= x <= w, (name, x))
            self.assertTrue(0 <= y <= h, (name, y))

    def test_the_anchors_land_on_the_furniture(self):
        """A seat anchor is a place on the cushion, and the art is the judge.

        These numbers were measured off the room once and then drifted: the
        sprite ended up pinned at the floor line beside the sofa, which looks
        like a bug in the pose rather than in the anchor. Reading the room's own
        pixels catches exactly that -- the anchor has to fall on upholstery,
        not on floorboards or outside the room.
        """
        from PIL import Image

        room = Image.open(ANIM / 'room' / 'bg.png').convert('RGBA')
        px = room.load()

        def upholstery(x, y):
            r, g, b, a = px[int(x), int(y)]
            if a < 128:
                return False
            top, low = max(r, g, b), min(r, g, b)
            # Pale and desaturated: the sofa's blue-grey and the bed's mint
            # sheet both qualify. Wood, walls and the rug are warmer than this
            # (a wide red-to-blue spread), which is what keeps them out.
            return 80 <= top <= 242 and top - low <= 30

        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        anchors = {
            name: tuple(int(v) for v in match.groups())
            for name, match in (
                (name, re.search(rf"\n  {name}: \{{ x: (\d+), y: (\d+), h: \d+ \}}", stage))
                for name in ('sofa', 'bed')
            )
        }
        self.assertEqual(set(anchors), {'sofa', 'bed'})
        for name, (x, y) in anchors.items():
            # The anchor line is her base; just above it is where her body is.
            self.assertTrue(upholstery(x, y - 6), f'{name} anchor ({x}, {y}) is not on furniture')


class StageScriptTest(unittest.TestCase):
    """The stage is browser code; check the seams the Python side depends on."""

    def test_scenes_cover_every_recorded_action(self):
        scenes = (ANIM / 'scenes.js').read_text(encoding='utf-8')
        for name in ('house', 'enter', 'plan', 'sit', 'study', 'chat', 'sleep', 'leave'):
            self.assertIn(f'function* {name}(', scenes, name)
        self.assertIn('const SCENES = { house, enter, plan, sit, study, chat, sleep, leave }', scenes)

    def test_nothing_still_swings_the_door(self):
        for name in ('scenes.js', 'stage.js', 'main.js'):
            source = (ANIM / name).read_text(encoding='utf-8')
            for gone in ('setDoor', 'DOOR_OPEN', 'outsidePuppet', 'GATE_FLOOR'):
                self.assertNotIn(gone, source, f'{name}: {gone}')

    def test_main_can_follow_the_room_without_a_ticket(self):
        main = (ANIM / 'main.js').read_text(encoding='utf-8')
        self.assertIn("params.get('follow') === 'now'", main)
        self.assertIn("fetch('/now/state')", main)
        self.assertIn("enqueue('house')", main)

    def test_every_stage_constant_is_defined(self):
        """The stage is not type-checked; a missing constant is a blank room.

        `TOP_PAD` went missing this way and took the whole speech column with
        it -- a ReferenceError inside `fit()` leaves the room drawn and every
        bubble silently uncreated.
        """
        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        for name in ('ROOM', 'FLOOR', 'SPOT', 'ANCHOR', 'SPEECH', 'TOP_PAD', 'WALK_SPEED'):
            self.assertRegex(stage, rf'\nconst {name} = ', name)

    def test_speech_is_one_column_for_the_room(self):
        """Not a bubble per head: two of those overlap in a pet-sized window.

        Checked structurally, because the failure is visual: the bubbles cover
        each other and whichever was lifted clear floats with nothing under it.
        """
        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        self.assertIn('say(speaker, text', stage)
        self.assertIn('this.stage.say(', stage)
        self.assertNotIn('this.bubbles', stage)
        css = (ANIM / 'stage.css').read_text(encoding='utf-8')
        self.assertIn('.speech {', css)
        self.assertNotIn('.bubbles {', css)

    def test_lines_arrive_one_at_a_time(self):
        """One tool call makes several lines; they must not land in one tick.

        They share a timestamp, so speaking them as the state arrives put a
        wall of text on screen at once -- the agent that is silent for minutes
        and then dumps everything. The stage queues them and the room's answer
        waits a beat, so the reply visibly follows what it answers.
        """
        main = (ANIM / 'main.js').read_text(encoding='utf-8')
        self.assertIn('sayQueue', main)
        self.assertIn('function speak(', main)
        self.assertIn('pumpSpeech()', main)
        self.assertIn('REPLY_GAP', main)
        # The state handler must hand off to the queue rather than say directly.
        self.assertIn('speak(fresh)', main)
        self.assertNotIn('mouth.say(voice.text', main)

    def test_speech_is_signed_with_who_said_it(self):
        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        self.assertIn("tag.className = 'who'", stage)
        self.assertIn("'DeepSeek'", stage)
        main = (ANIM / 'main.js').read_text(encoding='utf-8')
        self.assertIn('self_name', main)
        css = (ANIM / 'stage.css').read_text(encoding='utf-8')
        self.assertIn('.bubble .who', css)


class NowStateTest(unittest.TestCase):
    """What `follow=now` reads to find the visit it should be watching."""

    def test_empty_room_reports_no_ticket(self):
        with mock.patch.object(ReportService, 'latest_view', return_value=None):
            state = TestClient(app).get('/now/state').json()
        self.assertEqual(state['ticket'], '')
        self.assertFalse(state['still_inside'])

    def test_state_follows_a_visit_in_and_out(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter(model='grok')
            ticket = db.get(SessionRow, entrance.session_id).ticket
            service = ReportService(db)

            inside = service.latest_view()
            self.assertEqual(inside['ticket'].replace('-', ''), ticket)
            self.assertTrue(inside['still_inside'])

            service.leave_by_ticket(ticket)
            after = service.latest_view()
            # Still the latest visit, so the pet knows which room just emptied.
            self.assertEqual(after['ticket'], inside['ticket'])
            self.assertFalse(after['still_inside'])


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 4242
        self.running = True
        self.terminated = False

    def poll(self):
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def wait(self, timeout=None) -> int:
        return 0


class LaunchPetTest(unittest.TestCase):
    """One room per MCP session, however many times the client handshakes."""

    def setUp(self) -> None:
        pet._pets.clear()
        self.addCleanup(pet._pets.clear)

    def test_one_window_per_session(self):
        with mock.patch.object(pet, '_spawn') as spawn:
            self.assertTrue(pet.launch_pet(1))
            self.assertFalse(pet.launch_pet(1))
            self.assertTrue(pet.launch_pet(2))
        self.assertEqual([call.args[0] for call in spawn.mock_calls], [1, 2])

    def test_a_dead_window_may_be_replaced(self):
        gone = FakeProcess()
        gone.running = False
        pet._pets[1] = gone
        with mock.patch.object(pet, '_spawn'):
            self.assertTrue(pet.launch_pet(1))

    def test_closing_ends_the_process_and_forgets_it(self):
        proc = FakeProcess()
        pet._pets[1] = proc
        pet.close_pet(1)
        self.assertTrue(proc.terminated)
        self.assertNotIn(1, pet._pets)

    def test_closing_an_unknown_session_is_quiet(self):
        pet.close_pet(99)

    def test_a_window_that_lost_its_session_is_not_left_running(self):
        """close_pet can land while the window is still opening."""
        proc = FakeProcess()
        with mock.patch.object(pet, 'pet_python', return_value='python'), \
             mock.patch.object(pet, 'room_is_up', return_value=True), \
             mock.patch.object(pet.subprocess, 'Popen', return_value=proc), \
             mock.patch.object(pet, '_remember') as remember:
            pet._spawn(7)  # nobody is waiting for key 7
        self.assertTrue(proc.terminated)
        remember.assert_not_called()


class PetWindowTest(unittest.TestCase):
    SOURCE = (ROOT / 'plugin' / 'scripts' / 'pet_window.py').read_text(encoding='utf-8')

    def test_no_js_api_object(self):
        """pywebview walks a js_api's attributes; a window on one blows the stack."""
        self.assertNotIn('js_api=', self.SOURCE)
        self.assertIn('window.expose(close)', self.SOURCE)

    def test_ticket_is_optional(self):
        self.assertIn("parser.add_argument('--ticket', default='')", self.SOURCE)
        self.assertIn("'follow=now'", self.SOURCE)

    def test_the_window_is_the_room_and_nothing_else(self):
        """Transparent page, and the window cut down to the room's own outline.

        Both halves matter: the clip is what makes the pet a room rather than a
        picture of one, and it is also what lets clicks outside the walls reach
        the window underneath.
        """
        self.assertIn('transparent=True', self.SOURCE)
        self.assertIn('SetWindowRgn', self.SOURCE)
        self.assertIn('def clip_to_shape(', self.SOURCE)

    def test_the_shape_follows_the_speech(self):
        """A clip fixed at the walls slices the top off every bubble.

        The room's roof slopes in from both sides, so speech has to be allowed
        to stand in the air above it -- and the window has to grow to include
        it, every time a bubble appears or goes.
        """
        self.assertIn('def shape_loop(', self.SOURCE)
        self.assertIn('window.__outline', self.SOURCE)
        self.assertIn('clip_to_shape(hwnd, art, room, boxes)', self.SOURCE)
        stage = (ANIM / 'stage.js').read_text(encoding='utf-8')
        self.assertIn('room: {', stage)
        self.assertIn('boxes,', stage)

    def test_the_page_paints_no_box_around_the_room(self):
        css = (ANIM / 'stage.css').read_text(encoding='utf-8')
        self.assertIn('body.pet #stage {\n  background: transparent;', css)
        self.assertIn('body.pet #veil,\nbody.pet #caption {\n  display: none;', css)

    def test_nothing_paints_the_viewport_in_pet_mode(self):
        """The root element is what paints the viewport, not just `body`.

        Leaving `html` beige put a rectangle of #f4efe6 behind the room: the
        clip includes the speech above the walls, so that colour showed as a
        yellow panel around every bubble and a yellow rim in the corners a
        rectangle cannot round. `body` alone never covered it.
        """
        css = (ANIM / 'stage.css').read_text(encoding='utf-8')
        self.assertRegex(css, r'html\.pet,\s*\nbody\.pet,')
        main = (ANIM / 'main.js').read_text(encoding='utf-8')
        self.assertIn("document.documentElement.classList.add('pet')", main)

    def test_static_files_are_revalidated_not_cached(self):
        """The pet is a WebView2 with its own profile and no reload button.

        A cached stage.css there keeps drawing yesterday's layout with nothing
        to hint that a fix never arrived.
        """
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('no-cache, must-revalidate', main)
        self.assertIn('FreshStatic', main)


class OpenRoomFallbackTest(unittest.TestCase):
    """The hook is the net under the server, so it must not double up."""

    def test_hook_stands_down_when_the_server_owns_the_window(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'open_room', ROOT / 'plugin' / 'scripts' / 'open_room.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.SERVER_OWNED, pet.OWNER)

        with mock.patch.object(module, '_read_state', return_value=(pet.OWNER, 321)), \
             mock.patch.object(module, '_pid_alive', return_value=True), \
             mock.patch.object(module, 'ticket_from_server', return_value='ABCD-EFGH'), \
             mock.patch.object(module, 'launch_window') as launch, \
             mock.patch.object(module.sys.stdin, 'isatty', return_value=True):
            self.assertEqual(module.main(), 0)
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
