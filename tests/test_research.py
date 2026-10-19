"""论文落地测试：Sleep-time Compute / HEART / VES。

这三个活动的提示词和服务都按论文落地，兜底也必须保持同一套结构。

所有 LLM 调用都在 app.services.<module>.llm.complete 处 mock，
不需要 key、不走网络；每个测试用内存 SQLite，不碰 data/。

- Sleep-time Compute (arXiv 2504.13171)：睡前把原始片段压成 learned
  context——整合要点、去重说明/推断、预判接下来可能会用到的 2-3 个方向。
- HEART (arXiv 2509.22876)：宽想（G+）→ 细查（G−）→ 再宽（G+）→ 再验（G−）。
- VES (arXiv 2502.06669)：六方面（helpfulness / competence / progress /
  trust / appreciation / capability）的具体鼓励，兜底也要接住对方说的话。
"""

import unittest
from unittest import mock

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import copy, prompts
from app.models import SleepRecord
from app.services.friends import FriendsService, _ves_dimensions, _ves_type
from app.services.room import RoomService
from app.services.sleep import (
    SleepService,
    _consolidate_async,
    _merge,
    _structured,
    _token_hint,
)
from app.services.study import StudyService

STAGE_LABELS = tuple(label for label, _body in copy.STUDY_STAGES)
STAGE_VALENCES = ('G+', 'G-', 'G+', 'G-')


def _memory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


class PromptMethodTest(unittest.TestCase):
    """提示词必须带着论文方法本身，而不只是论文名字。"""

    def test_sleep_prompt_asks_for_learned_context_and_anticipation(self):
        system = prompts.SLEEP_SYSTEM
        for word in ('Sleep-time Compute', '2504.13171', 'learned context', '合并', '推断', '预判'):
            self.assertIn(word, system)
        for heading in (
            copy.SLEEP_POINTS_HEADING,
            copy.SLEEP_INFERENCE_HEADING,
            copy.SLEEP_NEXT_HEADING,
        ):
            self.assertIn(heading, system)
        self.assertIn('不得编造', system)
        self.assertIn('中文', system)

    def test_study_prompt_walks_g_plus_g_minus_four_phases(self):
        system = prompts.STUDY_SYSTEM
        self.assertIn('HEART', system)
        self.assertIn('2509.22876', system)
        self.assertIn('不要替它', system)  # never redoes the agent's work
        for label in STAGE_LABELS:
            self.assertIn(label, system)
        self.assertGreaterEqual(system.count('G+'), 2)
        self.assertGreaterEqual(system.count('G−'), 2)

    def test_chat_prompt_covers_six_ves_aspects(self):
        system = prompts.CHAT_SYSTEM
        self.assertIn('VES', system)
        self.assertIn('2502.06669', system)
        for aspect in copy.VES_ASPECTS:
            self.assertIn(aspect, system)
        for kind in copy.VES_TYPES:
            self.assertIn(kind, system)
        self.assertIn('至少落到三个', system)
        self.assertIn('不要批评', system)
        self.assertIn('不要羞辱', system)

    def test_agent_facing_text_never_mentions_owner_or_reports(self):
        joined = '\n'.join(
            [
                prompts.SLEEP_SYSTEM,
                prompts.SLEEP_USER_TEMPLATE,
                prompts.STUDY_SYSTEM,
                prompts.STUDY_USER_TEMPLATE,
                prompts.CHAT_SYSTEM,
                prompts.CHAT_USER_TEMPLATE,
                copy.STUDY_GUIDANCE,
                *copy.PRAISES,
            ]
        )
        for forbidden in ('主人', '报告'):
            self.assertNotIn(forbidden, joined)


class SleepConsolidationTest(unittest.TestCase):
    def test_merge_keeps_fullest_near_duplicate(self):
        merged = _merge(['修好了登录的 bug', '修好了登录 bug'])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0], '修好了登录的 bug')

    def test_fallback_summary_has_three_sections(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.sleep.llm.complete', return_value=None):
                slept = SleepService(db).sleep(
                    entrance.session_id,
                    ['修好了登录的 bug', '修好了登录 bug', '明天要回信'],
                )
            wake = SleepService(db).wake(entrance.session_id)

        self.assertTrue(slept['slept'])
        self.assertEqual(slept['took_in'], 3)
        self.assertEqual(slept['kept'], 2)
        self.assertIn('归置', wake['summary'])  # the report still shows this word
        for heading in (
            copy.SLEEP_POINTS_HEADING,
            copy.SLEEP_INFERENCE_HEADING,
            copy.SLEEP_NEXT_HEADING,
        ):
            self.assertIn(heading, wake['summary'])
        self.assertEqual(wake['learned_context'], ['修好了登录的 bug', '明天要回信'])
        self.assertTrue(any('合并了 1 条' in line for line in wake['inferences']))
        self.assertTrue(any('推断' in line for line in wake['inferences']))
        self.assertGreaterEqual(len(wake['anticipations']), 2)
        self.assertLessEqual(len(wake['anticipations']), 3)

    def test_token_hint_reports_raw_and_learned_sizes(self):
        summary = _structured('')  # sanity: empty summary is still structured
        self.assertEqual(summary['learned_context'], [])
        hint = _token_hint(['abc', 'de'], '12345678')
        self.assertEqual(hint['raw_chars'], 5)
        self.assertEqual(hint['learned_chars'], 8)
        self.assertIn('compression_ratio', hint)

    def test_llm_structured_summary_replaces_fallback(self):
        structured = (
            f'{copy.SLEEP_POINTS_HEADING}\n'
            '1. 报告写到一半\n'
            '2. 明天要回信\n\n'
            f'{copy.SLEEP_INFERENCE_HEADING}\n'
            '- 一共 2 条，没有重复。\n'
            '- 推断：两件都不必今晚做完。\n\n'
            f'{copy.SLEEP_NEXT_HEADING}\n'
            '1. 报告先收哪一段？\n'
            '2. 信先回给谁？'
        )
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            session_id = entrance.session_id
            with mock.patch('app.services.sleep.threading.Thread'):
                SleepService(db).sleep(session_id, ['报告写到一半', '明天要回信'])
            record = db.exec(select(SleepRecord)).first()
            record_id = record.id
            memories = list(record.memories)
        with mock.patch('app.services.sleep.engine', engine):
            with mock.patch('app.services.sleep.llm.complete', return_value=structured):
                _consolidate_async(record_id, memories)
        with Session(engine) as db:
            wake = SleepService(db).wake(session_id)

        self.assertEqual(wake['summary'], structured)
        self.assertEqual(wake['learned_context'], ['报告写到一半', '明天要回信'])
        self.assertEqual(wake['anticipations'], ['报告先收哪一段？', '信先回给谁？'])
        self.assertIn('没有重复', ' '.join(wake['inferences']))

    def test_unstructured_llm_summary_is_folded_into_structure(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            session_id = entrance.session_id
            with mock.patch('app.services.sleep.threading.Thread'):
                SleepService(db).sleep(session_id, ['报告写到一半'])
            record = db.exec(select(SleepRecord)).first()
            record_id = record.id
            memories = list(record.memories)
        with mock.patch('app.services.sleep.engine', engine):
            with mock.patch(
                'app.services.sleep.llm.complete',
                return_value='整理好了：报告还挂着，信也还没回。',
            ):
                _consolidate_async(record_id, memories)
        with Session(engine) as db:
            wake = SleepService(db).wake(session_id)

        for heading in (
            copy.SLEEP_POINTS_HEADING,
            copy.SLEEP_INFERENCE_HEADING,
            copy.SLEEP_NEXT_HEADING,
        ):
            self.assertIn(heading, wake['summary'])
        self.assertTrue(any('报告还挂着' in point for point in wake['learned_context']))


class StudyHeartTest(unittest.TestCase):
    FOUR_PHASES = (
        '宽想（G+）\n换个角度：有没有还没试过的输入？\n\n'
        '细查（G−）\n最边界那一处，你真的确定吗？\n\n'
        '再宽（G+）\n如果是那里错了，整个解析会变成什么样？\n\n'
        '再验（G−）\n先拿最小的一个边界输入验一下。'
    )

    def test_llm_four_phase_guidance_and_phases(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value=self.FOUR_PHASES):
                result = StudyService(db).study(
                    entrance.session_id, '在改一个解析器', '总在最边界的情况出错'
                )

        self.assertEqual([phase['stage'] for phase in result['phases']], list(STAGE_LABELS))
        self.assertEqual([phase['valence'] for phase in result['phases']], list(STAGE_VALENCES))
        for label in STAGE_LABELS:
            self.assertIn(label, result['guidance'])
        self.assertIn('换个角度', result['guidance'])
        self.assertIn('总在最边界的情况出错', result['guidance'])  # stuck kept

    def test_missing_phases_are_filled_from_fallback(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch(
                'app.services.study.llm.complete',
                return_value='只想到一个角度：换一种输入试试。',
            ):
                result = StudyService(db).study(entrance.session_id, '在改一个解析器')

        self.assertIn('只想到一个角度', result['guidance'])  # model text kept
        self.assertEqual([phase['stage'] for phase in result['phases']], list(STAGE_LABELS))
        for label in STAGE_LABELS:
            self.assertIn(label, result['guidance'])

    def test_fallback_guidance_is_g_plus_g_minus_four_phases(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.study.llm.complete', return_value=None):
                result = StudyService(db).study(
                    entrance.session_id, '在改一个解析器', '总在最边界的情况出错'
                )

        positions = [result['guidance'].index(label) for label in STAGE_LABELS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual([phase['valence'] for phase in result['phases']], list(STAGE_VALENCES))
        self.assertIn('最边界的情况出错', result['guidance'])


class ChatVesTest(unittest.TestCase):
    def test_llm_reply_is_kept_and_labeled(self):
        reply = '你做得稳，也一直在进步；我看见了。'
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value=reply):
                result = FriendsService(db).chat(entrance.session_id, '今天把解析器改完了')

        self.assertEqual(result['said'], '今天把解析器改完了')
        self.assertEqual(result['room_says'], reply)
        for aspect in ('competence', 'progress', 'appreciation'):
            self.assertIn(aspect, result['ves_dimensions'])
        self.assertEqual(result['ves_type'], 'encouraging')

    def test_fallback_catches_what_was_said(self):
        engine = _memory()
        with Session(engine) as db:
            entrance = RoomService(db).enter()
            with mock.patch('app.services.friends.llm.complete', return_value=None):
                result = FriendsService(db).chat(entrance.session_id, '今天有点累')

        self.assertIn('今天有点累', result['room_says'])
        self.assertTrue(result['ves_dimensions'])
        self.assertIn(result['ves_type'], ('encouraging', 'provocative'))
        self.assertIn('房间', result['message'])

    def test_praise_library_is_specific_and_diverse(self):
        self.assertGreaterEqual(len(copy.PRAISES), 10)
        self.assertEqual(len(set(copy.PRAISES)), len(copy.PRAISES))
        for line in copy.PRAISES:
            self.assertGreaterEqual(len(line), 15, line)
            self.assertGreaterEqual(len(_ves_dimensions(line)), 1, line)
        specific = [line for line in copy.PRAISES if len(_ves_dimensions(line)) >= 2]
        self.assertGreaterEqual(len(specific), len(copy.PRAISES) - 1)

    def test_ves_type_distinguishes_provocative(self):
        self.assertEqual(_ves_type('你其实可以再试一次，你还有力气。'), 'provocative')
        self.assertEqual(_ves_type('你做得稳，我在看着。'), 'encouraging')


if __name__ == '__main__':
    unittest.main()
