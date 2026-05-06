# Milestones

## v1.0 — Claude History MCP Server MVP

**Shipped:** 2026-05-06
**Phases:** 1–4 | **Plans:** 8 | **Tasks:** ~16
**Timeline:** 2026-05-03 → 2026-05-06 (3 days)
**Commits:** 79 | **Files changed:** 60 | **Source:** 910 LOC Python

### Delivered

A local MCP server that indexes Claude.ai conversation history into SQLite FTS5 and exposes 6 query tools to any Claude Code session — installable in under 5 minutes from the README.

### Key Accomplishments

1. **uv package scaffold** — pyproject.toml with 3 entry points (server, ingest, schema-discovery), mcp[cli] 1.27.0, stderr-only logging invariant established from day 0
2. **FastMCP stdio server** — registered in Claude Code project scope in Phase 1; zero stdout contamination AST-verified
3. **Schema discovery CLI** — `schema_discovery.py` reverse-engineered the Claude.ai export format against real data; produced SCHEMA.md that drove Phase 2 field extraction
4. **SQLite FTS5 + WAL schema** — unicode61 tokenizer with `tokenchars '-_'` handles snake_case search; content-table pattern with sync triggers; no duplicate storage
5. **Ingest pipeline** — 106 conversations, 4087 messages; idempotent re-run (0 new, 106 skipped); text attachment indexing (41 conversations)
6. **6 MCP tools** — search_conversations (BM25 ranked), get_conversation, list_projects, get_stats, export_conversation, get_status — all verified live against real data
7. **User-scope registration** — `uv --directory <abs-path> run server` in ~/.claude.json; works from any Claude Code session directory
8. **README** — complete install, ingest, registration, and tool reference; a developer with no prior context can get a working server from scratch

### Archive

- [v1.0 Roadmap Archive](milestones/v1.0-ROADMAP.md)
- [v1.0 Requirements Archive](milestones/v1.0-REQUIREMENTS.md)

---
