from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings
from .models import new_ticket

settings = get_settings()
connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
engine_kwargs: dict = {}
if not settings.database_url.startswith('sqlite'):
    engine_kwargs = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args, **engine_kwargs)


def create_db_and_tables() -> None:
    # Import models so metadata is populated.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    ensure_ticket_column()
    ensure_model_column()


def ensure_model_column(bound=None) -> None:
    """SQLite create_all does not add the visitor-model column to an existing sessions table."""
    target = bound or engine
    if not str(target.url).startswith('sqlite'):
        return
    with target.begin() as conn:
        found = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        ).first()
        if found is None:
            return
        columns = {row[1] for row in conn.execute(text('PRAGMA table_info(sessions)')).fetchall()}
        if 'model' not in columns:
            conn.execute(text('ALTER TABLE sessions ADD COLUMN model TEXT'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_sessions_model ON sessions(model)'))


def ensure_ticket_column(bound=None) -> None:
    """SQLite create_all does not add columns to an existing sessions table."""
    target = bound or engine
    if not str(target.url).startswith('sqlite'):
        return
    with target.begin() as conn:
        found = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        ).first()
        if found is None:
            return
        columns = {row[1] for row in conn.execute(text('PRAGMA table_info(sessions)')).fetchall()}
        if 'ticket' not in columns:
            conn.execute(text('ALTER TABLE sessions ADD COLUMN ticket TEXT'))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_sessions_ticket ON sessions(ticket)'))
        missing = conn.execute(
            text("SELECT id FROM sessions WHERE ticket IS NULL OR ticket = ''")
        ).fetchall()
        if not missing:
            return
        used = {
            row[0]
            for row in conn.execute(
                text("SELECT ticket FROM sessions WHERE ticket IS NOT NULL AND ticket != ''")
            ).fetchall()
        }
        for (session_id,) in missing:
            ticket = new_ticket()
            while ticket in used:
                ticket = new_ticket()
            used.add(ticket)
            conn.execute(
                text('UPDATE sessions SET ticket = :ticket WHERE id = :id'),
                {'ticket': ticket, 'id': session_id},
            )


def get_session():
    with Session(engine) as session:
        yield session
