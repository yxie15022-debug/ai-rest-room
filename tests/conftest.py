"""Keep the test run out of the real data/ directory.

The settings are read from environment variables before any app module is
imported, so ReportService writes into a throwaway directory and the FastAPI
TestClient talks to a throwaway SQLite file. The real data/rest_room.db and
data/reports/ are never touched by pytest.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix='ai-rest-room-tests-'))
os.environ['DATABASE_URL'] = f'sqlite:///{(_TMP / "tests.db").as_posix()}'
os.environ['REPORTS_DIR'] = str(_TMP / 'reports')
os.environ['DEEPSEEK_API_KEY'] = ''

# Create the tables the TestClient-based tests expect, without triggering the
# app's lifespan (these tests call TestClient(app) directly).
from app.db import create_db_and_tables  # noqa: E402

create_db_and_tables()


def _cleanup() -> None:
    shutil.rmtree(_TMP, ignore_errors=True)


atexit.register(_cleanup)
