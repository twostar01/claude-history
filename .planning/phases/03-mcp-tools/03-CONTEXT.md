# Phase 3: MCP Tools - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement all 6 MCP tool handlers that turn the indexed SQLite DB into a queryable MCP server. This phase creates two new modules (`search.py`, `models.py`) and replaces the Phase 1 stub in `server.py` with the full tool suite. The server must be validated against real indexed data via MCP Inspector.

Tools to implement:
- `search_conversations(query, project_filter?, include_full_content?)` — FTS5-ranked results with snippets
- `get_conversation(id)` — full conversation as labeled Human/Assistant turns
- `list_projects()` — stub returning empty list (export format limitation — see D-11)
- `get_stats()` — DB counts, date range, file size
- `export_conversation(id)` — conversation as clean markdown string
- `get_status()` — promote from stub to real stats (or keep as health check — Claude's discretion)

</domain>

<decisions>
## Implementation Decisions

### Search Result Shape (search_conversations)
- **D-01:** Default result limit is **10** conversations.
- **D-02:** **One result per conversation** — the highest-BM25 matching message supplies the snippet. `match_count` reports how many messages in the conversation matched. Do not return multiple snippet rows per conversation.
- **D-03:** Default snippet length is **~300 characters**, trimmed by FTS5's `highlight()` or `snippet()` function to a window around the match term.
- **D-04:** When `include_full_content=True`, return **all messages concatenated** for each matched conversation (same content as `get_conversation(id)` embedded in the result). Not just the best-matching message.

### FTS5 Query Handling
- **D-05:** Use a **best-effort fallback** strategy: attempt the query as raw FTS5 input first; if `sqlite3.OperationalError` is raised (malformed FTS5 syntax), re-run with the input sanitized as a plain phrase (e.g., wrapped in quotes or special chars stripped). This gives power users FTS5 operators (`AND`, `OR`, `NEAR()`, prefix wildcards like `claude*`) while remaining safe for arbitrary natural-language input.
- **D-06:** When a search query matches nothing, return an **empty list `[]`**. Do not raise an error or return a structured message object. (Requirement TOOL-06: graceful empty responses.)

### list_projects — Export Format Limitation
- **D-11:** `list_projects()` returns an **empty list `[]`** and the tool docstring explicitly documents why: the Claude.ai export format (`conversations.json`) contains no project association field. The 7 project files in the export (`projects/*.json`) hold metadata only — no conversation UUIDs. This is a Claude.ai export format gap, not a processing bug. The tool is implemented correctly for the data available.

### get_conversation Message Ordering
- **D-07:** Messages are returned sorted by **`position` integer** (ascending). The `position` field was set during ingest as the enumeration index within `chat_messages`. `parent_message_uuid` is not stored in the DB and thread reconstruction is out of scope.

### export_conversation Markdown Format
- **D-08:** Each message turn is introduced with an **`## Human`** or **`## Assistant`** H2 header.
- **D-09:** The export begins with a **compact metadata header**: `# {title}` and `*Date: {created_at}*`. No full metadata block (no message count, no conversation UUID, no project).
- **D-10:** **No per-message timestamps** in the export. The conversation date in the header is sufficient.

### Claude's Discretion
- `get_status()` — may remain a simple `{"status": "ok"}` health check or be promoted to return DB stats (conversation count, last ingested date). Either works; promote if trivial.
- Python return types for FastMCP tools — use `list[dict]` for list-returning tools and `dict` for single-object tools. FastMCP auto-generates JSON schemas from type hints; `TypedDict` or `dataclasses` are acceptable if it improves schema clarity, but plain dicts are fine.
- FTS5 sanitization implementation — the exact escaping approach (quote-wrapping vs. stripping FTS5 reserved chars) is left to the implementer. The requirement is: no unhandled `OperationalError` reaches the tool caller.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Requirements and Architecture
- `.planning/REQUIREMENTS.md` — Phase 3 requirements: TOOL-01 through TOOL-06, SETUP-02
- `.planning/ROADMAP.md` — Phase 3 goal, success criteria, plan breakdown (03-01, 03-02)
- `.planning/PROJECT.md` — Core value, constraints (stdout rule, FTS5 tokenizer locked, FastMCP+stdio stack)
- `CLAUDE.md` — Module layout, stderr-only logging rule (CRITICAL: stdout contamination silently kills stdio sessions)

### Schema and Data Format
- `.planning/SCHEMA.md` — Confirmed export field names, timestamp formats, and the project association gap (conversations.json has no project field — this is a raw data limitation, not a bug)

### Existing Implementation
- `src/claude_history/db.py` — FTS5 schema, trigger definitions, `init_db()` signature; search.py MUST use the existing `messages_fts` virtual table and `messages` content table
- `src/claude_history/ingest.py` — `build_message_content()` documents how content is assembled (text + attachment extracted_content); confirms `position` is the linear enumeration index
- `src/claude_history/config.py` — `DB_PATH` constant; server.py and search.py import from here

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.py:init_db(db_path)` — opens connection, creates schema, returns `sqlite3.Connection`. search.py and server.py call this; pass `DB_PATH` from config.py.
- `config.py:DB_PATH` — resolves to `<project_root>/history.db` regardless of working directory. Import in server.py and search.py.
- `server.py:main()` — logging setup pattern is established and must not change: `sys.stderr.reconfigure` → `logging.basicConfig(stream=sys.stderr)` → `FastMCP()` → tools → `mcp.run(transport="stdio")`.

### Established Patterns
- **Stdout contamination rule:** Any `print()` or `sys.stdout.write()` in server.py or any module it imports silently corrupts the stdio MCP session. All output must go to `sys.stderr` via `logging`. This is the #1 invariant.
- **INSERT OR IGNORE pattern (from ingest.py):** History records are immutable — no updates. Search results should treat the DB as read-only.
- **FTS5 content table pattern:** `messages_fts` is a content table (`content="messages"`), not a standalone table. Queries must join `messages_fts` back to `messages` (and optionally `conversations`) to retrieve metadata fields like `role`, `conversation_id`, `position`.

### Integration Points
- `search.py` is a new module imported by `server.py` — must not write to stdout.
- `models.py` is a new module for dataclasses/TypedDicts used by both `search.py` and `server.py`.
- Phase 2 validated: 106 conversations, 4087 messages indexed, FTS5 functional. Phase 3 can assume a populated DB.
- Phase 4 will promote MCP registration from project scope (`.mcp.json`) to user scope (`claude mcp add --scope user`).

</code_context>

<specifics>
## Specific Ideas

- The `list_projects()` limitation should be clearly documented in the tool's docstring so that when a Claude Code session calls it and gets `[]`, the explanation is visible in the tool schema. This prevents confusion.
- The `export_conversation` format (H2 headers, compact title+date metadata) mirrors how humans structure conversation summaries in markdown — easy to paste into notes or PRDs.

</specifics>

<deferred>
## Deferred Ideas

- **Design chat ingestion** — `design_chats/*.json` files weren't ingested in Phase 2 and are not part of Phase 3. Each design chat has a `project` field, so ingesting them would partially address the project association gap. Candidate for a future phase or v2 work.
- **Manual project tagging** — A mechanism for the user to tag conversations with project names post-hoc. Would solve the project association gap for regular conversations. Out of scope for v1.
- **Project file ingestion for metadata only** — Parse `projects/*.json` to populate a `projects` table so `list_projects()` returns project names (even with `count=0`). Lower priority since count=0 results have limited utility until project associations exist.

</deferred>

---

*Phase: 3-MCP Tools*
*Context gathered: 2026-05-05*
