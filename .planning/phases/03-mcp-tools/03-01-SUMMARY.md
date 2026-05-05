---
phase: 03-mcp-tools
plan: "01"
subsystem: database
tags: [sqlite, fts5, bm25, search, python]

# Dependency graph
requires:
  - phase: 02-ingest
    provides: "history.db with messages and messages_fts FTS5 virtual table (106 conversations, 4087 messages)"
  - phase: 01-scaffolding-schema-discovery
    provides: "db.py init_db(), config.py DB_PATH, project scaffold"
provides:
  - "search.py with search_conversations() — FTS5 BM25 ranked search, one result per conversation"
  - "Private _fts_rows() — raw FTS5 query with bm25() ordering"
  - "Private _get_snippet() — FTS5 snippet() extraction for best-matching message"
  - "D-05 FTS5 sanitization fallback (OperationalError → double-quoted phrase)"
  - "D-06 empty-result safety (returns [] never raises)"
affects: [03-02, server.py, MCP tools]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "bm25-cannot-group-by: FTS5 bm25() is only valid in direct FTS virtual table query — use Python aggregation dict to dedup per-conversation"
    - "fts5-fallback: wrap FTS5 queries in try/except OperationalError; re-run as double-quoted phrase search"
    - "content-table-rowid: snippet() requires MATCH active in same query; filter by rowid to restrict to target row"

key-files:
  created:
    - src/claude_history/search.py
  modified: []

key-decisions:
  - "bm25() cannot appear in a GROUP BY subquery in SQLite FTS5 — Python dict aggregation is the correct dedup pattern"
  - "token_count=64 for snippet() calibrated to ~300 chars average (verified in RESEARCH.md)"
  - "D-05 fallback: quote.replace('\"', '\"\"') before wrapping in double quotes to handle embedded quotes"

patterns-established:
  - "FTS5 two-step: _fts_rows() returns (conv_id, rowid, score) rows; caller aggregates in Python before calling _get_snippet() per best rowid"
  - "Connection lifecycle: init_db(DB_PATH) in function body, conn.close() in finally block — no global connection"
  - "row_factory=sqlite3.Row set after init_db() call, not inside init_db()"

requirements-completed: [TOOL-01, TOOL-02]

# Metrics
duration: 1min
completed: "2026-05-05"
---

# Phase 03 Plan 01: FTS5 Search Module Summary

**FTS5 BM25 search module with Python aggregation dedup, snippet extraction, and OperationalError fallback — search_conversations() is the query layer for all MCP search tools**

## Performance

- **Duration:** 1 min
- **Started:** 2026-05-05T20:54:25Z
- **Completed:** 2026-05-05T20:55:28Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created search.py implementing the complete FTS5 search pipeline used by server.py
- Solved the bm25-cannot-GROUP-BY constraint with Python dict aggregation for per-conversation dedup
- All 7 acceptance criteria (D-01 through D-06 + key structure checks) verified against live history.db (106 conversations, 4087 messages)

## Task Commits

1. **Task 1: Create search.py with _fts_rows, _get_snippet, and search_conversations** - `5a426f8` (feat)

**Plan metadata:** pending final commit

## Files Created/Modified
- `src/claude_history/search.py` - FTS5 search module: _fts_rows(), _get_snippet(), search_conversations(); 122 lines

## Decisions Made
- Used Python dict aggregation (not SQL GROUP BY) for per-conversation dedup because bm25() is invalid outside direct FTS virtual table queries — this is a SQLite FTS5 constraint, not a design choice
- token_count=64 in snippet() to target ~300 char average (per RESEARCH.md verification on live DB)
- OperationalError fallback escapes embedded double-quotes before phrase-quoting to avoid further FTS5 syntax errors

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Minor: `uv run` failed with "file in use" error on first attempt (server.exe locked by another process). Used `uv run --no-sync` as workaround — all verification commands passed cleanly.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - search_conversations() reads from live history.db and returns real FTS5 results.

## Threat Flags

No new threat surface introduced beyond what is specified in the plan's threat model. All three threats (T-03-01-01 through T-03-01-03) are mitigated as specified:
- T-03-01-01: Parameterized queries used throughout; OperationalError fallback implemented
- T-03-01-02: limit=10 default applied (D-01)
- T-03-01-03: Read-only SQLite access, local filesystem only

## Next Phase Readiness
- search_conversations() is ready for server.py tool wiring (Plan 03-02)
- The function signature matches what server.py will call: search_conversations(query, limit=10, include_full_content=False) -> list[dict]
- All 6 result keys (id, title, created_at, project, match_count, snippet) are present and documented

## Self-Check: PASSED

- FOUND: src/claude_history/search.py
- FOUND: commit 5a426f8 (feat(03-01): implement FTS5 search_conversations with BM25 ranking)

---
*Phase: 03-mcp-tools*
*Completed: 2026-05-05*
