---
phase: 02-database-ingest
plan: "02"
subsystem: database
tags: [sqlite, fts5, ingest, zip, tdd, python]
dependency_graph:
  requires:
    - phase: 02-01
      provides: [src/claude_history/db.py, init_db]
  provides: [src/claude_history/ingest.py, ingest_zip]
  affects: [phase-3-search, phase-4-mcp-tools]
tech_stack:
  added: []
  patterns: [INSERT OR IGNORE for idempotent upsert, deferred module imports to avoid circular deps, logging to sys.stderr only]
key_files:
  created:
    - src/claude_history/ingest.py
    - tests/test_ingest.py
  modified:
    - pyproject.toml
decisions:
  - "INSERT OR IGNORE (not OR REPLACE) — append-only history records must not overwrite existing data"
  - "project=NULL hardcoded — Claude.ai export format does not include project metadata"
  - "All logging goes to sys.stderr — stdout is reserved for MCP stdio transport"
  - "Deferred imports of db.py and config.py inside functions to avoid circular imports at module load"
  - "Attachment content extracted via export ZIP entry path matching on conversation_id prefix"
metrics:
  duration: "~20min"
  completed: "2026-05-05"
  tasks_completed: 2
  files_changed: 3
requirements_satisfied: [INGEST-02, INGEST-03, INGEST-04, INGEST-05]
---

# Phase 2 Plan 2: Ingest (ingest.py) Summary

**ZIP parser that reads Claude.ai conversation exports and upserts 106 conversations / 4087 messages into SQLite FTS5 with idempotent re-run support.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-05
- **Completed:** 2026-05-05
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `ingest.py` reads a Claude.ai export ZIP, parses all `conversations.json` entries, and upserts conversations + messages into `history.db`
- Idempotent re-run: second pass reports `0 new, 106 already indexed — skipping 106` with zero row count change
- Attachment content extracted from ZIP entries matching `<conversation_id>/` prefix and merged into message content
- FTS5 index stays in sync via the sync triggers created by `init_db()` — no application-level FTS writes needed
- All 23 TDD tests pass; verified against real export (106 conversations, 4087 messages, 41 with attachment content)

## Task Commits

1. **Task 1: Uncomment ingest entry point** - `3f9e720` (chore)
2. **Task 2: RED — failing tests** - `4876d62` (test — 23 tests, all failing)
3. **Task 2: GREEN — implementation** - `30024dc` (feat — 23/23 passing)

_Note: Task 2 followed TDD: RED commit first, then GREEN commit._

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | 4876d62 | 23 tests written, all failing (ImportError — ingest.py did not exist) |
| GREEN (impl) | 30024dc | 23 tests passing |
| REFACTOR | N/A | No refactoring needed |

## Tests Written (23 total)

| Test Class | Tests | Behavior Verified |
|---|---|---|
| `TestParseConversations` | 4 | Returns list of dicts, required keys present, role/content mapped, timestamps parsed |
| `TestUpsertConversations` | 5 | Inserts conversations, inserts messages, idempotency (no duplicate rows), message count incremented, FTS synced |
| `TestIngestZip` | 5 | Opens ZIP, parses JSON, returns stats dict with new/skipped counts, attachment content extracted, incremental re-run |
| `TestAttachmentExtraction` | 4 | Attachment entry detected by path prefix, content merged into message body, missing attachment handled gracefully |
| `TestStats` | 5 | Stats keys present (conversations_new, conversations_skipped, messages_indexed, attachments_found), correct counts for fresh run vs. re-run |

## Files Created/Modified

- `src/claude_history/ingest.py` — 177 lines; `ingest_zip(zip_path, db_path)` public entry point; `_parse_conversations()`, `_upsert_conversations()`, `_extract_attachment_content()` helpers
- `tests/test_ingest.py` — 23 tests covering parse, upsert, full ingest, attachments, and stats
- `pyproject.toml` — `ingest` entry point uncommented (`uv run ingest` now wired to `claude_history.ingest:main`)

## Decisions Made

- **INSERT OR IGNORE over OR REPLACE:** Append-only history — re-running must never overwrite existing messages (matches `db.py` convention established in 02-01)
- **project=NULL hardcoded:** Claude.ai export ZIP does not include project metadata in any parseable field; NULL is the correct sentinel value
- **sys.stderr for all logging:** stdout contamination silently kills MCP stdio sessions — all `print()` / `logging` output goes to stderr
- **Deferred imports inside functions:** `db.py` and `config.py` imported at call time (not module load) to prevent circular import errors during test collection
- **Attachment content via path prefix matching:** ZIP entries under `<conversation_id>/` are treated as attachment files; content appended to the associated message body

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written. The TDD cycle was clean on first attempt.

### Known Issue (not auto-fixed — environmental)

**`uv run ingest` fails on Windows when MCP server is running**

- **Found during:** Human verification (Step 1)
- **Issue:** `uv` tries to install/update into `.venv` but `server.exe` is locked by the running MCP process; results in a `PermissionError` or silent hang
- **Workaround:** Call `.venv/Scripts/python.exe -m claude_history.ingest <zip-path>` directly — bypasses uv's venv management and runs immediately
- **Impact:** Ingest functionality is fully working; only the `uv run ingest` shortcut is affected on Windows when server is active
- **Resolution:** No code change needed; documented for users in README (deferred to Phase 4 docs task)

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** Plan executed exactly as written. One environmental issue (Windows file lock) documented but does not affect correctness.

## Plan Verification Results (Human UAT)

All steps from the plan's verify block passed during human checkpoint review:

| Step | Command / Check | Result |
|------|-----------------|--------|
| 1 | `uv run ingest <zip>` (via .venv/Scripts/python.exe) | `106 conversations found in ZIP`, `106 new, 0 already indexed`, `indexed 4087 messages (41 with attachment content)` |
| 2 | Row counts via sqlite3 | conversations=106, messages=4087, messages_fts=4087 (all match) |
| 3 | Re-run (idempotency) | `0 new, 106 already indexed — skipping 106`, row counts unchanged |
| 4 | FTS search via Python | `python` query returned 3 snippet rows with highlighted matches |
| 5 | snake_case tokenizer | `search_conversations` returned 0 rows (correct — no false positive), no error |

## Issues Encountered

- Windows file lock on `server.exe` blocked `uv run ingest` shortcut — resolved by calling `.venv/Scripts/python.exe` directly (see Deviations above)

## Known Stubs

None. `ingest_zip()` is fully wired — reads real ZIP, writes real rows, returns real stats.

## Threat Flags

No new threat surface beyond the plan's threat model. All SQL uses parameterized queries. ZIP extraction reads only JSON and known attachment entries — no path traversal risk (entries filtered by known path patterns before extraction).

## Self-Check

Files created/modified exist:
- `src/claude_history/ingest.py` — EXISTS
- `tests/test_ingest.py` — EXISTS
- `pyproject.toml` — modified (ingest entry point uncommented)

Commits exist:
- `3f9e720` — chore(02-02): uncomment ingest entry point in pyproject.toml
- `4876d62` — test(02-02): add failing tests for ingest.py helper functions (RED phase — 23 tests)
- `30024dc` — feat(02-02): implement ingest.py — ZIP parsing, upsert, incremental ingest (GREEN — 23/23 passing)

## Self-Check: PASSED

## Next Phase Readiness

- `history.db` now contains 106 real conversations and 4087 FTS-indexed messages — Phase 3 search tools have a live dataset to query against
- `init_db()` + `ingest_zip()` form a complete write path; Phase 3 only needs to add read/search functions
- No blockers for Phase 3

---
*Phase: 02-database-ingest*
*Completed: 2026-05-05*
