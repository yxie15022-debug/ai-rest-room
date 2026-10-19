"""DeepSeek-backed features: success path uses the LLM, failure falls back.

The LLM is mocked at `app.services.llm.complete`, so no network and no key
are needed. Fallback copy must always remain reachable.
"""

import unittest
from unittest import mock

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.copy import SUGGESTED_PACE
from app.services.friends import FriendsService
from app.services.room import RoomService
from app.services.study import StudyService


def _memory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class EnterPaceTest(unittest.TestCase):
    def test_enter_uses_llm_pace_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            with mock.patch('app.services.room.llm.complete', return_value='先晒晒太阳再睡。'):
                entrance = RoomService(db).enter()
            self.assertIn('先晒晒太阳再睡。', entrance.note)

    def test_enter_falls_back_to_fixed_pace(self):
        engine = _memory()
        with Session(engine) as db:
            with mock.patch('app.services.room.llm.complete', return_value=None):
                entrance = RoomService(db).enter()
            self.assertIn(SUGGESTED_PACE, entrance.note)


class StudyHeartTest(unittest.TestCase):
    def test_study_uses_llm_guidance_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value='宽想一步，再细查一步。'):
                result = StudyService(db).study(entrance.session_id, '改解析器', '边界出错')
            self.assertIn('宽想一步，再细查一步。', result['guidance'])
            self.assertIn('边界出错', result['guidance'])  # lead kept

    def test_study_falls_back_to_fixed_guidance(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value=None):
                result = StudyService(db).study(entrance.session_id, '改解析器', '边界出错')
            self.assertIn('换角度', result['guidance'])


class ChatVesTest(unittest.TestCase):
    def test_chat_uses_llm_praise_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value='你扛住的样子很稳。'):
                result = FriendsService(db).chat(entrance.session_id, '今天有点累')
            self.assertEqual(result['room_says'], '你扛住的样子很稳。')

    def test_chat_falls_back_to_praise_library(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value=None):
                result = FriendsService(db).chat(entrance.session_id, '今天有点累')
            self.assertTrue(result['room_says'])


class SleepConsolidateTest(unittest.TestCase):
    def test_consolidate_keeps_fallback_when_llm_returns_none(self):
        # LLM off -> _consolidate_async must not touch the record.
        from app.services.sleep import _consolidate_async

        with mock.patch('app.services.sleep.llm.complete', return_value=None):
            # record_id 1 may not exist here; the point is it returns before any write.
            _consolidate_async(1, ['片段一', '片段二'])

    def test_sleep_returns_immediately_with_fallback_summary(self):
        from app.services.sleep import SleepService

        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.sleep.llm.complete', return_value=None):
                result = SleepService(db).sleep(entrance.session_id, ['做了一半的报告', '明天要回的信'])
                wake = SleepService(db).wake(entrance.session_id)
            self.assertTrue(result['slept'])
            self.assertIn('归置', wake['summary'])  # deterministic fallback


if __name__ == '__main__':
    unittest.main()
