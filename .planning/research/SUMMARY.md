# Research Summary: Claude History MCP Server

**Synthesized:** 2026-05-03
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Recommended Stack

| Component | Choice | Version | Notes |
|-----------|--------|---------|-------|
| MCP framework | mcp[cli] Python SDK (FastMCP) | >=1.2.0 (~1.8.x current) | Official Tier 1 SDK; auto-generates tool schemas from type hints and docstrings |
| Python runtime | Python 3.11+ | 3.11 minimum | CPython Windows installer ships with FTS5-enabled SQLite |
| Package manager | uv | latest | Official MCP docs use uv; manages venvs + pyproject.toml; Claude Code invokes via uv run |
| Database | SQLite via stdlib sqlite3 | bundled | Zero dependencies; WAL mode for concurrent ingest+serve |
| Full-text search | SQLite FTS5 | built into SQLite 3.9+ | BM25 ranking, snippet(), highlight() all built in |
| ZIP/JSON parsing | stdlib zipfile + json | bundled | No third-party deps needed for export loading |
| Transport | stdio (FastMCP) | - | Claude Code spawns the server on demand; no persistent process required |
| Logging | stdlib logging to stderr | - | stdout is the JSON-RPC wire; must never be touched |

**Installation:**

``powershell
uv init claude-history-mcp
uv add "mcp[cli]>=1.2.0"
``

**Registration with Claude Code:**

claude mcp add --transport stdio --scope user claude-history -- uv --directory "C:\Users\nclem\Claude Code\claude-history" run server.py

---

## Table Stakes Features

Must-haves for v1. Missing any of these = product feels broken.

| Feature | Tool | Notes |
|---------|------|-------|
| Full-text search across all conversations | search_conversations(query, ...) | FTS5 MATCH with BM25 ranking |
| Snippet/excerpt in results | search_conversations return shape | 32-40 tokens via snippet(); use <<<>>> highlight markers |
| Result count metadata | search_conversations return shape | Return total_matches, returned_count, has_more so LLM knows when to narrow |
| Per-result conversation ID | search_conversations return shape | Required for the get_conversation follow-up call |
| Conversation title and date in results | search_conversations return shape | Primary human-readable identifiers |
| Project filter on search | search_conversations(project=...) | Optional string; NULL = search all projects |
| List available projects | list_projects() | Returns [{name, conversation_count}] |
| Full conversation retrieval | get_conversation(id) | All messages in order with role labels |
| Stats overview | get_stats() | Total counts, date range, project summary; fast LLM orientation |
| Graceful empty results | All tools | Return empty list + message, never error on zero matches |
| Read-only enforcement | server.py | SQLite opened read-only (uri=true and mode=ro) |

**Recommended tool set (4 tools total):**
1. search_conversations(query, project?, role?, after?, before?, limit?, include_full_content?)
2. list_projects()
3. get_conversation(id)
4. get_stats()

**Deliberate non-features (defer to v2+):**
- Fuzzy/typo-tolerant search (use FTS5 prefix term* instead)
- Vector/semantic search (BM25 is sufficient for personal history)
- Write operations (Claude.ai is the source of truth)
- Automated export fetching (no Claude.ai API; manual only)
- Pagination cursors (use limit + offset instead)
---

## Architecture Overview

The server has two completely separate processes sharing a single SQLite file. ingest.py is a standalone CLI script the user runs manually after downloading a Claude.ai export ZIP; it unzips the archive, parses JSON, normalizes messages, and upserts into history.db (SQLite, WAL mode). server.py is an MCP stdio server that Claude Code spawns on demand; it opens history.db read-only and exposes four tools that execute FTS5 queries against a virtual table backed by a denormalized full_text column built at ingest time. The FTS5 index is kept in sync with the content table via BEFORE DELETE / AFTER INSERT triggers. Claude Code sends JSON-RPC 2.0 messages over the process stdin/stdout; the server returns tool results as structured JSON strings, never touching stdout for any other purpose.

**Component map:**

```
Claude.ai (browser)
    | manual export -> ZIP download
    v
[ingest.py]  (CLI, run manually per export cycle)
    | parse -> normalize -> upsert (WAL write)
    v
[history.db]  (SQLite, FTS5, WAL mode)
    | read-only SQL queries (FTS MATCH + JOIN)
    v
[server.py]  (MCP stdio server, spawned by Claude Code)
    | JSON-RPC 2.0 over stdin/stdout
    v
[Claude Code CLI]  (MCP client)
    | tool call results in LLM context
    v
Claude model
```

**Recommended module layout:**

```
claude-history/
|-- server.py      # FastMCP entry point; thin tool handlers
|-- ingest.py      # CLI: unzip -> parse -> upsert
|-- db.py          # Schema init, upsert, read queries
|-- search.py      # FTS5 query building and result shaping
|-- models.py      # Dataclasses: Conversation, Turn, SearchResult
|-- config.py      # DB_PATH and constants (single source of truth)
|-- history.db     # (gitignored)
```

---

## Critical Decisions

Decisions that must be made correctly from day 1. Getting these wrong requires schema drops and rebuilds.

### 1. Transport: stdio, not HTTP

PROJECT.md mentions Task Scheduler auto-starting the server on boot. This assumption is wrong. Claude Code uses stdio transport: it spawns the server process fresh for each session and manages the lifecycle automatically. No Task Scheduler entry is needed. Use mcp.run(transport=stdio).

**Action required:** Correct PROJECT.md to remove the Task Scheduler requirement for the MCP server. Task Scheduler is only relevant if the project later switches to HTTP transport.

### 2. Export schema: unknown until examined

The Claude.ai export format has no official public documentation. The ingest script cannot be written until a real export file is examined. Phase 1 must be schema discovery. All inferred schemas in the research files are guesses (uuid vs id, sender vs role, text vs content[].text) and must be verified.

**Unblocked by:** User providing an actual export ZIP.

### 3. stdout must be clean before anything else

For stdio MCP servers, stdout is the JSON-RPC wire. Any stray byte on stdout silently corrupts the protocol and breaks all tool calls. The first lines of server.py must configure logging to stderr and reconfigure stderr encoding to UTF-8 for Windows cp1252 safety. Never use bare print(). Wrap mcp.run() in a try/except that logs exceptions to stderr.

### 4. FTS5 tokenizer must be configured before first ingest

The FTS5 virtual table schema cannot be altered after creation. If the tokenizer is wrong, the table must be dropped and rebuilt, destroying the index.

The correct tokenizer: unicode61 remove_diacritics 2 tokenchars '-_'

- remove_diacritics 2: fixes a documented SQLite bug with multi-diacritic codepoints (default value 1 is incorrect per official SQLite docs)
- tokenchars '-_': keeps hyphens and underscores as word chars so search_conversations matches as one token, not two

This must be set in db.py before any data is ingested.

### 5. Use INSERT OR REPLACE with BEFORE DELETE triggers for deduplication

Re-ingesting from a new export must be idempotent. INSERT OR REPLACE handles the content table, but FTS5 has no native update operation -- stale FTS entries must be explicitly deleted before new ones are inserted. Use BEFORE DELETE triggers (remove FTS rows) and AFTER INSERT triggers (add FTS rows). INSERT OR REPLACE internally does DELETE + INSERT, so both triggers fire in the right order automatically.

---

## Watch Out For

Top 5 pitfalls in priority order.

### 1. stdout contamination (Critical -- kills the server silently)

Any write to stdout corrupts the JSON-RPC stream. The MCP client receives malformed JSON and either drops the connection or silently fails every tool call. This is the most common cause of MCP server failures with zero error messages.

**Prevention:** Configure logging to stderr as the very first thing in server.py. Never use bare print(). Wrap mcp.run() in a try/except that logs to stderr.

### 2. Export schema is unknown (Critical -- blocks ingest phase)

The ingest script is a stub until the actual export is examined. Field names for conversation ID, project, role, message text, and timestamps are all unverified. Writing a parser against assumed names produces a broken ingest that silently stores empty or null data.

**Prevention:** Do schema discovery first. Write a 10-line diagnostic script that loads the export JSON and prints type(data), data[0].keys(), and the keys of the first message object. Document the real field names before writing the parser.

### 3. FTS5 schema mistakes are permanent (Critical -- requires full rebuild)

The FTS5 virtual table cannot be ALTERed. Wrong tokenizer options, wrong column list, or wrong content= reference require dropping the virtual table and rebuilding the index from scratch.

**Prevention:** Finalize the FTS5 CREATE VIRTUAL TABLE statement in db.py and test it against a sample dataset before ingesting full history.

### 4. Relative paths cause working-directory failures (Significant)

Claude Code spawns the MCP server subprocess with an undefined working directory. Relative paths in MCP config or os.getcwd()-based path construction silently point to the wrong location.

**Prevention:** Resolve the database path relative to Path(__file__).parent, not os.getcwd(). Use absolute paths in claude mcp add arguments. On Windows, paths with spaces must be quoted.

### 5. Unicode61 tokenizer defaults break technical content (Significant -- silent wrong results)

The default unicode61 tokenizer treats hyphens and underscores as word separators. search_conversations tokenizes as search + conversations. Searches for snake_case function names, hyphenated terms, and code identifiers silently return zero results.

**Prevention:** Set tokenchars '-_' in the tokenizer string. Must be done before first ingest.

---

## Open Questions

Blockers that require a real export file to resolve. Everything else can proceed.

| Question | Impact | Unblocked by |
|----------|--------|--------------|
| What are the actual top-level field names in conversations.json? | Cannot write ingest parser | Examining real export ZIP |
| Is message content a plain string or a typed array ([{type, text}])? | Determines extract_text() implementation | Examining real export |
| What is the field name for project association on a conversation? | Determines project filter implementation | Examining real export |
| Are conversations with no project null or a missing key? | Defensive parsing strategy | Examining real export |
| What timestamp format is used (ISO 8601 string, Unix int, ms int)? | Determines parse_timestamp() implementation | Examining real export |
| What is the ZIP file name and internal structure? | Determines unzip logic | Examining real export |
| Are tool_use / tool_result / thinking blocks present in the export? | Determines content extraction filtering | Examining real export |
| How large is the export file? | Determines whether streaming JSON (ijson) is needed | Examining real export |

**Recommended first action:** Before any code is written beyond project scaffolding, download a Claude.ai export and run a schema discovery script.

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| MCP SDK (FastMCP, stdio, claude mcp add) | HIGH | Official modelcontextprotocol.io and code.claude.com docs verified 2026-05-03 |
| SQLite FTS5 (schema, tokenizer, BM25, snippet) | HIGH | Official sqlite.org/fts5.html verified 2026-05-03 |
| Tool design patterns (4-tool set, return shapes) | HIGH | Official MCP spec + reference server patterns |
| Transport decision (stdio vs HTTP) | HIGH | Official MCP transport spec confirmed; PROJECT.md assumption corrected |
| Windows encoding/path pitfalls | HIGH | Official MCP debugging docs |
| Claude.ai export schema | LOW | No official documentation; must reverse-engineer from real file |
| Export ZIP internal structure | LOW | Community inference only; treat as unknown |

**Overall confidence:** HIGH on everything except the export schema, which is an acknowledged known unknown. The schema gap blocks the ingest phase but does not block server scaffolding, FTS schema design, or tool stub implementation.
