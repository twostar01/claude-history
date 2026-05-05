# Phase 3: MCP Tools - Pattern Map

**Mapped:** 2026-05-05
**Files analyzed:** 3 (models.py NEW, search.py NEW, server.py MODIFY)
**Analogs found:** 3 / 3

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/claude_history/models.py` | model/utility | transform | `src/claude_history/ingest.py` (dataclass-free; plain dicts) | role-match (skip file per research Q2) |
| `src/claude_history/search.py` | service | request-response (read-only) | `src/claude_history/ingest.py` (DB open/close/cursor) | role-match |
| `src/claude_history/server.py` | controller/entry-point | request-response | `src/claude_history/server.py` itself (stub, lines 1-41) | exact (in-place replacement) |

---

## Pattern Assignments

### `src/claude_history/models.py` (model, transform)

**Decision from RESEARCH.md Q2:** Skip `models.py` entirely. FastMCP auto-converts `list[dict]` correctly; plain dicts are sufficient. Only create this file if type errors arise during implementation. If created, use stdlib `dataclasses` — no third-party dependency needed.

**Analog:** N/A — no dataclass/TypedDict modules exist in this codebase.

**If the file is created, imports pattern to follow (mirror ingest.py style):**
```python
# src/claude_history/models.py
from dataclasses import dataclass
```

**No further pattern needed.** Planner should treat `models.py` as optional and note it in the plan.

---

### `src/claude_history/search.py` (service, request-response)

**Analog:** `src/claude_history/ingest.py`

**Imports pattern** (`ingest.py` lines 14-30):
```python
import logging
import sys

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)
```
search.py must NOT call `logging.basicConfig()` at module level (that is only done once, in `server.py:main()`). Instead use module-level `log = logging.getLogger(__name__)` only.

**Import pattern for DB access** (`ingest.py` lines 84, 203-204):
```python
from claude_history.db import init_db
from claude_history.config import DB_PATH
```

**DB connection lifecycle pattern** (`ingest.py` lines 86-87, 179-181):
```python
conn = init_db(db_path)
try:
    cur = conn.cursor()
    # ... all DB work here ...
    conn.commit()   # omit in search.py — read-only, no commit needed
finally:
    conn.close()
```
search.py is read-only; omit `conn.commit()` but keep the `try/finally conn.close()` structure.

**row_factory pattern** (RESEARCH.md Pattern 4 — verified against server.py+db.py):
```python
conn = init_db(DB_PATH)
try:
    conn.row_factory = sqlite3.Row   # set immediately after init_db()
    cur = conn.cursor()
    # access rows as row["column_name"]
    ...
finally:
    conn.close()
```

**FTS5 query with bm25 — Step 1** (RESEARCH.md Pattern 1, verified against live DB):
```python
def _fts_rows(cur, fts_query: str) -> list:
    cur.execute("""
        SELECT m.conversation_id, m.rowid, bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        WHERE messages_fts MATCH ?
        ORDER BY bm25(messages_fts)
    """, (fts_query,))
    return cur.fetchall()
```
Critical: `bm25()` only valid in direct FTS virtual table query. Never wrap in subquery or GROUP BY.

**FTS5 sanitization fallback — D-05** (RESEARCH.md Pattern 2, verified against live DB):
```python
try:
    rows = _fts_rows(cur, query)
except sqlite3.OperationalError:
    escaped = query.replace('"', '""')
    rows = _fts_rows(cur, f'"{escaped}"')
    query = f'"{escaped}"'  # use sanitized form for subsequent snippet() calls too
```

**Python aggregation for one-result-per-conversation — D-02** (RESEARCH.md Pattern 1):
```python
best = {}  # conv_id -> {"rowid": int, "score": float, "count": int}
for row in rows:
    cid = row["conversation_id"]
    if cid not in best:
        best[cid] = {"rowid": row["rowid"], "score": row["score"], "count": 1}
    else:
        best[cid]["count"] += 1

ranked = sorted(best.items(), key=lambda x: x[1]["score"])
top_n = ranked[:limit]  # limit defaults to 10 (D-01)
```
bm25() returns negative scores; lower (more negative) = better match. `sorted()` ascending puts best matches first.

**snippet() extraction — D-03** (RESEARCH.md Pattern 3, verified against live DB with avg=305 chars):
```python
cur.execute("""
    SELECT snippet(messages_fts, 0, '**', '**', '...', 64) AS snip
    FROM messages_fts
    WHERE messages_fts MATCH ? AND rowid = ?
""", (query, info["rowid"]))
snip_row = cur.fetchone()
snippet = snip_row["snip"] if snip_row else ""
```
`token_count=64` calibrated to ~300 chars average (RESEARCH.md Pitfall 4). snippet() requires the same MATCH to be active in the same query — cannot call it on a plain rowid separately.

**Empty results — D-06:**
```python
if not rows:
    return []
```

**Message ordering query — D-07** (used by get_conversation and export_conversation):
```python
cur.execute("""
    SELECT role, content, position
    FROM messages
    WHERE conversation_id = ?
    ORDER BY position ASC
""", (conv_id,))
```

**Role label mapping — D-08:**
```python
ROLE_LABEL = {"human": "Human", "assistant": "Assistant"}
label = ROLE_LABEL.get(role, role.capitalize())
```

**include_full_content concatenation — D-04:**
```python
if include_full_content:
    cur.execute("""
        SELECT role, content FROM messages
        WHERE conversation_id = ?
        ORDER BY position ASC
    """, (conv_id,))
    msg_rows = cur.fetchall()
    result["full_content"] = "\n\n".join(
        f"{('Human' if r['role'] == 'human' else 'Assistant')}: {r['content']}"
        for r in msg_rows
    )
```

**export_conversation markdown format — D-08, D-09, D-10:**
```python
lines = [
    f"# {conv['title'] or '(Untitled)'}",
    f"*Date: {conv['created_at']}*",
    "",
]
for msg in messages:
    label = "Human" if msg["role"] == "human" else "Assistant"
    lines.append(f"## {label}")
    lines.append("")
    lines.append(msg["content"])
    lines.append("")
return "\n".join(lines)
```

**get_stats file size — RESEARCH.md Pattern 7:**
```python
db_size_bytes = DB_PATH.stat().st_size
db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
```

**Error handling pattern** (`ingest.py` lines 98-109):
```python
# For missing-entity cases, return None or empty — do not raise
cur.execute("SELECT title, created_at FROM conversations WHERE id = ?", (id,))
conv = cur.fetchone()
if conv is None:
    return f"Conversation {id} not found."
```
No unhandled exceptions should reach the MCP caller. FTS `OperationalError` is caught by the sanitization fallback. Not-found cases return a descriptive string or empty list.

---

### `src/claude_history/server.py` (controller, request-response — in-place modification)

**Analog:** `src/claude_history/server.py` itself (lines 1-41 — the existing stub)

**Preserve exactly — lines 1-29 (logging setup, stdout-contamination guard):**
```python
"""Claude History MCP Server — FastMCP stdio stub (Phase 1)."""

import sys
sys.stderr.reconfigure(encoding="utf-8")  # must precede all other imports

import logging

# STDOUT CONTAMINATION RULE: logging.basicConfig() MUST be called before any
# FastMCP instantiation. The FastMCP stdio transport uses stdout exclusively for
# JSON-RPC framing. Any write to stdout silently corrupts the session.

from mcp.server.fastmcp import FastMCP


def main() -> None:
    """Entry point for `uv run server`."""

    # Step 1: Route ALL logging to stderr (must be before FastMCP() instantiation)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    log = logging.getLogger(__name__)
    log.info("claude-history MCP server starting")

    # Step 2: Create FastMCP instance AFTER logging is configured
    mcp = FastMCP("claude-history")
```

**Ordering rule (non-negotiable):** `sys.stderr.reconfigure()` BEFORE all other imports, then `logging.basicConfig()` BEFORE `FastMCP()` instantiation. This order must not change.

**Add new imports after line 6 (after `import sys`, before `import logging`):**
```python
import sqlite3
from pathlib import Path
from claude_history.config import DB_PATH
from claude_history.db import init_db
```
Or import `search` module functions directly if search.py is implemented as a separate module:
```python
from claude_history import search
```

**Tool decorator pattern — line 31-34 (copy for all 6 tools):**
```python
@mcp.tool()
def get_status() -> dict:
    """Return server health status. Smoke test target for Phase 1."""
    return {"status": "ok"}
```
`@mcp.tool()` with no arguments. FastMCP reads the function signature (type annotations) and docstring to auto-generate the JSON schema. Return type annotation determines schema output type.

**Preserve exactly — lines 36-41 (mcp.run and __main__ guard):**
```python
    # Step 3: Start the MCP stdio loop (blocks until client disconnects)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```
`mcp.run(transport="stdio")` must be the last statement in `main()`. All `@mcp.tool()` definitions must appear before this call.

**Tool return type conventions (RESEARCH.md Pattern 5):**
- List-returning tools: `-> list[dict]` — FastMCP serializes via `pydantic_core.to_json`
- Single-object tools: `-> dict`
- String-returning tools (export_conversation): `-> str` — returned as-is
- Empty list tools (list_projects): `-> list`

**get_status() promoted form (Claude's Discretion, RESEARCH.md Q1 recommendation):**
```python
@mcp.tool()
def get_status() -> dict:
    """Return server health and database statistics.

    Includes conversation count and last ingested date for a quick
    at-a-glance view of the indexed data.
    """
    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM conversations")
        conv_count = cur.fetchone()["n"]
        cur.execute("SELECT MAX(created_at) AS latest FROM conversations")
        latest = cur.fetchone()["latest"]
    finally:
        conn.close()
    return {"status": "ok", "conversations": conv_count, "last_ingested": latest}
```

**list_projects() docstring requirement (D-11, CONTEXT.md Specifics):**
```python
@mcp.tool()
def list_projects() -> list:
    """Return list of projects with conversation counts.

    NOTE: The Claude.ai export format (conversations.json) contains no
    project association field for conversations. This tool always returns
    an empty list. This is a data availability limitation in the export
    format, not a bug.
    """
    return []
```
The explanation must appear in the docstring so that Claude Code sessions calling the tool see the reason for the empty result in the tool schema.

---

## Shared Patterns

### DB Connection Lifecycle
**Source:** `src/claude_history/ingest.py` lines 86-87, 179-181
**Apply to:** Every tool in server.py that queries the DB (get_stats, get_status, search_conversations, get_conversation, export_conversation)
```python
conn = init_db(DB_PATH)
try:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # ... all queries ...
finally:
    conn.close()
```
One connection opened per tool call. No shared connection across tools. No `conn.commit()` in read-only tools.

### stderr-Only Logging
**Source:** `src/claude_history/server.py` lines 19-25, `src/claude_history/ingest.py` lines 25-30
**Apply to:** All modules (server.py, search.py, and any new module imported by server.py)
```python
# In server.py main() only — one-time setup:
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(levelname)s %(name)s %(message)s")

# In every module (search.py etc.) — module-level only:
log = logging.getLogger(__name__)
```
`logging.basicConfig()` is called exactly once in `server.py:main()`. All other modules use `logging.getLogger(__name__)` only. No `print()` anywhere. No `sys.stdout.write()` anywhere.

### Config Import
**Source:** `src/claude_history/config.py` lines 1-8; `src/claude_history/ingest.py` line 203
**Apply to:** search.py and server.py
```python
from claude_history.config import DB_PATH
```
`DB_PATH` is a `pathlib.Path` object already resolved to the project root. Do not recompute or hardcode it.

### init_db Import
**Source:** `src/claude_history/ingest.py` line 84
**Apply to:** search.py and server.py
```python
from claude_history.db import init_db
```
`init_db(db_path)` opens the connection, creates tables if absent (idempotent), enables WAL, and returns an open `sqlite3.Connection`. Always use it; do not call `sqlite3.connect()` directly.

### Not-Found / Empty Handling
**Source:** CONTEXT.md D-06; RESEARCH.md export_conversation example
**Apply to:** get_conversation, export_conversation, search_conversations
- `search_conversations`: return `[]` when FTS matches nothing
- `get_conversation` / `export_conversation`: return a descriptive string `f"Conversation {id} not found."` when the UUID does not exist in the DB
- Never raise an exception that would surface as an MCP error for a simple not-found case

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/claude_history/models.py` | model | transform | No dataclass/TypedDict modules exist in this codebase. RESEARCH.md recommends skipping this file entirely in favor of plain `list[dict]` / `dict` returns. |

---

## Metadata

**Analog search scope:** `src/claude_history/` (all 5 existing modules read in full)
**Files scanned:** config.py (9 lines), db.py (81 lines), ingest.py (206 lines), server.py (42 lines)
**Pattern extraction date:** 2026-05-05
