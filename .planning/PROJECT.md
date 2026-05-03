# Claude History MCP Server

## What This Is

A local MCP server that makes Claude.ai conversation history queryable from any Claude Code session. You export your full history from Claude.ai (JSON/ZIP), run an ingest script that loads it into a local SQLite database with FTS5 full-text search, then query it via MCP tools so any Claude Code session can pull relevant context without loading the full history into the prompt.

## Core Value

Any Claude Code session can search past conversations and retrieve relevant context with a single tool call.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Ingest script parses Claude.ai export format into SQLite with FTS5
- [ ] MCP server exposes search_conversations(query, project_filter?, include_full_content?) tool
- [ ] MCP server exposes list_projects() tool
- [ ] MCP server exposes get_conversation(id) tool returning full content
- [ ] Claude Code MCP config registers server (stdio transport, user scope) so it's available in every session
- [ ] MCP server exposes get_stats() tool returning conversation/message counts
- [ ] Ingest script is run manually after each Claude.ai export download

### Out of Scope

- Automated Claude.ai export download — export requires manual action in claude.ai settings
- Scheduled/automatic re-ingestion — manual script run after each export
- Remote access or multi-machine sync — local-only by design
- Write operations via MCP — read-only server
- Web UI for search — Claude Code is the interface

## Context

- **Export format**: Claude.ai provides a ZIP/JSON export from account settings. Exact schema TBD — user will provide the export file when ready to test the ingest script. First step is reverse-engineering the schema.
- **Platform**: Windows 11, Python 3.11+, Claude Code CLI, uv package manager
- **Target repo**: github.com/twostar01/claude-history
- **Runtime**: stdio transport — Claude Code spawns the server process on demand per session; no persistent daemon or Task Scheduler needed
- **Interface**: FastMCP from `mcp[cli]` package (official Anthropic MCP Python SDK)
- **Scale**: Potentially years of conversations — SQLite FTS5 handles this well up to millions of rows

## Constraints

- **Tech stack**: Python 3.11+, uv, FastMCP (`mcp[cli]`), SQLite FTS5 (stdlib) — no deviations
- **Platform**: Windows 11; stdio transport means no Task Scheduler or persistent daemon needed
- **Security**: stdio transport inherits Claude Code's process isolation; no network binding required
- **Search UX**: search_conversations returns snippets + metadata by default; full content available via include_full_content=true flag or get_conversation(id)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite + FTS5 over vector search | Zero infra, ships in Python stdlib, fast enough for personal history | — Pending |
| Manual ingest only | Claude.ai export requires manual trigger — no API to automate | ✓ Correct constraint |
| Snippets-first search results | Avoids flooding LLM context window; full content available on demand | — Pending |
| Localhost-only, no auth | Personal tool, single machine — auth adds friction with no benefit | — Pending |
| FastMCP via `mcp[cli]` + uv | Official SDK + recommended package manager per MCP quickstart; auto-generates tool schemas from type hints | — Pending |
| stdio transport (not HTTP) | Claude Code spawns the server per-session; no persistent process needed; simpler than HTTP daemon | ✓ Confirmed by research |
| No Task Scheduler | stdio transport makes Task Scheduler irrelevant — this was a pre-research assumption | ✓ Corrected by research |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-03 after research — corrected transport model (stdio, not HTTP daemon)*
