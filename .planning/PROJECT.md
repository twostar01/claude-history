# Claude History MCP Server

## What This Is

A local MCP server that makes Claude.ai conversation history queryable from any Claude Code session. Export your full history from Claude.ai (JSON/ZIP), run an ingest script that loads it into a local SQLite database with FTS5 full-text search, then query it via MCP tools. Any Claude Code session can pull relevant context without loading the full history into the prompt.

**Shipped:** v1.0 (2026-05-06) — 106 conversations, 4087 messages indexed; all 6 tools live.

## Core Value

Any Claude Code session can search past conversations and retrieve relevant context with a single tool call.

## Requirements

### Validated

- ✓ Schema discovery CLI inspects Claude.ai export ZIP and produces a field reference document — v1.0 (Phase 1)
- ✓ uv package with stdio FastMCP server, stderr-only logging, zero stdout contamination — v1.0 (Phase 1)
- ✓ SQLite FTS5 with unicode61 `tokenchars '-_'` handles snake_case terms as single tokens — v1.0 (Phase 2)
- ✓ Ingest script parses Claude.ai export ZIP into SQLite: 106 conversations, 4087 messages — v1.0 (Phase 2)
- ✓ Idempotent re-run: INSERT OR IGNORE, UUID pre-check, 0 duplicates — v1.0 (Phase 2)
- ✓ Text attachment content indexed; binary files skipped — v1.0 (Phase 2)
- ✓ 6 MCP tools live: search_conversations (BM25), get_conversation, list_projects, get_stats, export_conversation, get_status — v1.0 (Phase 3)
- ✓ User-scope registration via `uv --directory` — works from any Claude Code session — v1.0 (Phase 4)
- ✓ README covers install, ingest, registration, all 6 tool signatures — v1.0 (Phase 4)

### Active (v2)

- [ ] `search_conversations` supports `date_from` / `date_to` filter parameters (SRCH-01)
- [ ] `search_conversations` supports `role_filter` parameter (SRCH-02)
- [ ] `export_conversation` can optionally write markdown to a file path (EXP-01)
- [ ] Ingest script indexes PDF attachment content (ATTACH-01)

### Out of Scope

- Automated Claude.ai export download — export requires manual action in claude.ai settings; no API available
- Scheduled/automatic re-ingestion — manual ingest after each export is deliberate (simpler, no background process)
- Remote access or multi-machine sync — local-only personal tool; no network exposure needed
- Vector/semantic search — FTS5 + BM25 is fast enough and zero-infrastructure for personal history scale
- Web UI — Claude Code is the interface
- Write operations via MCP — read-only server

## Context

**Current state:** v1.0 shipped. Server registered in user scope (`~/.claude.json`). 106 conversations (4087 messages, 9.88 MB DB) indexed from real Claude.ai export.

**Platform:** Windows 11, Python 3.11+ (Python 3.14.4 in use), uv 0.11.8, mcp[cli] 1.27.0, SQLite FTS5 (stdlib)

**Source:** 910 LOC Python across 7 modules (config, models, db, search, ingest, server, schema_discovery)

**Known quirk:** `uv run ingest` fails on Windows when the MCP server process has server.exe locked. Workaround: `.venv/Scripts/python.exe -m claude_history.ingest <zip-path>`

**Target repo:** github.com/twostar01/claude-history

## Constraints

- **Tech stack**: Python 3.11+, uv, FastMCP (`mcp[cli]`), SQLite FTS5 (stdlib) — no deviations
- **Platform**: Windows 11; stdio transport means no Task Scheduler or persistent daemon needed
- **Security**: stdio transport inherits Claude Code's process isolation; no network binding required
- **Search UX**: search_conversations returns snippets + metadata by default; full content available via include_full_content=true or get_conversation(id)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite + FTS5 over vector search | Zero infra, ships in Python stdlib, fast enough for personal history | ✓ Correct — 106 conversations at <10ms query |
| Manual ingest only | Claude.ai export requires manual trigger — no API to automate | ✓ Correct constraint |
| Snippets-first search results | Avoids flooding LLM context window; full content available on demand | ✓ Works well |
| Localhost-only, no auth | Personal tool, single machine — auth adds friction with no benefit | ✓ Correct |
| FastMCP via `mcp[cli]` + uv | Official SDK + recommended package manager; auto-generates tool schemas from type hints | ✓ Smooth — no schema boilerplate |
| stdio transport (not HTTP) | Claude Code spawns the server per-session; no persistent process needed; simpler than HTTP daemon | ✓ Confirmed — no daemon management |
| No Task Scheduler | stdio transport makes Task Scheduler irrelevant | ✓ Corrected pre-development assumption |
| FTS5 tokenizer locked at `unicode61 remove_diacritics 2 tokenchars '-_'` | Cannot change after data insertion without full rebuild | ✓ Snake_case search works as expected |
| INSERT OR IGNORE (not OR REPLACE) | Append-only history — re-run must never overwrite existing messages | ✓ Idempotent ingest confirmed |
| Python dict aggregation for BM25 dedup | bm25() is invalid outside direct FTS virtual table queries — cannot GROUP BY | ✓ Required by SQLite FTS5 constraint |
| User-scope registration via `uv --directory <abs-path>` | Works from any Claude Code session directory (not just project dir) | ✓ Fresh session confirmed working |
| project=NULL for all conversations | Claude.ai export has no project-conversation association field | ✓ Documented in list_projects docstring |

---
*Last updated: 2026-05-06 after v1.0 milestone*
