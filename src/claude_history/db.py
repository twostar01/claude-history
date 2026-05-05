"""SQLite schema initialization for the claude-history MCP server."""

import sqlite3
from pathlib import Path


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create tables, FTS5 index, triggers, and enable WAL mode.

    Idempotent: uses CREATE ... IF NOT EXISTS throughout.
    Returns an open connection; caller is responsible for closing.

    Schema:
        conversations — id (TEXT PK), title, project (NULL in Phase 2),
                        created_at, updated_at, message_count
        messages      — rowid (INTEGER PK, stable for FTS5 content_rowid),
                        id (TEXT UNIQUE), conversation_id, role, content,
                        position, created_at
        messages_fts  — FTS5 virtual table; content="messages"; tokenizer
                        unicode61 with tokenchars '-_' so snake_case terms
                        like search_conversations index as a single token.

    Triggers:
        messages_ai   — AFTER INSERT: sync new row into messages_fts
        messages_ad   — AFTER DELETE: remove old row from messages_fts
        messages_au   — AFTER UPDATE: delete+reinsert in messages_fts

    WAL note: PRAGMA journal_mode=WAL is set before executescript() so all
    subsequent DDL and DML use WAL from the start. WAL mode persists across
    reconnections once set.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id            TEXT PRIMARY KEY,
            title         TEXT,
            project       TEXT,
            created_at    TEXT,
            updated_at    TEXT,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            rowid           INTEGER PRIMARY KEY,
            id              TEXT UNIQUE NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role            TEXT NOT NULL,
            content         TEXT NOT NULL DEFAULT '',
            position        INTEGER NOT NULL,
            created_at      TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content="messages",
            content_rowid="rowid",
            tokenize="unicode61 remove_diacritics 2 tokenchars '-_'"
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
            INSERT INTO messages_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;
    """)
    conn.commit()
    return conn
