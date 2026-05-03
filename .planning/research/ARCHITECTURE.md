# Architecture Research: Claude History MCP Server

**Domain:** Local Python MCP server with SQLite FTS5 full-text search
**Researched:** 2026-05-03
**Confidence note:** WebSearch, WebFetch, and Bash tool calls were all denied in this session. All findings are from training data (cutoff August 2025). Confidence levels reflect that limitation. Validate against current MCP Python SDK docs and Claude Code docs before implementation.

---

## Component Map

```
Claude.ai (browser)
    |
    | manual export → ZIP/JSON file
    v
[ingest.py]  (standalone script, run manually)
    |
    | parse → normalize → upsert
    v
[history.db]  (SQLite file, FTS5 enabled)
    |
    | SQL queries (fts MATCH, rowid JOIN)
    v
[server.py]  (persistent MCP server process)
    |
    | stdio (JSON-RPC 2.0 over stdin/stdout)
    v
[Claude Code CLI]  (mcp client, per-session)
    |
    | tool calls: search_conversations, list_projects, get_conversation
    v
Claude model (in-context results)
```

**What talks to what:**

| From | To | Protocol | Notes |
|------|----|----------|-------|
| ingest.py | history.db | sqlite3 (stdlib) | Direct file access, no network |
| server.py | history.db | sqlite3 (stdlib) | Read-only after ingest |
| Claude Code | server.py | stdio JSON-RPC | MCP transport (see Transport section) |
| Windows Task Scheduler | server.py | process spawn | Boot-time auto-start |

**Ingest and server are separate processes by design.** They share only the SQLite file. Ingest writes; server reads. This separation means the server never needs to restart after ingest — SQLite WAL mode makes the new data immediately visible to readers.

---

## Data Flow

### Ingest path (manual, run after each export download)

```
1. User downloads ZIP from claude.ai Settings → Export
2. User runs:  python ingest.py --input ~/Downloads/claude-export.zip
3. ingest.py unzips to temp directory
4. Iterates conversation JSON files
5. For each conversation:
   a. Parse metadata (id, title, created_at, updated_at, project name)
   b. Parse turns (role, text content, timestamp)
   c. Concatenate all turn text into a single searchable blob
   d. Upsert into `conversations` table (ON CONFLICT DO UPDATE)
   e. FTS5 virtual table updates automatically via trigger or content= table
6. Commit. Temp directory cleaned up.
7. Print summary: N conversations ingested, M updated, elapsed time.
```

### Query path (per Claude Code tool call)

```
1. Claude Code invokes tool, e.g.:
   search_conversations(query="authentication JWT", project_filter="api-project")
2. server.py receives JSON-RPC call over stdio
3. Handler builds FTS5 query:
   SELECT c.id, c.title, c.project, c.created_at,
          snippet(conversations_fts, 2, '<', '>', '...', 20) AS snippet
   FROM conversations_fts
   JOIN conversations c ON conversations_fts.rowid = c.id
   WHERE conversations_fts MATCH ?
     AND (? IS NULL OR c.project = ?)
   ORDER BY rank
   LIMIT 10
4. Rows returned as JSON list of {id, title, project, created_at, snippet}
5. MCP tool returns this list to Claude Code
6. Claude model reads snippets, decides whether to call get_conversation(id)
   for full content
```

### Full content retrieval

```
get_conversation(id) →
  SELECT all turns for conversation id, ordered by position →
  Return [{role, text, timestamp}, ...] array
```

---

## SQLite Schema Design

### Confidence: HIGH (SQLite FTS5 docs, stdlib behavior well-established)

#### Core tables

```sql
PRAGMA journal_mode = WAL;   -- allows concurrent reads during ingest write
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,   -- claude.ai conversation UUID
    title       TEXT NOT NULL,
    project     TEXT,               -- NULL if no project assigned
    created_at  TEXT NOT NULL,      -- ISO-8601 UTC
    updated_at  TEXT NOT NULL,      -- ISO-8601 UTC
    turn_count  INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL       -- ISO-8601 UTC, set by ingest script
);

CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    position        INTEGER NOT NULL,   -- 0-based ordering within conversation
    role            TEXT NOT NULL,      -- 'human' | 'assistant'
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL       -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_turns_conversation
    ON turns(conversation_id, position);

CREATE INDEX IF NOT EXISTS idx_conversations_project
    ON conversations(project);

CREATE INDEX IF NOT EXISTS idx_conversations_updated
    ON conversations(updated_at DESC);
```

#### FTS5 virtual table

Two valid approaches:

**Option A: Content table (recommended)**

The FTS5 index mirrors `conversations` but stores only the text content. The content= parameter links it to the source table, which means SQLite won't duplicate the full text in the FTS index — it retrieves content from the base table when needed. Requires a trigger to keep in sync.

```sql
-- The searchable text column combines title + all turn content
-- Pre-computed at ingest time into a denormalized column
ALTER TABLE conversations ADD COLUMN full_text TEXT;  -- denormalized for FTS

CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    title,
    full_text,
    project UNINDEXED,          -- stored in index but not searchable (filter only)
    content='conversations',    -- content table: don't duplicate text in index
    content_rowid='rowid'       -- conversations.rowid maps to FTS rowid
);

-- Triggers to keep FTS in sync with base table
CREATE TRIGGER conv_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, title, full_text, project)
    VALUES (new.rowid, new.title, new.full_text, new.project);
END;

CREATE TRIGGER conv_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, title, full_text, project)
    VALUES ('delete', old.rowid, old.title, old.full_text, old.project);
END;

CREATE TRIGGER conv_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, title, full_text, project)
    VALUES ('delete', old.rowid, old.title, old.full_text, old.project);
    INSERT INTO conversations_fts(rowid, title, full_text, project)
    VALUES (new.rowid, new.title, new.full_text, new.project);
END;
```

**Why `full_text` is a denormalized column on `conversations`:**

Rather than joining all turns at query time for FTS indexing, ingest builds `full_text` once as `title + "\n\n" + " ".join(turn.content for turn in turns)`. This is the text FTS5 indexes. Query-time JOIN to get full turns is still possible via `get_conversation(id)`.

**Option B: Separate FTS table with stored content**

Simpler, no triggers needed, but doubles storage (text stored in both `full_text` column and FTS index):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    title,
    full_text
    -- no content= means FTS stores its own copy
);
```

**Recommendation: Option A (content table + triggers).** Less storage, FTS rowid maps cleanly to conversations.rowid, snippet() works correctly.

#### FTS5 query notes

- Use `MATCH` with BM25 ranking (FTS5 default): `WHERE conversations_fts MATCH 'authentication JWT'`
- `rank` column is automatically available; `ORDER BY rank` gives BM25-ranked results
- `snippet()` function extracts context around matches: `snippet(conversations_fts, 1, '[', ']', '...', 25)`
  - Args: table, column-index, start-match-tag, end-match-tag, ellipsis, token-count
- Phrase queries: `MATCH '"exact phrase"'`
- Prefix queries: `MATCH 'auth*'`

---

## MCP Transport

### Confidence: HIGH for general MCP spec; MEDIUM for Windows-specific Claude Code config path

### stdio vs HTTP/SSE

| Transport | How it works | Pros | Cons |
|-----------|-------------|------|------|
| **stdio** | Claude Code spawns the server process; communicates over stdin/stdout as JSON-RPC | No port conflicts, no firewall rules, Claude Code manages process lifecycle | Server restarts if Claude Code session ends (unless Task Scheduler keeps a separate instance) |
| **HTTP/SSE** (streamable HTTP) | Server runs as persistent HTTP process on localhost; Claude Code connects via URL | True persistent process, survives Claude Code restarts, Task Scheduler model fits naturally | Port must be available, slightly more config |

### For this project: HTTP/SSE transport is the correct choice.

**Rationale:**

1. The project requirement specifies Task Scheduler auto-start on boot — this means the server is a persistent background process independent of any Claude Code session. stdio transport means Claude Code would spawn a new process per session, which defeats the Task Scheduler requirement.

2. With HTTP transport on `127.0.0.1:PORT`, Task Scheduler starts the server once at boot. Every Claude Code session connects to the already-running server. No process overhead per session.

3. The MCP Python SDK supports both transports. HTTP/SSE was introduced as `streamable-http` in the SDK (replacing the older SSE-only transport). As of the SDK versions available at training cutoff, the pattern is:

```python
# server.py — HTTP transport
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("claude-history")

@mcp.tool()
def search_conversations(query: str, project_filter: str | None = None, include_full_content: bool = False) -> list[dict]:
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
```

### Claude Code MCP config on Windows

Claude Code reads MCP server configuration from a JSON config file. The file location depends on scope:

**Global config (all projects):**
```
%APPDATA%\Claude\claude_desktop_config.json
```
Typically resolves to:
```
C:\Users\<username>\AppData\Roaming\Claude\claude_desktop_config.json
```

**Project-scoped config (alternative):**
A `.mcp.json` file at the repo root or a `.claude/mcp.json` within the project. Claude Code picks this up automatically when you open that project directory.

**IMPORTANT:** Validate the exact Windows path against current Claude Code documentation — this is the most likely area where training data may be stale. The config file name and location changed between Claude Code versions.

**Config entry for HTTP transport:**

```json
{
  "mcpServers": {
    "claude-history": {
      "url": "http://127.0.0.1:8765/mcp",
      "transport": "http"
    }
  }
}
```

**Config entry for stdio transport (if HTTP is not available):**

```json
{
  "mcpServers": {
    "claude-history": {
      "command": "python",
      "args": ["C:\\Users\\nclem\\Claude Code\\claude-history\\server.py"],
      "transport": "stdio"
    }
  }
}
```

**Recommendation: Start with stdio transport for initial development, switch to HTTP for the Task Scheduler deployment.**

Stdio is simpler to test (no port management, no firewall) and the MCP SDK makes transport switching trivial — it's one argument change in `mcp.run()`. Validate the full pipeline works first, then switch transport and test the persistent-process model.

### Port selection

Use `8765` (not a well-known port, low collision risk for local tools). Bind to `127.0.0.1` not `0.0.0.0`.

---

## File / Module Structure

### Confidence: HIGH (standard Python project conventions + MCP SDK patterns)

```
claude-history/
├── server.py               # MCP server entry point — runs as persistent process
├── ingest.py               # CLI tool — run manually after each export
├── db.py                   # Database module: schema creation, query functions
├── search.py               # FTS5 query building, snippet extraction, result shaping
├── models.py               # Dataclasses: Conversation, Turn, SearchResult
├── config.py               # Paths, port, db location — single source of truth
│
├── history.db              # SQLite database (gitignored)
│
├── requirements.txt        # mcp[cli], (no other runtime deps needed)
├── .gitignore              # history.db, __pycache__, *.pyc, export zips
│
├── .planning/              # GSD planning files (not shipped)
│   ├── PROJECT.md
│   └── research/
│       └── ARCHITECTURE.md
│
└── scripts/
    └── task-scheduler-setup.ps1   # PowerShell to register Task Scheduler entry
```

### Module responsibilities

**`config.py`**
```python
from pathlib import Path

DB_PATH = Path(__file__).parent / "history.db"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
SEARCH_RESULT_LIMIT = 10
SNIPPET_TOKENS = 25
```
Single import point. Keeps paths out of every other module.

**`models.py`**
Dataclasses for Conversation, Turn, SearchResult. No logic — pure data shapes. Makes type hints useful across modules.

**`db.py`**
- `init_db(db_path)` — creates schema if not exists, sets PRAGMA WAL
- `upsert_conversation(conn, conversation)` — used by ingest
- `get_conversation(conn, id)` — used by server
- No FTS query logic here; that lives in `search.py`

**`search.py`**
- `fts_search(conn, query, project_filter, limit)` — builds MATCH query, returns SearchResult list
- `build_snippet(...)` — wraps FTS5 snippet() function
- Isolated so query logic can be tested independently of the MCP server

**`ingest.py`**
- CLI entry point: `python ingest.py --input path/to/export.zip`
- Unzips, discovers conversation files, calls `db.upsert_conversation`
- Reports summary. No MCP dependency.

**`server.py`**
- Instantiates FastMCP, registers tools
- Tool implementations call `search.fts_search` and `db.get_conversation`
- Single `if __name__ == "__main__": mcp.run(...)` block
- Keeps tool handler code thin — delegate to search.py and db.py

### Why separate ingest.py and server.py (not combined)?

1. **Different lifecycles.** Server runs continuously; ingest runs once per export cycle.
2. **Different dependencies.** Ingest needs ZIP handling, JSON parsing. Server needs MCP SDK.
3. **Testing.** Each can be tested independently.
4. **Restart isolation.** Ingesting new data does not require restarting the server. SQLite WAL lets the server see new rows without any intervention.

---

## Build Order

### Confidence: HIGH (dependency ordering is straightforward)

Build in dependency order — each component can be tested before the next depends on it.

### Phase 1: Schema and ingest (no MCP required)

**1. `config.py`** — zero dependencies, establish paths first
**2. `models.py`** — define data shapes before any logic
**3. `db.py`** — schema creation and upsert logic; test with `sqlite3` CLI
**4. Reverse-engineer export format** — examine actual ZIP from claude.ai before writing parser
**5. `ingest.py`** — parse export, call db functions; validate with real export file

Test: run ingest, open `history.db` in DB Browser for SQLite, verify rows and FTS index.

### Phase 2: Search (no MCP required)

**6. `search.py`** — FTS5 query building; test directly with `python -c "import search; ..."`

Test: query the populated DB, verify snippets and ranking look correct.

### Phase 3: MCP server (depends on 1-6)

**7. `server.py` with stdio transport** — wire tools to search.py and db.py
**8. Test with MCP Inspector or `mcp dev server.py`** — validate tools work before touching Claude Code config
**9. Register in Claude Code config** — add stdio entry, test in a real Claude Code session
**10. Switch to HTTP transport** — change `mcp.run()` arg, update Claude Code config to URL form
**11. `scripts/task-scheduler-setup.ps1`** — register as boot-time service

### Why this order?

- Steps 1-5 can be done and validated without installing the MCP SDK
- Steps 6 validates FTS5 search quality before building the MCP surface
- Step 8 (MCP Inspector) catches tool schema errors before they become Claude Code config problems
- HTTP transport (step 10) is deferred until the pipeline is proven — it's easy to switch once the rest works
- Task Scheduler setup (step 11) is last because it's operational infrastructure, not logic

---

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Separate ingest.py and server.py | Different lifecycles, enables server to stay running during ingest |
| SQLite WAL mode | Allows concurrent readers while ingest is writing; essential for the separate-process model |
| FTS5 content table with triggers | Less storage than standalone FTS table; rowid alignment keeps JOINs clean |
| Denormalized `full_text` column | Build searchable text once at ingest; avoids expensive JOIN-and-concat at FTS index time |
| HTTP transport for production | Matches Task Scheduler persistent-process requirement; stdio for dev only |
| `search.py` isolated from `server.py` | Testable without MCP infrastructure; keeps tool handlers thin |
| Single `config.py` for paths/ports | Prevents hardcoded paths scattered across modules |

---

## Gaps and Validation Required

| Gap | Risk | How to resolve |
|-----|------|---------------|
| Claude.ai export JSON schema unknown | High — ingest parser cannot be written until schema is seen | Examine actual export ZIP before Phase 2 |
| Claude Code config file path on Windows | Medium — path may differ by Claude Code version | Check `claude config` command output or official Claude Code docs |
| MCP SDK streamable-http transport API | Medium — API may differ from training-data knowledge | Check `mcp` package changelog / README after install |
| Task Scheduler + Python venv interaction | Low-medium — scheduler may not activate venv automatically | Test with full absolute path to venv python.exe in scheduler entry |
| FTS5 content= table trigger behavior on upsert | Low — triggers handle INSERT/DELETE/UPDATE, but ON CONFLICT DO UPDATE path needs verification | Test upsert with duplicate conversation ID in populated DB |
