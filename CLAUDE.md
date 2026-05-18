# CLAUDE.md — Claude History MCP Server

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Claude History MCP Server** — A local MCP server that makes Claude.ai conversation history queryable from any Claude Code session. Export history from Claude.ai, ingest into SQLite FTS5, query via MCP tools.

**Core value:** Any Claude Code session can search past conversations and retrieve relevant context with a single tool call.

**Stack:** Python 3.11+, uv, FastMCP (`mcp[cli]`), SQLite FTS5 (stdlib), stdio transport

**Transport:** stdio — Claude Code spawns the server on demand per session. No persistent daemon, no Task Scheduler.

See `.planning/PROJECT.md` for full context, decisions, and requirements.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

| Component | Choice | Notes |
|-----------|--------|-------|
| Runtime | Python 3.11+ | stdlib sqlite3 ships with FTS5 on Windows |
| Package manager | uv | Official MCP quickstart recommendation |
| MCP framework | FastMCP (`mcp[cli]`) | Auto-generates tool schemas from type hints |
| MCP transport | stdio | Claude Code manages process lifecycle |
| Database | SQLite FTS5 | Trigram tokenizer for fuzzy search; content table pattern |
| Entry points | `uv run server` / `uv run ingest` | Defined in pyproject.toml |

**Critical:** Never write to stdout in the server. All logging goes to `sys.stderr`. Stdout contamination silently kills stdio MCP sessions.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Two separate processes sharing one SQLite file:

- **`ingest.py`** — reads Claude.ai export ZIP, writes to `history.db` (WAL mode)
- **`server.py`** — FastMCP stdio server, reads `history.db`, exposes 6 tools

**Module structure:**
```
src/
  config.py       # DB_PATH and constants
  models.py       # dataclasses (SearchResult, Conversation, Stats)
  db.py           # schema creation, FTS5 setup, WAL mode
  search.py       # FTS5 query building, BM25 ranking, snippet shaping
  ingest.py       # ZIP parsing, upsert, incremental, attachments
  server.py       # FastMCP tool definitions (entry point)
  schema_discovery.py  # prints export ZIP structure (Phase 1 gate)
```

**FTS5 schema must lock in before first ingest** — tokenizer options (`unicode61 tokenchars '-_' remove_diacritics 2`) cannot change after data is inserted without a full rebuild.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to `.claude/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

## Release Process

**Live UAT is required before marking any milestone complete.** Do not skip it — automated tests and verifiers cannot catch stdio transport issues, FTS5 schema mismatches, or MCP tool registration problems.

### Steps

1. Export fresh history from Claude.ai (Settings → Data & Privacy → Export Data → JSON)
2. Run ingest: `uv run ingest <export.zip>` — confirm output shows expected conversation/message counts
3. Restart Claude Code to let it re-spawn the MCP server process
4. Open the milestone's UAT checklist (`.planning/<milestone>-UAT.md`) and run every test live in a Claude Code session
5. Every test must show `result: pass` before the milestone is tagged complete

### UAT Checklist Files

Per-milestone checklists: `.planning/<milestone>-UAT.md` (e.g., `.planning/v1.1-UAT.md`)

Each test entry has `expected:`, `result:` (pass/fail/skip), and optional `note:` fields.

### Why Live UAT Matters Here

- The MCP server runs over **stdio** — transport contamination (any `print()` to stdout) silently kills the session and only shows up at runtime
- FTS5 tokenizer options are locked at schema creation and can't be changed without a full DB rebuild — schema problems surface during ingest or first query
- MCP tool registration (`~/.claude.json`) can drift if paths change — registration failures only appear when Claude Code tries to spawn the server

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` — do not edit manually.
<!-- GSD:profile-end -->
