# Phase 3: MCP Tools - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-05
**Phase:** 3-MCP Tools
**Areas discussed:** Search result shape, FTS5 query handling, list_projects with NULL data, export_conversation format

---

## Search Result Shape

| Option | Description | Selected |
|--------|-------------|----------|
| 5 results | Very conservative, good for token cost | |
| 10 results | Good balance for Claude Code context window | ✓ |
| 20 results | More results, risks large responses | |

**User's choice:** 10 (default limit)
**Notes:** No additional context provided.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Best match only | One snippet per conversation, highest-BM25 message | ✓ |
| All matching messages | Multiple rows per conversation when several messages match | |

**User's choice:** Best match only, with match_count field
**Notes:** No additional context provided.

---

| Option | Description | Selected |
|--------|-------------|----------|
| ~150 chars | Very tight, saves tokens | |
| ~300 chars | Enough context to recognize the conversation | ✓ |
| ~500 chars | Generous window, good readability | |

**User's choice:** ~300 chars
**Notes:** No additional context provided.

---

| Option | Description | Selected |
|--------|-------------|----------|
| All messages concatenated | Full conversation text per match | ✓ |
| Top match's full message only | Single best-matching message in full | |

**User's choice:** All messages concatenated when include_full_content=True
**Notes:** No additional context provided.

---

## FTS5 Query Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Sanitize to plain text | Safe for any input, loses FTS5 operators | |
| Pass through as-is | Full FTS5 syntax, OperationalError risk | |
| Best-effort: try raw, fallback to sanitized | FTS5 power with safety net | ✓ |

**User's choice:** Best-effort with fallback
**Notes:** No additional context provided.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Empty list [] | Consistent with TOOL-06 empty-list behavior | ✓ |
| Structured empty with message | More informative but inconsistent return type | |

**User's choice:** Empty list []
**Notes:** No additional context provided.

---

## list_projects with NULL Data

*This area required an unplanned investigation mid-discussion. User noted that at least half their conversations are in projects in Claude.ai, which contradicted the stored data. Real-time inspection of the export ZIP confirmed:*
- *All 106 conversations in conversations.json have no `project` field*
- *projects/*.json files contain metadata only — no conversation UUIDs*
- *This is a Claude.ai export format limitation, not a processing bug*

| Option | Description | Selected |
|--------|-------------|----------|
| Return project names with count=0 | Ingest 7 project files, show names with zero counts | |
| Return empty list, document why | Honest and simple | |
| Skip list_projects for now | Implement as stub | ✓ |

**User's choice:** Skip (stub returning empty list with docstring explanation)
**Notes:** User was surprised that project associations were missing. Investigation revealed a raw data gap in Claude.ai's export format. Deferred project-related work noted for future phases.

---

## export_conversation Format

| Option | Description | Selected |
|--------|-------------|----------|
| ## Human / ## Assistant H2 headers | Readable in any renderer, clear visual separation | ✓ |
| **Human:** / **Assistant:** inline bold | More compact, text runs on without breaks | |
| --- divider + bold label | Most explicit separation, slightly more verbose | |

**User's choice:** H2 headers

---

| Option | Description | Selected |
|--------|-------------|----------|
| Title + date only | Compact, useful for identification | ✓ |
| Full metadata block | Complete but noisy (includes UUID) | |
| No metadata header | Cleaner, no identification info | |

**User's choice:** Title + date only

---

| Option | Description | Selected |
|--------|-------------|----------|
| No timestamps | Less clutter, date in header is enough | ✓ |
| Per-message timestamps | Useful for timeline, but noisier | |

**User's choice:** No per-message timestamps

---

## Claude's Discretion

- `get_status()` — may remain a simple health check or be promoted to return DB stats
- Python return types for FastMCP tools — plain `list[dict]` / `dict` is acceptable
- FTS5 sanitization — exact escaping strategy left to implementer; requirement is no unhandled OperationalError

## Deferred Ideas

- Design chat ingestion — `design_chats/*.json` were not ingested; have project fields that would partially address project association gap
- Manual project tagging — post-hoc project assignment for conversations
- Project file ingestion for metadata only — populate a `projects` table so list_projects() returns names even with count=0
