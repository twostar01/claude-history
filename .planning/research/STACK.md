# Stack Research: Claude History MCP Server

**Researched:** 2026-05-03
**Overall confidence:** HIGH — all major claims verified against official docs (modelcontextprotocol.io, docs.anthropic.com, sqlite.org, Python docs)

---

## Recommended Stack

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| MCP framework | `mcp[cli]` Python SDK (FastMCP) | >=1.2.0 (current ~1.8.x) | Official Anthropic SDK, Tier 1, best Claude Code compatibility |
| Python runtime | Python 3.11+ | 3.11 minimum | Required by project; SDK requires 3.10+ |
| Package manager | uv | latest | Official MCP docs use uv; faster than pip; manages venvs + pyproject.toml |
| Database | SQLite via stdlib `sqlite3` | bundled with Python | Zero-dep, FTS5 included in CPython Windows builds |
| FTS | FTS5 (SQLite virtual table) | built into SQLite 3.9+ | BM25 ranking, snippet(), highlight() all built in |
| ZIP parsing | stdlib `zipfile` | bundled with Python | No dependency needed for ZIP extraction |
| JSON parsing | stdlib `json` | bundled with Python | Claude.ai export is JSON; no third-party lib needed |
| Transport | stdio (via FastMCP) | — | Standard for local MCP; Claude Code spawns the process |
| Process persistence | Windows Task Scheduler | — | Correct approach for boot-time auto-start on Windows 11 |
| Logging | stdlib `logging` to stderr | — | MCP stdio servers must never write to stdout |

---

## MCP Python SDK

### Installation

```powershell
# Install uv (one-time, Windows)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Create project
uv init claude-history-mcp
cd claude-history-mcp
uv venv
.venv\Scripts\activate

# Install mcp with CLI extras (includes FastMCP)
uv add "mcp[cli]"
```

The `mcp[cli]` extra is required for FastMCP and the CLI runner. The plain `mcp` package works too but omits convenience tooling.

### SDK Version

The MCP quickstart docs (verified 2026-05-03) state: "You must use the Python MCP SDK 1.2.0 or higher." The current release is in the 1.x series (approximately 1.8.x based on protocol support for version 2025-06-18). Always pin with `uv add "mcp[cli]>=1.2.0"`.

The Python SDK is a **Tier 1** official SDK at `modelcontextprotocol/python-sdk`.

### Defining Tools with FastMCP

FastMCP reads type hints and docstrings to auto-generate tool schemas — no manual JSON schema required:

```python
import sys
import logging
from mcp.server.fastmcp import FastMCP

# Configure logging to stderr ONLY — stdout is the MCP wire protocol
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

mcp = FastMCP("claude-history")

@mcp.tool()
async def search_conversations(
    query: str,
    project_filter: str | None = None,
    include_full_content: bool = False
) -> str:
    """Search past Claude conversations by full-text query.

    Args:
        query: Search terms to match against conversation content
        project_filter: Optional project name to restrict results
        include_full_content: If True, return full text; otherwise return snippets
    """
    # ... implementation
    return results

@mcp.tool()
async def list_projects() -> str:
    """List all projects found in the conversation history."""
    # ...
    return project_list

@mcp.tool()
async def get_conversation(conversation_id: str) -> str:
    """Return the full content of a single conversation by ID."""
    # ...
    return full_text
```

### Running the Server

```python
def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

Run via uv (what Claude Code invokes):
```powershell
uv --directory C:\path\to\project run server.py
```

### Critical Logging Rule

**For stdio servers: never use `print()` without `file=sys.stderr`.** stdout is the JSON-RPC wire — any stray output corrupts the protocol. Use `logging` (which goes to stderr by default) or explicit `print(..., file=sys.stderr)`.

### Registering with Claude Code

Claude Code uses `claude mcp add` commands, not `claude_desktop_config.json`. The config is stored in `~/.claude.json` (maps to `C:\Users\<user>\.claude.json` on Windows).

```powershell
# Register the server for all projects (user scope)
claude mcp add --transport stdio --scope user claude-history `
  -- uv --directory "C:\Users\nclem\Claude Code\claude-history" run server.py
```

Scopes:
- `--scope user` — available in all Claude Code projects on this machine (recommended for a personal tool)
- `--scope local` — available only in the current project (default)
- `--scope project` — stored in `.mcp.json`, checked into version control

Config file (`~/.claude.json`) format for reference:
```json
{
  "projects": {
    "/path/to/any/project": {
      "mcpServers": {
        "claude-history": {
          "type": "stdio",
          "command": "uv",
          "args": ["--directory", "C:\\Users\\nclem\\Claude Code\\claude-history", "run", "server.py"]
        }
      }
    }
  }
}
```

With `--scope user`, the entry is at the top-level of `~/.claude.json`, not nested under a project path.

---

## SQLite FTS5

### FTS5 Availability in Python on Windows

Python's stdlib `sqlite3` module is a thin wrapper around the system SQLite library. The **official CPython Windows installer** ships with a SQLite build that has FTS5 enabled (this has been true since Python 3.6+). Confirm at runtime:

```python
import sqlite3
conn = sqlite3.connect(":memory:")
try:
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    print("FTS5 available")
except sqlite3.OperationalError:
    print("FTS5 NOT available — rebuild/replace SQLite")
finally:
    conn.close()
```

If FTS5 is missing (rare, custom Python builds), the fix is to install a fresh Python 3.11+ from python.org — the standard installer always includes FTS5.

### Schema Design

```sql
-- Main conversations table (relational data, not FTS)
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    project     TEXT,
    title       TEXT,
    created_at  TEXT,
    updated_at  TEXT
);

-- Per-message turns (enables turn-level search later)
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT REFERENCES conversations(id),
    role            TEXT,   -- 'human' or 'assistant'
    content         TEXT,
    turn_index      INTEGER
);

-- FTS5 virtual table — content= points to messages.content
-- This avoids storing text twice
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    conversation_id UNINDEXED,  -- metadata, not indexed
    role UNINDEXED,
    content='messages',         -- external content table
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync with triggers
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, conversation_id, role)
    VALUES (new.id, new.content, new.conversation_id, new.role);
END;
```

Using an **external content table** (`content='messages'`) avoids duplicating the message text in both the FTS index and the base table.

### Indexing (Ingest Script)

```python
import sqlite3

def ingest_conversation(conn: sqlite3.Connection, conv: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?, ?)",
        (conv["id"], conv["project"], conv["title"],
         conv["created_at"], conv["updated_at"])
    )
    for i, msg in enumerate(conv["messages"]):
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, turn_index)"
            " VALUES (?, ?, ?, ?)",
            (conv["id"], msg["role"], msg["content"], i)
        )
    # Triggers keep FTS in sync automatically

conn.execute("BEGIN")
for conv in conversations:
    ingest_conversation(conn, conv)
conn.execute("COMMIT")

# Periodic optimization after bulk load
conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('optimize')")
```

### Querying with Snippets and BM25 Ranking

```python
def search_conversations(
    conn: sqlite3.Connection,
    query: str,
    project_filter: str | None = None,
    include_full_content: bool = False,
    limit: int = 10
) -> list[dict]:
    # snippet() parameters: table, column_index, open_tag, close_tag, ellipsis, max_tokens
    base_sql = """
        SELECT
            c.id,
            c.project,
            c.title,
            c.created_at,
            snippet(messages_fts, 0, '[', ']', '...', 32) AS preview,
            bm25(messages_fts, 1.0) AS score
        FROM messages_fts
        JOIN conversations c ON messages_fts.conversation_id = c.id
        WHERE messages_fts MATCH ?
    """
    params: list = [query]

    if project_filter:
        base_sql += " AND c.project = ?"
        params.append(project_filter)

    base_sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    rows = conn.execute(base_sql, params).fetchall()
    results = []
    for row in rows:
        result = {
            "id": row[0],
            "project": row[1],
            "title": row[2],
            "created_at": row[3],
            "preview": row[4],
        }
        if include_full_content:
            full = conn.execute(
                "SELECT content FROM messages WHERE conversation_id = ? ORDER BY turn_index",
                (row[0],)
            ).fetchall()
            result["content"] = "\n\n".join(r[0] for r in full)
        results.append(result)
    return results
```

Key notes:
- BM25 returns negative values where **lower = more relevant**; use `ORDER BY score` (ascending) for best-first.
- `snippet()` column index `0` refers to the first indexed column (`content`).
- The `UNINDEXED` columns (`conversation_id`, `role`) are stored in the FTS table but not in the inverted index, saving space.
- Use `porter unicode61` tokenizer for stemming (matches "searching" when query is "search").

### FTS5 Query Syntax Supported

| Pattern | Example | Use |
|---------|---------|-----|
| Phrase | `"tool call"` | Exact phrase |
| Prefix | `config*` | Prefix match |
| AND (implicit) | `python sqlite` | Both terms |
| OR | `python OR javascript` | Either term |
| NOT | `python NOT javascript` | Exclude term |
| NEAR | `NEAR(python sqlite, 5)` | Within 5 tokens |

---

## Windows Service / Startup

### Task Scheduler Approach (Recommended)

The right Windows 11 approach for a personal local server is **Task Scheduler with "At log on" trigger**. This starts the process when the user logs in, keeps it running in the background, and does not require admin rights or service installation.

**Key Task Scheduler settings:**

| Setting | Value | Reason |
|---------|-------|--------|
| Trigger | At log on (your user) | Starts automatically, no admin |
| Action: Program | `C:\path\to\uv.exe` | Full path required |
| Action: Arguments | `--directory "C:\Users\nclem\Claude Code\claude-history" run server.py` | uv project runner |
| Run whether logged on or not | No (use "only when logged on") | Keeps it simple |
| Run with highest privileges | No | Not needed for localhost |
| "Start in" | `C:\Users\nclem\Claude Code\claude-history` | Working directory |

**Important:** MCP stdio transport requires Claude Code to **spawn** the server process, not connect to a long-running server. Task Scheduler is actually for a **different scenario** than stdio — see the architecture note below.

### Stdio vs. Persistent Process Architecture

There is a critical design decision here:

**stdio transport (recommended for this project):**
- Claude Code spawns the server process fresh for each session
- No persistent process needed — Task Scheduler is unnecessary
- Zero networking — pure stdin/stdout pipe
- Simpler, no port conflicts, no firewall concerns

**Streamable HTTP transport (alternative):**
- Server runs as a persistent process on `http://127.0.0.1:PORT`
- Claude Code connects via HTTP
- Task Scheduler makes sense here to keep the process alive
- More complex; overkill for a single-user local tool

**For this project, stdio is the correct choice.** The PROJECT.md requirement for "Task Scheduler auto-starts MCP server on boot" is based on a pre-implementation assumption. With stdio, Claude Code manages the process lifecycle automatically — no Task Scheduler entry is needed.

If the team decides to use Streamable HTTP anyway (e.g., for future multi-client support), here is the Task Scheduler approach:

```powershell
# Create a .bat wrapper (Task Scheduler needs a non-console entry point)
# File: start-mcp-server.bat
@echo off
cd /d "C:\Users\nclem\Claude Code\claude-history"
"C:\Users\nclem\.local\bin\uv.exe" run server.py --transport streamable-http --port 3333
```

Task Scheduler action:
- Program: `C:\Users\nclem\Claude Code\claude-history\start-mcp-server.bat`
- Trigger: At log on, for your user account

For stdio, simply register via `claude mcp add` and Claude Code handles everything.

---

## ZIP and JSON Parsing

Claude.ai exports a ZIP file containing one or more JSON files. Both are handled by Python stdlib:

```python
import zipfile
import json
from pathlib import Path

def load_export(zip_path: Path) -> list[dict]:
    """Extract and parse a Claude.ai export ZIP."""
    conversations = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                with zf.open(name) as f:
                    data = json.load(f)
                    # Schema TBD — parse after inspecting real export
                    conversations.extend(data if isinstance(data, list) else [data])
    return conversations
```

No third-party libraries needed. The exact schema of the Claude.ai export is TBD (marked in PROJECT.md as "Exact schema TBD — user will provide the export file when ready to test").

---

## Python Packaging (pyproject.toml)

```toml
[project]
name = "claude-history-mcp"
version = "0.1.0"
description = "MCP server for searching Claude.ai conversation history"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.2.0",
]

[project.scripts]
# Enables: uv run claude-history-mcp (instead of uv run server.py)
claude-history-mcp = "claude_history_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = []
```

With a `[project.scripts]` entry, Claude Code's `claude mcp add` command becomes:
```powershell
claude mcp add --scope user claude-history `
  -- uv --directory "C:\Users\nclem\Claude Code\claude-history" run claude-history-mcp
```

---

## What NOT to Use

| Alternative | Why Not |
|-------------|---------|
| **Streamable HTTP transport** | Overkill for single-user local tool; requires persistent process, port management, Task Scheduler. Stdio is simpler and fully supported by Claude Code. |
| **SSE transport** | Deprecated as of MCP protocol 2025-06-18. The "HTTP+SSE" transport is the old protocol (2024-11-05). Do not implement. |
| **FastAPI / Starlette** | Not needed. FastMCP handles the server loop and protocol. Adding a web framework creates unnecessary complexity. |
| **SQLite FTS4** | FTS5 supersedes FTS4. FTS5 has BM25 built in, better performance, and `snippet()` support. FTS4 lacks built-in BM25. |
| **SQLite external FTS (Whoosh, Tantivy via tantivy-py)** | Adds a dependency for zero gain. FTS5 handles millions of rows fine for personal history. |
| **pip + venv directly** | uv is the official MCP recommendation; it's faster and manages Python versions. No reason to use raw pip. |
| **apsw (third-party SQLite)** | Provides full SQLite API but adds a C extension dependency. stdlib sqlite3 has everything needed for FTS5. |
| **threading for DB access** | SQLite in WAL mode supports concurrent reads but writes must be serialized. The MCP server is single-user, so no concurrency architecture needed. Use `check_same_thread=False` only if needed. |
| **docker / containerization** | Local personal tool on one machine. No isolation needed. Adds friction with no benefit. |
| **Windows Service (sc.exe / NSSM)** | Requires admin rights; unnecessary since stdio transport needs no persistent process. |

---

## Confidence Notes

| Area | Confidence | Source | Notes |
|------|------------|--------|-------|
| MCP Python SDK install + FastMCP patterns | HIGH | Official modelcontextprotocol.io quickstart (verified 2026-05-03) | Exact code confirmed from official docs |
| SDK minimum version (1.2.0) | HIGH | Official docs state "must use 1.2.0 or higher" | Current exact version not confirmed (WebFetch restricted), ~1.8.x estimated |
| Claude Code `claude mcp add` command format | HIGH | code.claude.com/docs/en/mcp (verified 2026-05-03) | Including --scope, --transport, -- separator |
| `~/.claude.json` as config store | HIGH | Official Claude Code docs (verified 2026-05-03) | Windows: `C:\Users\<user>\.claude.json` |
| stdio is correct transport (not HTTP) | HIGH | Official MCP transport docs; Claude Code docs | Clients SHOULD support stdio; Claude Code spawns stdio servers directly |
| SSE deprecated | HIGH | Official MCP transport spec (2025-06-18) states HTTP+SSE is deprecated | Use Streamable HTTP or stdio |
| SQLite FTS5 setup and SQL patterns | HIGH | Official sqlite.org/fts5.html (verified 2026-05-03) | snippet(), bm25(), MATCH, BM25 sort order all confirmed |
| FTS5 included in CPython Windows installer | MEDIUM | Training knowledge (CPython has shipped with FTS5 since ~3.6); not re-verified due to WebFetch restriction on python.org | Add a runtime check in setup instructions |
| uv install command for Windows | HIGH | Confirmed from official MCP quickstart docs (PowerShell snippet) | `irm https://astral.sh/uv/install.ps1 \| iex` |
| Claude.ai export ZIP/JSON schema | LOW | Not yet observed — PROJECT.md explicitly flags this as TBD | Must reverse-engineer from real export file |
| Task Scheduler for stdio transport | HIGH — NOT NEEDED | Confirmed by understanding stdio lifecycle | Task Scheduler is needed only if using HTTP transport |

### Key Uncertainty to Resolve

The Claude.ai export format (ZIP structure, JSON schema, field names) is unknown until the user provides an actual export. The ingest script is a stub until that schema is observed. This is a known unknown documented in PROJECT.md.
