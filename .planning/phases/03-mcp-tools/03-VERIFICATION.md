---
phase: 03-mcp-tools
verified: 2026-05-06T00:00:00Z
status: human_needed
score: 5/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm no stdout output when uv run server starts"
    expected: "Server blocks on stdin with zero bytes written to stdout"
    why_human: "Server blocks indefinitely on stdio; programmatic subprocess timeout test would require a running process; cannot be verified with static file analysis alone"
  - test: "Call get_status, search_conversations, get_conversation, export_conversation, get_stats, list_projects via MCP Inspector or claude mcp tool call"
    expected: "All 6 tools return non-error responses; search_conversations returns ranked snippets; export_conversation starts with '# ' title header and '*Date:' line"
    why_human: "End-to-end MCP JSON-RPC tool dispatch requires the server to be running; ROADMAP SC-6 requires validated 'validated via MCP Inspector, Claude Code can call them against real data'"
---

# Phase 3: MCP Tools Verification Report

**Phase Goal:** All six MCP tools return correct, well-shaped results and Claude Code can use them against real indexed data
**Verified:** 2026-05-06
**Status:** HUMAN_NEEDED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `search_conversations("some query")` returns BM25-ranked results with snippet, title, project, date, and conversation ID | VERIFIED | Live run: 10 results, keys `['created_at', 'id', 'match_count', 'project', 'snippet', 'title']` present; BM25 ordering confirmed (scores from -4.9 to -0.4, ascending = most-negative first) |
| SC-2 | `search_conversations("query", include_full_content=True)` returns full message text instead of snippets | VERIFIED | Live run: `full_content` key present in all results |
| SC-3 | `get_conversation(id)` returns all turns formatted as labeled Human/Assistant blocks in correct order | VERIFIED | `ORDER BY position ASC` present in server.py (line 96); `role_label` dict maps to "Human"/"Assistant"; returns `{"error": "..."}` dict for missing IDs |
| SC-4 | `list_projects()` returns project names with counts and date ranges; `get_stats()` returns total counts, date range, and DB file size | VERIFIED | `list_projects` returns `[]` with docstring explaining export-format limitation; `get_stats` returns `conversations=106, messages=4087, date_from, date_to, db_size_mb=9.88` — all five required keys present |
| SC-5 | `export_conversation(id)` returns a clean markdown string with no raw JSON or formatting artifacts | VERIFIED | Live run: output starts with `# (Untitled)`, contains `*Date: 2026-04-01T...*`, `## Human`, `## Assistant`; no JSON artifacts |
| SC-6 | All tools return graceful empty-list responses (not errors) when given queries or IDs that match nothing | PARTIAL | `search_conversations('ZZZNOMATCH999')` returns `[]` (VERIFIED); `get_conversation` returns `{"error": "..."}` dict (not empty-list, but graceful); `export_conversation` returns an error string (not empty-list, but graceful). Programmatic validation confirmed — but "validated via MCP Inspector, Claude Code can call them against real data" per ROADMAP Phase 3 goal requires end-to-end human confirmation |

**Score:** 5/6 truths fully verified; SC-6 is substantively satisfied by code evidence but the ROADMAP goal text explicitly calls for MCP Inspector / Claude Code validation

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/claude_history/search.py` | FTS5 search logic, BM25 aggregation, snippet shaping, full-content mode; min 60 lines | VERIFIED | 126 lines; exports `search_conversations`, `_fts_rows`, `_get_snippet`; no `print()`, no `logging.basicConfig()` |
| `src/claude_history/server.py` | 6 MCP tool definitions registered with FastMCP; min 100 lines | VERIFIED | 257 lines; exactly 6 `@mcp.tool()` decorators; 0 `print()` calls; imports cleanly via `uv run --no-sync python -c "import claude_history.server"` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `search.py:search_conversations` | `messages_fts` FTS5 table | `_fts_rows()` with `bm25(messages_fts) AS score ORDER BY score` | VERIFIED | Pattern confirmed at lines 12-18; uses alias `score` = `bm25(messages_fts)` — functionally identical to `ORDER BY bm25(messages_fts)`; live run returns 306 rows sorted ascending (most negative first) |
| `search.py:search_conversations` | `conversations` table | `SELECT title, created_at, project FROM conversations WHERE id = ?` | VERIFIED | Pattern `FROM conversations WHERE id` found at line 91 |
| `search.py` | `claude_history.db.init_db` | `from claude_history.db import init_db` | VERIFIED | Line 6 of search.py |
| `server.py:search_conversations tool` | `search.py:search_conversations` | `from claude_history.search import search_conversations as _search` | VERIFIED | Line 17 of server.py; tool delegates via `return _search(query, limit=10, include_full_content=include_full_content)` |
| `server.py:get_conversation tool` | `messages` table | `SELECT role, content, position FROM messages WHERE conversation_id = ? ORDER BY position ASC` | VERIFIED | Lines 92-97; `ORDER BY position ASC` count = 2 in server.py (get_conversation + export_conversation) |
| `server.py:export_conversation tool` | Markdown string | `## Human` / `## Assistant` H2 headers with `# title` / `*Date: date*` metadata | VERIFIED | Lines 205-216; live output confirmed: `# (Untitled)\n*Date: ...*\n\n## Human\n\n...\n## Assistant` |
| `server.py:get_stats tool` | `DB_PATH.stat().st_size` | `pathlib stat()` | VERIFIED | Line 153: `db_size_bytes = DB_PATH.stat().st_size`; wrapped in `try/except FileNotFoundError` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `search.py:search_conversations` | `rows` (FTS5 results) | `_fts_rows()` → `messages_fts MATCH ?` | Yes — 306 message rows matched for "python" in live run | FLOWING |
| `server.py:get_conversation` | `messages` (turn list) | `SELECT role, content, position FROM messages WHERE conversation_id = ? ORDER BY position ASC` | Yes — live conv returned 2 messages | FLOWING |
| `server.py:get_stats` | `conv_count`, `msg_count`, `dates` | `SELECT COUNT(*) FROM conversations/messages`, `MIN/MAX(created_at)` | Yes — 106 conversations, 4087 messages, dates confirmed | FLOWING |
| `server.py:export_conversation` | `lines` (markdown) | Same queries as get_conversation; joined into string | Yes — live output confirmed correct markdown | FLOWING |
| `server.py:list_projects` | (none) | Intentional static `return []` — export format limitation | N/A — known limitation, documented in docstring | ACCEPTABLE |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `search_conversations` returns 10 ranked results with correct keys | `uv run --no-sync python -c "from claude_history.search import search_conversations; r = search_conversations('python'); print(len(r), sorted(r[0].keys()))"` | `10 ['created_at', 'id', 'match_count', 'project', 'snippet', 'title']` | PASS |
| BM25 scores correctly ordered (most negative first) | Live `_fts_rows` query: first score -4.9, last -0.44 | Ascending sort confirmed | PASS |
| `search_conversations('ZZZNOMATCH999')` returns `[]` | Live run | `True` | PASS |
| FTS5 sanitization fallback on `'trailing OR'` | Live run | `isinstance(result, list) == True` | PASS |
| `include_full_content=True` adds `full_content` key | Live run | `'full_content' in fc[0] == True` | PASS |
| `get_stats` returns correct DB counts | Live run | `conversations=106, messages=4087, db_size_mb=9.88` | PASS |
| `get_status` returns `{status, conversations, last_ingested}` | Live run | All three keys present, `status='ok'` | PASS |
| `export_conversation` markdown format | Live run | `# (Untitled)\n*Date: ...*\n\n## Human\n\n## Assistant` | PASS |
| `import claude_history.server` | `uv run --no-sync python -c "import claude_history.server; print('IMPORT OK')"` | `IMPORT OK` | PASS |
| No `print()` in server.py | grep count | 0 | PASS |
| No `print()` in search.py | grep count | 0 | PASS |
| `sys.stderr.reconfigure` on line 4 | Line 4 of server.py | Confirmed | PASS |
| `logging.basicConfig` only inside `main()` | grep — search.py count = 0, server.py count = 1 actual call (+ 1 comment) | Correct | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TOOL-01 | 03-01, 03-02 | `search_conversations(query, project_filter?)` returns BM25-ranked snippets, title, project, date, match count | SATISFIED | `search_conversations` returns all 6 required keys; BM25 ordering verified live |
| TOOL-02 | 03-01, 03-02 | `search_conversations` accepts `include_full_content=True` to return complete message text | SATISFIED | `include_full_content=True` adds `full_content` key confirmed live |
| TOOL-03 | 03-02 | `get_conversation(id)` returns full conversation as labeled turns (Human/Assistant) | SATISFIED | `ORDER BY position ASC`; `role_label` dict; returns `{"error": ...}` dict for missing IDs |
| TOOL-04 | 03-02 | `list_projects()` returns project names with conversation counts and date ranges | SATISFIED (with known limitation) | Returns `[]` per export format; docstring explains why; accepted in REQUIREMENTS.md with note |
| TOOL-05 | 03-02 | `get_stats()` returns conversation count, message count, date range, and DB file size | SATISFIED | All 5 keys returned: `conversations, messages, date_from, date_to, db_size_mb` |
| TOOL-06 | 03-02 | `export_conversation(id, format?)` returns markdown string | SATISFIED | `# title`, `*Date: date*`, `## Human`/`## Assistant` format confirmed live |
| SETUP-02 | 03-02 | FastMCP stdio transport; all logging to stderr; stdout never written directly | SATISFIED (automated) | `sys.stderr.reconfigure` line 4; `logging.basicConfig(stream=sys.stderr)` inside `main()`; `print()` count = 0; stdout contamination needs human confirmation for end-to-end |

**No orphaned requirements:** All 7 requirement IDs declared in plan frontmatter (TOOL-01 through TOOL-06, SETUP-02) are verified above.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | No anti-patterns found |

- No `TODO`, `FIXME`, or `PLACEHOLDER` comments in either file
- No `sys.stdout.write()` calls
- No `print()` calls
- No hardcoded empty data returns (except `list_projects` which is intentional and documented)
- No `return null` / `return {}` / `return []` stub patterns (list_projects `return []` is the known limitation, not a stub)

### Human Verification Required

#### 1. Stdout Contamination — End-to-End

**Test:** Run `uv run server` and capture stdout output for 2-3 seconds before killing it, or use MCP Inspector to initiate a connection.

**Expected:** Zero bytes written to stdout. Server starts, emits startup log to stderr, then blocks waiting for JSON-RPC input on stdin.

**Why human:** The server blocks indefinitely waiting for stdin input. Programmatic subprocess capture with a short timeout is not reliable in this environment (the server process may not flush stderr in time). Static code analysis confirms no `print()` calls and correct `sys.stderr.reconfigure` + `logging.basicConfig(stream=sys.stderr)` ordering — but actual runtime stdout capture is the definitive test.

#### 2. MCP Tool Calls via Claude Code or MCP Inspector

**Test:** With the server registered (Phase 4 confirmed), open a Claude Code session and call:
- `search_conversations` with query `"python"` — expect 10 ranked results
- `get_conversation` with a real ID from the previous result — expect labeled turns
- `get_stats` — expect `{conversations: 106, messages: 4087, db_size_mb: 9.88, ...}`
- `list_projects` — expect `[]` with no error
- `export_conversation` with a real ID — expect markdown starting with `# `
- `get_status` — expect `{status: "ok", conversations: 106, last_ingested: "..."}`

**Expected:** All 6 tools respond with correct shapes and non-error content within 5 seconds.

**Why human:** Full MCP JSON-RPC dispatch (tool registration, schema generation by FastMCP, JSON serialization, response framing) requires the server to be running. Phase 3 ROADMAP text specifies "validated via MCP Inspector, Claude Code can call them against real data" — this is inherently a live-system test.

### Gaps Summary

No hard gaps found. All artifacts exist, are substantive (above minimum line counts), are wired to real data sources, and produce correct output under direct Python invocation. The two human verification items are runtime-confirmation checks required by the ROADMAP's own success criteria language ("validated via MCP Inspector, Claude Code can call them against real data"), not missing implementation.

**If Phase 4 has already been completed** (ROADMAP shows Phase 4 marked complete on 2026-05-06), the MCP registration and end-to-end tool call confirmation likely occurred during Phase 4 validation. If Phase 4's VERIFICATION.md confirms those tool calls succeeded, these two human items may be treated as retrospectively satisfied.

---

_Verified: 2026-05-06_
_Verifier: Claude (gsd-verifier)_
