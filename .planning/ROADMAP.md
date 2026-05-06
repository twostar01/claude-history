# Roadmap: Claude History MCP Server

## Overview

Four phases that move from nothing to a fully registered, searchable MCP server. Phase 1 is gated on a real export file — schema discovery is the first task and unblocks everything else. Phases 2 and 3 are the heavy lift (database + ingest, then tools). Phase 4 closes the loop with end-to-end validation and the README.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Scaffolding + Schema Discovery** - uv project, stdio server stub, stderr logging, MCP registration working with stub tools, schema_discovery.py prints real export structure *(completed 2026-05-04)*
- [x] **Phase 2: Database + Ingest** - FTS5 schema locked, ingest.py parses real export, dedup + incremental, text attachment indexing, WAL mode *(completed 2026-05-05)*
- [x] **Phase 3: MCP Tools** - All 6 tools implemented, validated via MCP Inspector, Claude Code can call them against real data *(completed 2026-05-05)*
- [x] **Phase 4: Integration + README** - End-to-end test with full history, claude mcp add registration confirmed, README complete *(completed 2026-05-06)*

## Phase Details

### Phase 1: Scaffolding + Schema Discovery
**Goal**: A working project skeleton where Claude Code can call a stub MCP tool without stdout contamination, AND the real export schema is documented so Phase 2 can start without guessing field names
**Depends on**: Nothing (first phase) — but export ZIP must be on disk before schema_discovery.py can be run
**Requirements**: SETUP-01, SETUP-02, SETUP-04, INGEST-01
**Success Criteria** (what must be TRUE):
  1. `uv run server.py` starts without error and responds to MCP ping over stdio
  2. Calling a stub tool from Claude Code returns a result and nothing appears on stdout (no contamination)
  3. `uv run schema_discovery.py <export.zip>` prints the top-level keys, message structure, and timestamp format of the real export without modifying any database
  4. The SQLite DB file and export ZIPs are absent from `git status` (gitignored correctly)
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — uv install, pyproject.toml with build system + entry points, .gitignore, config.py with DB_PATH
- [x] 01-02-PLAN.md — server.py with stderr-only logging + get_status tool, claude mcp add --scope project, human smoke test
- [x] 01-03-PLAN.md — schema_discovery.py inspects real export ZIP, writes .planning/SCHEMA.md with project-association gap warning

### Phase 2: Database + Ingest
**Goal**: A populated SQLite database with a correctly configured FTS5 index that Claude Code can query, built from a real Claude.ai export
**Depends on**: Phase 1 (schema discovered, project structure in place)
**Requirements**: DB-01, DB-02, DB-03, DB-04, INGEST-02, INGEST-03, INGEST-04, INGEST-05
**Success Criteria** (what must be TRUE):
  1. Running `uv run ingest <export.zip>` on a fresh database populates conversations and messages tables with no errors
  2. Re-running ingest on the same ZIP produces identical row counts (no duplicates — idempotent)
  3. Re-running ingest on an updated ZIP only processes new conversations (incremental behavior confirmed by log output)
  4. An FTS5 search query in `sqlite3 history.db` returns ranked results with snippets, and snake_case terms like `search_conversations` match as a single token
  5. Text attachment content (e.g., a `.py` or `.md` file) is present in the FTS index; a binary file attachment is skipped without error
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — db.py: init_db() with conversations + messages tables, FTS5 virtual table (unicode61 tokenchars '-_' remove_diacritics 2), WAL mode, AFTER INSERT / AFTER DELETE / AFTER UPDATE triggers *(completed 2026-05-04)*
- [x] 02-02-PLAN.md — ingest.py: ZIP parsing, field extraction (SCHEMA.md field names), INSERT OR IGNORE upsert, incremental skip, attachment extracted_content indexing; uncomment pyproject.toml ingest entry point *(completed 2026-05-05)*

### Phase 3: MCP Tools
**Goal**: All six MCP tools return correct, well-shaped results and Claude Code can use them against real indexed data
**Depends on**: Phase 2 (database populated with real data)
**Requirements**: TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, TOOL-06, SETUP-02
**Success Criteria** (what must be TRUE):
  1. `search_conversations("some query")` returns BM25-ranked results with snippet, title, project, date, and conversation ID
  2. `search_conversations("query", include_full_content=True)` returns full message text instead of snippets
  3. `get_conversation(id)` returns all turns formatted as labeled Human/Assistant blocks in correct order
  4. `list_projects()` returns project names with conversation counts and date ranges; `get_stats()` returns total counts, date range, and DB file size
  5. `export_conversation(id)` returns a clean markdown string with no raw JSON or formatting artifacts
  6. All tools return graceful empty-list responses (not errors) when given queries or IDs that match nothing
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — search.py: FTS5 query building, two-step Python BM25 aggregation (one result per conversation), snippet shaping (token_count=64), FTS5 sanitization fallback (D-05), include_full_content mode *(completed 2026-05-05)*
- [x] 03-02-PLAN.md — server.py: implement all 6 tool handlers (search_conversations, get_conversation, list_projects, get_stats, export_conversation, get_status); human smoke test validates no stdout contamination and correct tool shapes *(implemented 2026-05-05; checkpoint pending)*

### Phase 4: Integration + README
**Goal**: The server is registered with Claude Code for every session and a developer can install and use it from scratch using only the README
**Depends on**: Phase 3 (all tools working)
**Requirements**: SETUP-03, SETUP-05
**Success Criteria** (what must be TRUE):
  1. `claude mcp list` shows claude-history in user scope without any manual path adjustment
  2. A fresh Claude Code session can call `search_conversations` and `get_conversation` against the full indexed history with correct results
  3. Following only the README steps (uv init → ingest → claude mcp add → test call) produces a working server with no prior knowledge of the codebase
**Plans**: TBD

Plans:
- [x] 04-01-PLAN: User-scope MCP registration (`uv --directory` flag) + README with installation, ingest workflow, registration command, all 6 tool signatures *(completed 2026-05-06)*

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scaffolding + Schema Discovery | 3/3 | Complete | 2026-05-04 |
| 2. Database + Ingest | 2/2 | Complete | 2026-05-05 |
| 3. MCP Tools | 2/2 | Complete | 2026-05-05 |
| 4. Integration + README | 1/1 | Complete | 2026-05-06 |
