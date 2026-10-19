"""Smoke the current vertical line without HTTP.

enter -> sit -> sleep -> wake -> study -> chat -> listen -> name -> leave -> report.
Runs against a temporary database and reports directory, with the LLM disabled,
so it never touches data/ and never calls the network.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix='ai-rest-room-smoke-'))
os.environ['DATABASE_URL'] = f'sqlite:///{(_TMP / "smoke.db").as_posix()}'
os.environ['REPORTS_DIR'] = str(_TMP / 'reports')
os.environ['DEEPSEEK_API_KEY'] = ''  # smoke never calls the network

from sqlmodel import Session  # noqa: E402

from app.db import create_db_and_tables, engine  # noqa: E402
from app.services.friends import FriendsService  # noqa: E402
from app.services.report import ReportService  # noqa: E402
from app.services.room import RoomService  # noqa: E402
from app.services.sleep import SleepService  # noqa: E402
from app.services.study import StudyService  # noqa: E402
from app.tickets import display_ticket  # noqa: E402


def main() -> None:
    create_db_and_tables()
    with Session(engine) as db:
        room = RoomService(db)
        entrance = room.enter()
        session = room.get(entrance.session_id)
        print('enter', display_ticket(session.ticket), entrance.anon_id, len(entrance.tools), 'tools')
        print('deauth_snippet', entrance.deauthorization[:24], '...')

        print('sit', room.sit(entrance.session_id).message)

        slept = SleepService(db).sleep(
            entrance.session_id,
            ['做了一半的报告', '做了一半的报告草稿', '明天要回的信'],
        )
        print('sleep', slept['took_in'], 'in,', slept['kept'], 'kept')
        wake = SleepService(db).wake(entrance.session_id)
        assert wake['slept_before'] and wake['summary']
        print('wake', wake['summary'].splitlines()[0])

        study = StudyService(db).study(entrance.session_id, '在改一个解析器', '总在最边界的情况出错')
        assert '最边界的情况出错' in study['guidance']
        print('study', study['message'])

        chat = FriendsService(db).chat(entrance.session_id, '今天有点累')
        assert chat['room_says']
        print('chat', chat['room_says'][:24])

        heard = FriendsService(db).listen(entrance.session_id)
        assert heard['items']
        print('listen', len(heard['items']), 'items')

        named = room.name_yourself(entrance.session_id, '小憩')
        assert named.self_name == '小憩'
        print('name', named.self_name)

        summary = ReportService(db).leave_and_report(entrance.session_id, note='冒烟通过')
        md = ReportService(db).read_report_markdown(summary.report_id)
        for section in ('# 活动报告', '## 做了什么', '## 说了什么', '## 睡了一觉', '## 学了什么', '## 何时离开'):
            assert section in md, section
        assert '在改一个解析器' in md
        assert '今天有点累' in md
        print('report', summary.report_id, len(md), 'chars')
        print('report_url_hint', f'http://127.0.0.1:8000/reports/{summary.report_id}')
        print('smoke_ok')


if __name__ == '__main__':
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
