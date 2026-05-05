"""Tests for src/claude_history/db.py — TDD RED phase.

These tests verify the behavior of init_db() before the implementation exists.
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


def get_init_db():
    """Import init_db lazily so import errors fail the test, not collection."""
    from claude_history.db import init_db
    return init_db


class TestInitDbCreatesSchema:
    """init_db() creates all required tables, FTS virtual table, and triggers."""

    def test_creates_conversations_table(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "conversations" in tables

    def test_creates_messages_table(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "messages" in tables

    def test_creates_messages_fts_virtual_table(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        vt = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone()
        conn.close()
        assert vt is not None, "messages_fts virtual table missing"

    def test_creates_messages_ai_trigger(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()}
        conn.close()
        assert "messages_ai" in triggers

    def test_creates_messages_ad_trigger(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()}
        conn.close()
        assert "messages_ad" in triggers

    def test_creates_messages_au_trigger(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()}
        conn.close()
        assert "messages_au" in triggers


class TestWalMode:
    """init_db() enables WAL journal mode."""

    def test_journal_mode_is_wal(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        row = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert row[0] == "wal", f"Expected journal_mode=wal, got {row[0]}"


class TestIdempotency:
    """init_db() is safe to call multiple times on the same database."""

    def test_second_call_does_not_raise(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn1 = init_db(db)
        conn1.close()
        # Second call must not raise OperationalError
        conn2 = init_db(db)
        conn2.close()

    def test_second_call_does_not_destroy_data(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        conn.execute("INSERT INTO conversations(id, title) VALUES ('c1', 'Keep Me')")
        conn.commit()
        conn.close()

        conn2 = init_db(db)
        row = conn2.execute("SELECT title FROM conversations WHERE id='c1'").fetchone()
        conn2.close()
        assert row is not None and row[0] == "Keep Me"


class TestFtsTriggers:
    """AFTER INSERT and AFTER DELETE triggers keep messages_fts in sync."""

    def _seed_conversation(self, conn):
        conn.execute("INSERT INTO conversations(id, title) VALUES ('c1', 'Test Conv')")
        conn.commit()

    def test_after_insert_populates_fts(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        self._seed_conversation(conn)
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, position)"
            " VALUES ('m1', 'c1', 'human', 'hello world content', 0)"
        )
        conn.commit()
        count = conn.execute("SELECT count(*) FROM messages_fts").fetchone()[0]
        conn.close()
        assert count == 1, f"Expected 1 FTS entry after INSERT, got {count}"

    def test_after_delete_removes_from_fts(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        self._seed_conversation(conn)
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, position)"
            " VALUES ('m1', 'c1', 'human', 'hello world content', 0)"
        )
        conn.commit()
        conn.execute("DELETE FROM messages WHERE id = 'm1'")
        conn.commit()
        count = conn.execute("SELECT count(*) FROM messages_fts").fetchone()[0]
        conn.close()
        assert count == 0, f"Expected 0 FTS entries after DELETE, got {count}"

    def test_after_update_updates_fts(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        self._seed_conversation(conn)
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, position)"
            " VALUES ('m1', 'c1', 'human', 'original content', 0)"
        )
        conn.commit()
        conn.execute("UPDATE messages SET content='updated content' WHERE id='m1'")
        conn.commit()
        # FTS should reflect updated content
        results = conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'updated'"
        ).fetchall()
        old_results = conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'original'"
        ).fetchall()
        conn.close()
        assert len(results) == 1, "FTS should find 'updated' after UPDATE"
        assert len(old_results) == 0, "FTS should NOT find 'original' after UPDATE"


class TestFtsTokenizer:
    """FTS tokenizer treats underscores as token characters (snake_case support)."""

    def test_snake_case_token_matches_as_single_token(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        conn.execute("INSERT INTO conversations(id, title) VALUES ('c1', 'Test')")
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, position)"
            " VALUES ('m1', 'c1', 'human', 'search_conversations are great', 0)"
        )
        conn.commit()
        results = conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'search_conversations'"
        ).fetchall()
        conn.close()
        assert len(results) == 1, (
            "FTS MATCH 'search_conversations' should find 1 row — "
            "underscore must be a token character, not a separator"
        )

    def test_partial_snake_case_does_not_match_full_token(self, tmp_path):
        """'search' alone should NOT match 'search_conversations' with unicode61 tokenchars '_'."""
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        conn.execute("INSERT INTO conversations(id, title) VALUES ('c1', 'Test')")
        conn.execute(
            "INSERT INTO messages(id, conversation_id, role, content, position)"
            " VALUES ('m1', 'c1', 'human', 'search_conversations are great', 0)"
        )
        conn.commit()
        results = conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'search'"
        ).fetchall()
        conn.close()
        assert len(results) == 0, (
            "FTS MATCH 'search' should NOT match 'search_conversations' — "
            "underscore makes this a single indivisible token"
        )


class TestReturnValue:
    """init_db() returns an open, usable sqlite3.Connection."""

    def test_returns_connection_object(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_returned_connection_is_open(self, tmp_path):
        init_db = get_init_db()
        db = tmp_path / "test.db"
        conn = init_db(db)
        # If connection is closed, execute would raise ProgrammingError
        row = conn.execute("SELECT 1").fetchone()
        conn.close()
        assert row[0] == 1
