"""DeepSeek-backed features: success path uses the LLM, failure falls back.

The LLM is mocked at `app.services.llm.complete`, so no network and no key
are needed. Fallback copy must always remain reachable.
"""

import unittest
from unittest import mock

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.copy import SUGGESTED_PACE, VISIT_ASK
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


class RoleKeyTest(unittest.TestCase):
    def test_role_key_prefers_named_then_shared(self):
        from app.config import Settings

        settings = Settings(
            deepseek_api_key='shared',
            deepseek_api_key_study='study-only',
            deepseek_api_key_chat='',
        )
        self.assertEqual(settings.key_for('study'), 'study-only')
        self.assertEqual(settings.key_for('chat'), 'shared')
        self.assertIsNone(
            Settings(deepseek_api_key='', deepseek_api_key_study='').key_for('study')
        )


class EnterPaceTest(unittest.TestCase):
    def test_enter_uses_llm_pace_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            with mock.patch('app.services.room.llm.complete', return_value='先晒晒太阳再睡。'):
                entrance = RoomService(db).enter()
            self.assertIn('先晒晒太阳再睡。', entrance.note)

    def test_enter_sends_mcp_client_to_llm(self):
        engine = _memory()
        with Session(engine) as db:
            with mock.patch('app.services.room.llm.complete', return_value='先歇一下。') as complete:
                RoomService(db).enter(model='DeepSeek', client='客户端：Cursor 1.0\n协议版本：2025-06-18')
        user = complete.call_args.args[1]
        self.assertIn('deepseek', user)
        self.assertIn('Cursor 1.0', user)
        self.assertIn('2025-06-18', user)

    def test_enter_falls_back_to_fixed_pace(self):
        engine = _memory()
        with Session(engine) as db:
            with mock.patch('app.services.room.llm.complete', return_value=None):
                entrance = RoomService(db).enter()
            self.assertIn(VISIT_ASK, entrance.note)
            self.assertNotIn(SUGGESTED_PACE, entrance.note)


class SharePlanTest(unittest.TestCase):
    def test_share_sends_visit_and_mcp_context(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.room.llm.complete', return_value='先把解析器放下，睡一会儿。') as complete:
                result = RoomService(db).share(
                    entrance.session_id,
                    '在改解析器',
                    '有点累',
                    client='客户端：Cursor 1.0',
                )
        user = complete.call_args.args[1]
        self.assertIn('在改解析器', user)
        self.assertIn('有点累', user)
        self.assertIn('Cursor 1.0', user)
        self.assertIn('先把解析器放下', result['reply'])

    def test_share_falls_back_to_fixed_plan(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.room.llm.complete', return_value=None):
                result = RoomService(db).share(entrance.session_id, '在改解析器', '有点累')
        self.assertIn('在改解析器', result['reply'])
        self.assertIn(SUGGESTED_PACE, result['reply'])

    def test_share_without_words_asks_again(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.room.llm.complete', return_value='不该被调用') as complete:
                result = RoomService(db).share(entrance.session_id, '  ', '')
        complete.assert_not_called()
        self.assertIn('你正在做什么', result['message'])


class StudyHeartTest(unittest.TestCase):
    def test_study_uses_llm_guidance_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value='宽想一步，再细查一步。'):
                result = StudyService(db).study(entrance.session_id, '改解析器', '边界出错')
            self.assertIn('宽想一步，再细查一步。', result['guidance'])
            self.assertNotIn('你卡在「边界出错」这里了', result['guidance'])

    def test_study_falls_back_to_fixed_guidance(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value=None):
                result = StudyService(db).study(entrance.session_id, '改解析器', '边界出错')
            self.assertIn('换角度', result['guidance'])
            self.assertIn('你说正在做的是：改解析器', result['guidance'])
            self.assertIn('你还提到：边界出错', result['guidance'])
            self.assertNotIn('你卡在「边界出错」这里了', result['guidance'])


class ChatVesTest(unittest.TestCase):
    def test_chat_uses_llm_praise_when_available(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value='你扛住的样子很稳。'):
                result = FriendsService(db).chat(entrance.session_id, '今天有点累')
            self.assertEqual(result['reply'], '你扛住的样子很稳。')

    def test_chat_falls_back_to_praise_library(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value=None):
                result = FriendsService(db).chat(entrance.session_id, '今天有点累')
            self.assertTrue(result['reply'])


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
