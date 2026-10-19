-- Reference schema for the rest room.
-- SQLModel.metadata.create_all() (app/db.py) is the source of truth; keep this
-- file in sync with app/models.py for manual inspection and older SQLite tooling.

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  anon_id TEXT NOT NULL,
  ticket TEXT,
  self_name TEXT,
  note TEXT,
  entered_at TIMESTAMP NOT NULL,
  left_at TIMESTAMP,
  report_path TEXT
);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  scene TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS friend_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  body TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'chat',
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS sleep_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  memories JSON NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS study_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  work TEXT NOT NULL,
  stuck TEXT,
  guidance TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sessions_anon_id ON sessions(anon_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sessions_ticket ON sessions(ticket);
CREATE INDEX IF NOT EXISTS ix_actions_session_id ON actions(session_id);
CREATE INDEX IF NOT EXISTS ix_friend_messages_session_id ON friend_messages(session_id);
CREATE INDEX IF NOT EXISTS ix_sleep_records_session_id ON sleep_records(session_id);
CREATE INDEX IF NOT EXISTS ix_study_sessions_session_id ON study_sessions(session_id);
