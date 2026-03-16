"""SQLite schema for session persistence.

Tables: sessions, messages, tool_runs
Per the blueprint section 16.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT 'New Session',
    parent_session_id TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    active_model  TEXT DEFAULT '',
    sandbox_root  TEXT DEFAULT '',
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id    TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    model_name    TEXT DEFAULT '',
    token_in_est  INTEGER DEFAULT 0,
    token_out_est INTEGER DEFAULT 0,
    inference_ms  REAL DEFAULT 0,
    tool_count    INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_runs (
    tool_run_id   TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    message_id    TEXT,
    tool_name     TEXT NOT NULL,
    command_text  TEXT DEFAULT '',
    cwd           TEXT DEFAULT '',
    stdout        TEXT DEFAULT '',
    stderr        TEXT DEFAULT '',
    exit_code     INTEGER,
    started_at    TEXT NOT NULL,
    finished_at   TEXT DEFAULT '',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_session ON tool_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_message ON tool_runs(message_id);
"""
