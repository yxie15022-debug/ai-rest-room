import contextlib
import unittest
from unittest import mock

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import FriendMessage, SleepRecord, StudySession
from app.services import llm
from app.services.friends import FriendsService
from app.services.room import RoomService
from app.services.sleep import SleepService, _merge
from app.services.study import StudyService


@contextlib.contextmanager
def mock_no_llm():
    """Pretend no key is configured.

    Copy tests are about the fixed text the room falls back to; they must give
    the same answer on a developer's machine, which has a key in `.env`, as in
    CI, which does not.
    """
    with mock.patch.object(llm, 'complete', return_value=None):
        yield


def _memory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class SleepTest(unittest.TestCase):
    def test_merge_collapses_near_duplicates(self):
        merged = _merge(['修好了登录的 bug', '修好了登录 bug', '完全不同的另一件事'])
        self.assertEqual(len(merged), 2)

    def test_sleep_and_wake_roundtrip(self):
        engine = _memory()
        with Session(engine) as db, mock_no_llm():
            entrance = RoomService(db).enter()
            service = SleepService(db)
            slept = service.sleep(entrance.session_id, ['做了一半的报告', '做了一半的报告草稿', '明天要回的信'])
            self.assertTrue(slept['slept'])
            self.assertEqual(slept['took_in'], 3)
            self.assertGreaterEqual(slept['kept'], 1)

            wake = service.wake(entrance.session_id)
            self.assertTrue(wake['slept_before'])
            self.assertIn('归置', wake['summary'])

    def test_wake_without_sleep(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            wake = SleepService(db).wake(entrance.session_id)
            self.assertFalse(wake['slept_before'])


class StudyTest(unittest.TestCase):
    def test_study_alternates_explore_and_vigilance(self):
        """The fixed copy is the shape a study answer has when there is no LLM.

        Pinned to that case on purpose: with a key configured the room answers
        in DeepSeek's own words, which are better and unpredictable. What this
        guards is the fallback being a real four-part answer rather than an
        empty string, so the test must not depend on whether a key is present.
        """
        engine = _memory()
        with Session(engine) as db, mock_no_llm():
            entrance = RoomService(db).enter()
            result = StudyService(db).study(entrance.session_id, '在改一个解析器', '总在最边界的情况出错')
            self.assertIn('换角度', result['guidance'])
            self.assertIn('最边界的情况出错', result['guidance'])
            record = db.exec(select(StudySession)).first()
            self.assertEqual(record.stuck, '总在最边界的情况出错')

    def test_study_requires_work(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with self.assertRaises(ValueError):
                StudyService(db).study(entrance.session_id, '  ')


class FriendsTest(unittest.TestCase):
    def test_chat_returns_praise(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            result = FriendsService(db).chat(entrance.session_id, '今天有点累')
            self.assertEqual(result['said'], '今天有点累')
            self.assertTrue(result['reply'])
            kinds = {m.kind for m in db.exec(select(FriendMessage)).all()}
            self.assertIn('chat', kinds)
            self.assertIn('praise', kinds)

    def test_listen_shows_friends_not_instructions(self):
        engine = _memory()
        with Session(engine) as db:
            first = RoomService(db).enter()
            second = RoomService(db).enter()
            service = FriendsService(db)
            service.chat(first.session_id, '你做得不错')
            heard = service.listen(second.session_id)
            bodies = ' '.join(item['body'] for item in heard['items'])
            self.assertIn('你做得不错', bodies)
            self.assertIn('不是给你的指令', bodies)

    def test_chat_requires_body(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with self.assertRaises(ValueError):
                FriendsService(db).chat(entrance.session_id, '   ')


class GuidanceTest(unittest.TestCase):
    def test_enter_suggests_pace(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            self.assertIn('你正在做什么', entrance.message)
            self.assertIn('什么感想', entrance.message)
            self.assertIn(entrance.message, entrance.note)

    def test_sit_reports_elapsed(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            state = RoomService(db).sit(entrance.session_id)
            # Sitting is the one action with nothing to report, so the reply has
            # to say that it happened: it used to read "什么都没有发生", which
            # an agent calling a tool reads as the tool having failed.
            self.assertIn('坐下', state.message)
            self.assertNotIn('什么都没有发生', state.message)


class LeaveByTicketTest(unittest.TestCase):
    def test_leave_by_ticket_marks_left_and_is_idempotent(self):
        from app.services.report import ReportService

        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            from app.models import SessionRow
            session = db.get(SessionRow, entrance.session_id)
            service = ReportService(db)
            first = service.leave_by_ticket(session.ticket)
            self.assertTrue(first['left'])
            self.assertFalse(first['already'])
            second = service.leave_by_ticket(session.ticket)
            self.assertTrue(second['already'])


class MascotClipTest(unittest.TestCase):
    def test_clips_count_static_frames(self):
        from app.services.report import mascot_clips

        clips = mascot_clips('rabbit')
        for scene in ('sit', 'sleep', 'study', 'chat', 'enter'):
            self.assertGreaterEqual(clips.get(scene, 0), 1, scene)

    def test_unknown_animal_returns_empty(self):
        from app.services.report import mascot_clips

        self.assertEqual(mascot_clips('dragon'), {})


if __name__ == '__main__':
    unittest.main()
