---
phase: 02-database-ingest
plan: "01"
subsystem: database
tags: [sqlite, fts5, schema, wal, tdd]
dependency_graph:
  requires: []
  provides: [src/claude_history/db.py, init_db]
  affects: [02-02-ingest, phase-3-search]
tech_stack:
  added: [pytest>=8.0 (dev dependency)]
  patterns: [FTS5 content table with sync triggers, WAL journal mode, INTEGER PRIMARY KEY for rowid stability]
key_files:
  created:
    - src/claude_history/db.py
    - tests/test_db.py
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - "FTS tokenizer locked as unicode61 remove_diacritics 2 tokenchars '-_' — cannot change after data insertion"
  - "rowid INTEGER PRIMARY KEY declared on messages to prevent VACUUM from reassigning rowids and corrupting FTS content_rowid links"
  - "PRAGMA journal_mode=WAL set before executescript() to ensure all DDL uses WAL from the start"
  - "No INSERT OR REPLACE anywhere — IGNORE is correct for append-only history records"
  - "pytest added as dev dependency with pythonpath=['src'] so tests import claude_history directly"
metrics:
  duration: "3m 6s"
  completed: "2026-05-04"
  tasks_completed: 1
  files_changed: 4
requirements_satisfied: [DB-01, DB-02, DB-03, DB-04]
---

# Phase 2 Plan 1: SQLite Schema (db.py) Summary

**One-liner:** SQLite FTS5 schema with WAL mode, sync triggers, and unicode61 snake_case tokenizer via `init_db(db_path)`.

## What Was Built

`src/claude_history/db.py` — a single public function `init_db(db_path: Path) -> sqlite3.Connection` that:

1. Opens (or creates) the SQLite file at `db_path`
2. Sets `PRAGMA journal_mode=WAL` before any DDL
3. Creates three tables/virtual tables using `IF NOT EXISTS` (idempotent):
   - `conversations` — id (TEXT PK), title, project (NULL), created_at, updated_at, message_count
   - `messages` — rowid (INTEGER PK), id (TEXT UNIQUE), conversation_id, role, content, position, created_at
   - `messages_fts` — FTS5 virtual table backed by `messages`, tokenizer `unicode61 remove_diacritics 2 tokenchars '-_'`
4. Creates three sync triggers using `IF NOT EXISTS`:
   - `messages_ai` — AFTER INSERT: pushes new row into FTS index
   - `messages_ad` — AFTER DELETE: removes old row from FTS index
   - `messages_au` — AFTER UPDATE: delete + reinsert in FTS index
5. Returns the open `sqlite3.Connection` (caller closes)

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | c23719f | 16 tests written, all failing (ModuleNotFoundError — db.py did not exist) |
| GREEN (impl) | b073817 | 16 tests passing |
| REFACTOR | N/A | No refactoring needed — implementation was clean on first pass |

## Tests Written (16 total)

| Test Class | Tests | Behavior Verified |
|---|---|---|
| `TestInitDbCreatesSchema` | 6 | conversations, messages, messages_fts, messages_ai, messages_ad, messages_au all created |
| `TestWalMode` | 1 | `PRAGMA journal_mode` returns `'wal'` |
| `TestIdempotency` | 2 | Second `init_db()` call does not raise; data is preserved |
| `TestFtsTriggers` | 3 | AFTER INSERT populates FTS; AFTER DELETE removes from FTS; AFTER UPDATE replaces in FTS |
| `TestFtsTokenizer` | 2 | `search_conversations` matches as single token; `search` alone does NOT match |
| `TestReturnValue` | 2 | Returns `sqlite3.Connection` instance; connection is open and usable |

## Plan Verification Results

All assertions from the plan's automated verify block passed:
- WAL mode confirmed: `PRAGMA journal_mode` = `'wal'`
- All tables present: conversations, messages, messages_fts
- All triggers present: messages_ai, messages_ad, messages_au
- AFTER INSERT trigger: FTS count = 1 after insert
- FTS tokenizer: `MATCH 'search_conversations'` returns 1 result
- AFTER DELETE trigger: FTS count = 0 after delete
- Idempotency: second `init_db()` call raises no error

Structural checks:
- `def init_db` count: 1
- `AFTER INSERT ON messages` count: 1
- `AFTER DELETE ON messages` count: 1
- `unicode61 remove_diacritics 2 tokenchars` count: 1
- `rowid           INTEGER PRIMARY KEY` count: 1
- `INSERT OR REPLACE` count: 0

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest missing from project dev dependencies**

- **Found during:** GREEN phase — tests written but could not run via `uv run python -m pytest`
- **Issue:** pyproject.toml had no dev dependencies section; pytest was not installed in the uv venv
- **Fix:** Added `[project.optional-dependencies] dev = ["pytest>=8.0"]` and `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `pythonpath = ["src"]` to pyproject.toml; ran `uv pip install pytest` to install into venv
- **Files modified:** pyproject.toml, uv.lock
- **Note:** `uv sync --extra dev` failed because server.exe was locked by a running process; used `uv pip install pytest` as workaround

## Known Stubs

None. `init_db()` is complete and fully wired — no placeholder returns, no TODO comments, no hardcoded empty values in the public interface.

## Threat Flags

No new threat surface beyond what was documented in the plan's threat model. All SQL uses parameterized queries (no string interpolation). FTS sync is done entirely via SQL triggers (no application-level sync logic).

## Self-Check

Files created/modified exist:
- `src/claude_history/db.py` — EXISTS
- `tests/test_db.py` — EXISTS
- `pyproject.toml` — modified (pytest dev dep added)

Commits exist:
- `c23719f` — test(02-01): add failing tests for init_db() — RED phase
- `b073817` — feat(02-01): implement init_db() — SQLite schema with FTS5 and WAL mode

## Self-Check: PASSED
