---
phase: 02-database-ingest
verified: 2026-05-05T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 2: Database + Ingest Verification Report

**Phase Goal:** A populated SQLite database with a correctly configured FTS5 index that Claude Code can query, built from a real Claude.ai export
**Verified:** 2026-05-05
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `uv run ingest <export.zip>` on a fresh database populates conversations and messages tables with no errors | VERIFIED | Human UAT: 106 conversations, 4087 messages ingested. `ingest_zip()` fully implemented in `src/claude_history/ingest.py` (177 lines). No print() statements; all logging to stderr. 39/39 tests pass. |
| 2 | Re-running ingest on the same ZIP produces identical row counts — no duplicates (idempotent) | VERIFIED | Human UAT: second run logged `0 new, 106 already indexed — skipping 106` with unchanged row counts. UUID pre-check (`SELECT 1 FROM conversations WHERE id = ?`) + `INSERT OR IGNORE` both confirmed in source at lines 103–106 and 115–126. |
| 3 | Re-running ingest on an updated ZIP only processes new conversations (incremental behavior confirmed by log output) | VERIFIED | Same UUID-check skip path produces `%d new, %d already indexed — skipping %d` log output. Confirmed by UAT step 3 and structural code review of `ingest_zip()`. |
| 4 | An FTS5 search query returns ranked results with snippets, and snake_case terms like `search_conversations` match as a single token | VERIFIED | Live DB query: `python` FTS MATCH returned 2 snippets with `**python**` highlighting. `unicode61 remove_diacritics 2 tokenchars '-_'` tokenizer confirmed in `db.py` line 58. Test `TestFtsTokenizer::test_snake_case_token_matches_as_single_token` passes. |
| 5 | Text attachment content is present in the FTS index; binary attachments are skipped without error | VERIFIED | `build_message_content()` appends `extracted_content` from attachments at lines 46–49. UAT reported 41 messages with attachment content indexed. `files[]` array (binary refs) is never read — silently skipped by design. Test `TestBuildMessageContent::test_files_array_ignored` passes. |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/claude_history/db.py` | `init_db(db_path: Path) -> sqlite3.Connection` — idempotent schema creation | VERIFIED | 79 lines (min 50). Exports `init_db`. WAL pragma before executescript. All 3 tables and 3 triggers with IF NOT EXISTS. No INSERT OR REPLACE. |
| `src/claude_history/ingest.py` | `main()`, `ingest_zip()`, `build_message_content()`, `normalize_ts()` | VERIFIED | 177 lines (min 90). All 4 symbols exported. No print(). logging to sys.stderr at module level. INSERT OR IGNORE throughout. project=NULL hardcoded. |
| `pyproject.toml` | `ingest = "claude_history.ingest:main"` uncommented | VERIFIED | Line 15: `ingest = "claude_history.ingest:main"` — confirmed active, no leading `#`. |
| `history.db` | Populated database — 106 conversations, 4087 messages, FTS indexed | VERIFIED | 10.4 MB on disk. Live queries: conversations=106, messages=4087, messages_fts=4087, journal_mode=wal. Gitignored via `*.db` glob pattern. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `messages_fts` virtual table | `messages` table | `content_rowid="rowid"` in FTS5 CREATE | VERIFIED | Line 57 of db.py: `content_rowid="rowid"` confirmed |
| `messages_ai` trigger | `messages_fts` | `AFTER INSERT ON messages` | VERIFIED | Line 61 of db.py: `CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages` confirmed |
| `messages_ad` trigger | `messages_fts` | `AFTER DELETE ON messages` | VERIFIED | Line 66 of db.py: `CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages` confirmed |
| `ingest_zip()` | `db.init_db()` | `from claude_history.db import init_db` (deferred import inside function) | VERIFIED | Line 80 of ingest.py: import inside `ingest_zip()` — deferred to avoid circular imports |
| `main()` | `config.DB_PATH` | `from claude_history.config import DB_PATH` (deferred import inside function) | VERIFIED | Line 175 of ingest.py: import inside `main()` |
| `INSERT OR IGNORE INTO messages` | `messages_ai` trigger | `AFTER INSERT` trigger fires automatically on every row | VERIFIED | No application-level FTS writes in ingest.py — triggers handle all FTS sync |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `history.db` (messages_fts) | FTS index rows | AFTER INSERT trigger on messages table, populated by `ingest_zip()` reading `conversations.json` from ZIP | Yes — 4087 rows confirmed by live query | FLOWING |
| `ingest_zip()` conversations | `conversations` list | `json.load(zf.open("conversations.json"))` from real Claude.ai export ZIP | Yes — 106 real conversations from live ingest | FLOWING |
| `ingest_zip()` messages | `content_text` per message | `build_message_content(msg)` — reads `msg["text"]` + `att["extracted_content"]` | Yes — 4087 messages, 41 with attachment content | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| FTS search returns snippets | `SELECT snippet(...) FROM messages_fts WHERE messages_fts MATCH 'python' LIMIT 2` | 2 rows with `**python**` highlighted | PASS |
| WAL mode active on live DB | `PRAGMA journal_mode` on history.db | `wal` | PASS |
| Row counts match real export | `SELECT count(*) FROM conversations/messages/messages_fts` | 106 / 4087 / 4087 | PASS |
| 39 unit tests pass | `python -m pytest tests/test_db.py tests/test_ingest.py -v` | 39 passed, 0 failed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DB-01 | 02-01-PLAN | SQLite FTS5 virtual table | SATISFIED | `messages_fts USING fts5(...)` confirmed. NOTE: REQUIREMENTS.md says "trigram tokenizer" but ROADMAP and Phase 1 research locked `unicode61 remove_diacritics 2 tokenchars '-_'`. The ROADMAP contract and phase goal are satisfied; REQUIREMENTS.md wording is stale. |
| DB-02 | 02-01-PLAN | FTS5 content table pattern with sync triggers | SATISFIED | `content="messages"`, `content_rowid="rowid"`, AFTER INSERT/DELETE/UPDATE triggers confirmed. NOTE: REQUIREMENTS.md says "BEFORE DELETE / AFTER INSERT" — actual triggers use AFTER for both, matching ROADMAP and SQLite FTS5 §4.4.3. |
| DB-03 | 02-01-PLAN | WAL journal mode | SATISFIED | `conn.execute("PRAGMA journal_mode=WAL")` before executescript. Live DB confirms `journal_mode=wal`. |
| DB-04 | 02-01-PLAN | Schema stores conversations and messages with required columns | SATISFIED | conversations: id, title, project, created_at, updated_at, message_count. messages: rowid, id, conversation_id, role, content, position, created_at. |
| INGEST-02 | 02-02-PLAN | Ingest script loads all conversations and messages from ZIP | SATISFIED | `ingest_zip()` reads `conversations.json` from ZIP, upserts all records. 106 conversations / 4087 messages loaded from real export. |
| INGEST-03 | 02-02-PLAN | No duplicate conversations on re-run | SATISFIED | UUID pre-check + INSERT OR IGNORE prevents duplicates. Re-run confirmed idempotent by UAT. NOTE: REQUIREMENTS.md says "INSERT OR REPLACE on conversation UUID" — implementation uses INSERT OR IGNORE (correct approach to avoid FTS rowid corruption). Goal achieved; REQUIREMENTS.md describes a mechanism, not the outcome. |
| INGEST-04 | 02-02-PLAN | Incremental — existing conversations skipped | SATISFIED | `SELECT 1 FROM conversations WHERE id = ?` + continue on match. Log output: `0 new, 106 already indexed — skipping 106` confirmed by UAT. |
| INGEST-05 | 02-02-PLAN | Attachment content indexed; binary files skipped | SATISFIED | `build_message_content()` reads `extracted_content` from `attachments[]`. `files[]` entries silently ignored. 41 attachment-content messages indexed from real export. |

**Requirements coverage: 8/8 satisfied**

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TODOs, placeholders, print() statements, INSERT OR REPLACE, empty returns, or hardcoded stubs found | — | — |

Structural grep gates confirmed clean:
- `print(` in ingest.py: 0 matches
- `INSERT OR REPLACE` in ingest.py: 0 matches in executable code (1 mention in docstring only)
- `INSERT OR REPLACE` in db.py: 0 matches
- `stream=sys.stderr` in ingest.py: 1 match (at module level, correct)
- `NULL` in ingest.py conversations INSERT: 1 match (correct hardcoded sentinel)

---

### Human Verification Required

None. All behavioral checks were completed by the developer during the UAT gate in plan 02-02 (Task 3 human-verify checkpoint). Results are documented in 02-02-SUMMARY.md and match what the automated verification confirms:
- 106 conversations, 4087 messages ingested from real export
- Re-run produces 0 new, 106 skipped (idempotent confirmed)
- FTS `python` query returns snippets
- snake_case tokenizer raises no error and correctly handles the term as a single token

---

### REQUIREMENTS.md Wording Discrepancies (informational — not blocking)

Three requirements in REQUIREMENTS.md describe implementation mechanisms that were superseded by Phase 1 research decisions recorded in the ROADMAP:

1. **DB-01** says "trigram tokenizer" — Phase 1 schema discovery determined `unicode61 remove_diacritics 2 tokenchars '-_'` is the correct tokenizer for snake_case support. The ROADMAP locks this in. The functional goal (FTS5 index with snake_case support) is fully achieved.

2. **DB-02** says "BEFORE DELETE / AFTER INSERT triggers" — SQLite FTS5 §4.4.3 requires AFTER triggers for content table sync. The ROADMAP plan explicitly calls for AFTER INSERT/DELETE/UPDATE. The functional goal (FTS stays in sync with messages) is fully achieved.

3. **INGEST-03** says "INSERT OR REPLACE on conversation UUID" — the implementation uses INSERT OR IGNORE plus a UUID pre-check. INSERT OR REPLACE changes rowids and would corrupt the FTS content_rowid links; INSERT OR IGNORE is the technically correct choice. The functional goal (no duplicate conversations) is fully achieved.

These discrepancies indicate REQUIREMENTS.md was not updated to reflect Phase 1 research outcomes. They are informational only and do not affect phase goal achievement. Recommended: update REQUIREMENTS.md to match actual implementation decisions before Phase 3.

---

### Gaps Summary

No gaps. All 5 ROADMAP success criteria are verified. All 8 requirement IDs assigned to Phase 2 are satisfied. Both source files are substantive, correctly wired, and data flows through the full pipeline to a populated live database. The 39-test suite passes cleanly.

---

_Verified: 2026-05-05_
_Verifier: Claude (gsd-verifier)_
