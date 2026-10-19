import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import FriendMessage, SleepRecord, StudySession
from app.services.friends import FriendsService
from app.services.room import RoomService
from app.services.sleep import SleepService, _merge
from app.services.study import StudyService


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
        with Session(engine) as db:
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
        engine = _memory()
        with Session(engine) as db:
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
            self.assertTrue(result['room_says'])
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
            self.assertIn('先睡一会儿', entrance.note)
            self.assertIn('约 10 分钟', entrance.note)
            self.assertIn('这只是建议', entrance.note)

    def test_sit_reports_elapsed(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            state = RoomService(db).sit(entrance.session_id)
            self.assertIn('坐着', state.message)


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
