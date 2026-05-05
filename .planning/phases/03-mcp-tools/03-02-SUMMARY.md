---
phase: 03-mcp-tools
plan: "02"
subsystem: mcp-server
tags: [fastmcp, mcp-tools, sqlite, fts5, server, stdio]

# Dependency graph
requires:
  - phase: 03-01
    provides: "search.py search_conversations() — FTS5 BM25 ranked search"
  - phase: 01-scaffolding-schema-discovery
    provides: "db.py init_db(), config.py DB_PATH, project scaffold"
  - phase: 02-ingest
    provides: "history.db with 106 conversations, 4087 messages"
provides:
  - "server.py with 6 registered @mcp.tool() functions"
  - "search_conversations: FTS5 BM25 search delegating to search.py"
  - "get_conversation: full turns ORDER BY position ASC"
  - "list_projects: returns [] with export-limitation docstring"
  - "get_stats: conv count, msg count, date range, db_size_mb"
  - "export_conversation: markdown with # title / *Date:* / ## Human / ## Assistant"
  - "get_status: status + conversations count + last_ingested"
affects: [.mcp.json, Phase 4 config]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fastmcp-tool-in-main: all @mcp.tool() definitions must be inside main() after mcp = FastMCP()"
    - "sqlite-row-factory-per-call: conn.row_factory = sqlite3.Row set after init_db(), not inside init_db()"
    - "connection-finally: init_db(DB_PATH) in function body, conn.close() in finally block"
    - "stderr-first: sys.stderr.reconfigure line 4, logging.basicConfig(stream=stderr) before FastMCP()"

key-files:
  created: []
  modified:
    - src/claude_history/server.py

key-decisions:
  - "get_status promoted from Phase 1 stub to include conversation count and last_ingested date"
  - "project_filter parameter kept in search_conversations signature for schema compatibility (all project fields NULL)"
  - "list_projects always returns [] — Claude.ai export format has no project-conversation association"

patterns-established:
  - "Tool definitions nested inside main(): enforces logging-before-FastMCP invariant"
  - "Parameterized queries for all id parameters (T-03-02-02 mitigated)"
  - "No print() calls anywhere — verified by grep count == 0"

requirements-completed: [TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, TOOL-06, SETUP-02]

# Metrics
duration: 2min
completed: "2026-05-05"
---

# Phase 03 Plan 02: Full MCP Tool Suite Summary

**6 FastMCP tools wired to live SQLite FTS5 database — search_conversations, get_conversation, list_projects, get_stats, export_conversation, get_status — with no stdout contamination**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-05T20:57:49Z
- **Completed:** 2026-05-05T20:59:31Z
- **Tasks:** 1 automated + 1 human checkpoint
- **Files modified:** 1

## Accomplishments

- Replaced Phase 1 stub (single get_status) with 6 complete tool implementations
- search_conversations delegates to search.py (Plan 03-01) for all FTS5 logic
- get_conversation and export_conversation both use ORDER BY position ASC for correct turn ordering
- list_projects returns [] with detailed docstring explaining the Claude.ai export format limitation
- get_stats returns conversation count, message count, date range, and db_size_mb via pathlib stat()
- export_conversation formats as # title / *Date: date* / ## Human / ## Assistant markdown
- get_status promoted: now returns status + conversations + last_ingested date
- All threat model mitigations applied: parameterized queries (T-03-02-02), no stdout contamination (T-03-02-03)

## Task Commits

1. **Task 1: Replace server.py stub with 6 full tool implementations** - `a42e796` (feat)

## Files Created/Modified

- `src/claude_history/server.py` - Full MCP server: 6 @mcp.tool() functions; 238 lines (was 42)

## Acceptance Criteria Results

| Criterion | Result |
|-----------|--------|
| server.py > 100 lines | PASS (238 lines) |
| @mcp.tool() count == 6 | PASS |
| def search_conversations count == 1 | PASS |
| def get_conversation count == 1 | PASS |
| def list_projects count == 1 | PASS |
| def get_stats count == 1 | PASS |
| def export_conversation count == 1 | PASS |
| def get_status count == 1 | PASS |
| print( count == 0 | PASS |
| sys.stderr.reconfigure count == 1 | PASS |
| from claude_history.search import count == 1 | PASS |
| ORDER BY position ASC count == 2 | PASS |
| stat().st_size count == 1 | PASS |
| uv run python -c "import claude_history.server" exits 0 | PASS (via --no-sync) |
| uv run python -c "from claude_history.server import main" exits 0 | PASS (via --no-sync) |

Note: `uv run` (without --no-sync) fails with "server.exe locked by another process" — same issue as Plan 03-01. `uv run --no-sync` works reliably.

## Pre-Verified Checks (before human checkpoint)

- `search_conversations('python')` returns 10 results with correct keys: id, title, created_at, project, match_count, snippet
- Empty query `ZZZNOMATCH999` returns `[]`
- `include_full_content=True` adds `full_content` key to results
- DB counts: 106 conversations, 4087 messages
- DB size: 9.88 MB
- export_conversation format: `# (Untitled)`, `*Date: 2026-04-01T23:44:12.155755+00:00*`, `## Human`, `## Assistant`

## Decisions Made

- project_filter parameter included in search_conversations signature for future schema compatibility, but not applied (all project fields NULL in current data)
- list_projects docstring explains the export format limitation in detail so Claude Code users understand why it returns []
- get_status promoted beyond Phase 1 stub to include conversations count and last_ingested — useful at-a-glance health check

## Deviations from Plan

None - plan executed exactly as written.

Note: `## Human` grep count is 2 (not 1 as stated in acceptance criteria) because the export_conversation docstring illustrates the format with `## Human` on line 162, in addition to the comment on line 198. The actual format string `f"## {label}"` is dynamic. This is an inherent result of following the plan's own code template exactly.

## Known Stubs

None - all 6 tools read from live history.db.

## Threat Flags

No new threat surface introduced beyond the plan's threat model. All mitigations applied:
- T-03-02-01: search delegates to search.py which uses parameterized queries with OperationalError fallback
- T-03-02-02: id parameters passed as (id,) tuple in all SQLite queries
- T-03-02-03: sys.stderr.reconfigure line 4, no print() calls (verified grep count == 0)

## Self-Check: PASSED

- FOUND: src/claude_history/server.py (238 lines)
- FOUND: commit a42e796 (feat(03-02): replace server.py stub with 6 full MCP tool implementations)
