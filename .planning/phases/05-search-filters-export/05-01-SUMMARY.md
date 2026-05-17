---
phase: 05-search-filters-export
plan: "01"
subsystem: search
tags: [search, filters, export, fts5, sqlite, date-range, role-filter]
dependency_graph:
  requires: []
  provides: [SRCH-01, SRCH-02, EXP-01]
  affects: [search_conversations, export_conversation]
tech_stack:
  added: []
  patterns:
    - "[:10] prefix comparison for ISO timestamp date filtering (avoids T-separator boundary failure)"
    - "Parameterized SQL role filter (AND m.role = ?) in FTS JOIN — no string interpolation"
    - "Bulk created_at lookup via IN() for post-dedup date filtering"
    - "pathlib Path.resolve() for absolute path return from file write"
key_files:
  created:
    - tests/test_search_filters.py
  modified:
    - src/claude_history/search.py
    - src/claude_history/server.py
decisions:
  - "Date filter uses [:10] prefix comparison not direct ISO string comparison (Pitfall 1 — T separator silently breaks date_to boundary)"
  - "Date filter applied post-dedup, pre-limit-slice via single bulk SELECT id,created_at FROM conversations WHERE id IN (...)"
  - "Role filter applied in SQL (_fts_rows AND m.role = ?) not in Python post-processing — per D-04"
  - "No input validation on role_filter — malformed values return [] naturally per D-05"
  - "file_path=None preserves existing export_conversation behavior — fully backward compatible"
  - "export_conversation returns 'Written to: {Path.resolve()}' for machine-readable absolute path on Windows"
metrics:
  duration: "4 minutes"
  completed_date: "2026-05-16"
  tasks_completed: 2
  files_changed: 3
---

# Phase 5 Plan 01: Search Filters + Export Summary

## One-liner

Date range and role filtering on search_conversations via SQL parameterization and post-dedup [:10] prefix comparison; file export via pathlib write_text with absolute path return.

## What Was Built

### Task 1: search.py extensions (SRCH-01, SRCH-02)

Three changes to `src/claude_history/search.py`:

**`_passes_date_filter(created_at, date_from, date_to) -> bool`** (new helper)
- Slices `created_at[:10]` to get `YYYY-MM-DD` prefix before comparing
- Critical fix for Pitfall 1: direct ISO timestamp comparison with `date_to` silently excludes same-day conversations because `'2026-03-05T...' > '2026-03-05'` lexicographically
- Inclusive on both bounds; empty/null `created_at` passes through defensively

**`_fts_rows(cur, fts_query, role=None) -> list`** (updated)
- When `role` is not None, appends `AND m.role = ?` to the WHERE clause with parameterized binding
- No new JOINs needed — `messages.role` is already accessible from the existing `JOIN messages m ON messages_fts.rowid = m.rowid`
- Backward compatible: `role=None` produces identical SQL to the original

**`search_conversations(..., date_from=None, date_to=None, role_filter=None) -> list[dict]`** (updated)
- Three new optional parameters, all defaulting to None
- `role_filter` passed to both the primary and fallback `_fts_rows` calls
- Date filter applied AFTER BM25 dedup (after `best` dict is built), BEFORE `ranked[:limit]` slice — via a single bulk `SELECT id, created_at FROM conversations WHERE id IN (...)` query, then list comprehension
- This ensures `limit` is respected on the date-filtered set, not the pre-filter set

### Task 2: server.py extensions (EXP-01)

Two changes to `src/claude_history/server.py`:

**`search_conversations` tool** (updated)
- Added `date_from: str | None = None`, `date_to: str | None = None`, `role_filter: str | None = None` to the tool function signature (after `include_full_content`)
- `project_filter` kept for schema compatibility (not applied)
- `_search()` call updated to pass all three new params through
- Docstring updated with Args entries for all three new params

**`export_conversation(id, file_path=None)` tool** (updated)
- Added `file_path: str | None = None` parameter
- When `file_path` is provided: creates parent directories recursively (`mkdir(parents=True, exist_ok=True)`), writes markdown as UTF-8, returns `f"Written to: {output_path.resolve()}"` with the absolute Windows path
- When `file_path` is None: returns markdown string (existing behavior — fully backward compatible)
- `Path` was already imported; no new imports needed
- No `print()` calls — all errors via `log.error()` to stderr

### TDD Red/Green Cycle

Written to `tests/test_search_filters.py`:
- 9 tests for `_passes_date_filter` (boundary cases, empty passthrough, critical same-day date_to)
- 2 tests for `_fts_rows` role parameter signature
- 6 tests for `search_conversations` signature (three new params, defaults)
- 4 functional tests (skipped when history.db absent)

All 17 non-skipped tests pass (4 skipped — DB integration tests require live history.db).

## Key Decisions Honored

- **D-01**: date filter on `conversations.created_at` (conversation start date, not message date)
- **D-02**: Both bounds inclusive (>= date_from, <= date_to using prefix)
- **D-03**: Date filter post-FTS-aggregation, pre-limit-slice
- **D-04**: Role filter in SQL JOIN predicate, not Python post-processing
- **D-05**: No role_filter validation — malformed values return [] naturally from SQL
- **D-06**: file_path provided → write + return "Written to: ..." (not markdown)
- **D-07**: file_path=None → return markdown string (backward compatible)
- **D-08**: Overwrite existing files silently
- **D-09**: Create parent directories recursively

## Patterns Established

- **ISO timestamp date comparison**: Always use `[:10]` prefix slice when comparing `conversations.created_at` against bare `YYYY-MM-DD` date strings. Never compare the full ISO timestamp directly.
- **SQL role filtering pattern**: `AND m.role = ?` with parameterized binding inside the FTS JOIN — no string interpolation, no validation needed.
- **Bulk pre-filter pattern**: When filtering ranked results pre-limit-slice, fetch all needed columns in a single `WHERE id IN (...)` query rather than per-item queries.
- **export file write pattern**: `Path(file_path).parent.mkdir(parents=True, exist_ok=True)` then `write_text(encoding="utf-8")` then `return f"Written to: {path.resolve()}"`.

## Deviations from Plan

None — plan executed exactly as written. The TDD cycle was implemented using the plan's `tdd="true"` flag: RED phase committed first (`4167d7b`), GREEN phase committed after (`a082edf`), no REFACTOR phase needed (code was already clean).

## Known Stubs

None — all new parameters are fully wired through from tool signature to SQL/filesystem.

## Threat Flags

No new threat surface beyond what was documented in the plan's `<threat_model>`. T-05-01 through T-05-06 were evaluated during planning; all implemented mitigations are in place:
- T-05-01 (role filter injection): mitigated via `AND m.role = ?` parameterized SQL — verified
- T-05-03 (export path elevation): accepted — server runs as user's own process

## Self-Check

Files created/modified:
- tests/test_search_filters.py: EXISTS
- src/claude_history/search.py: EXISTS
- src/claude_history/server.py: EXISTS

Commits:
- 4167d7b: test(05-01): add failing tests for date/role filter extensions (RED)
- a082edf: feat(05-01): extend search.py with date/role filters (GREEN)
- 1d788ea: feat(05-01): extend server.py with date/role search filters and file export (EXP-01)

## Self-Check: PASSED
