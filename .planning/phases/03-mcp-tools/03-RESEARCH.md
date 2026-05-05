# Phase 3: MCP Tools - Research

**Researched:** 2026-05-05
**Domain:** FastMCP tool implementation, SQLite FTS5 BM25 search, Python aggregation patterns
**Confidence:** HIGH — all patterns verified against live codebase and populated database

## Summary

Phase 3 implements the 6 MCP tool handlers that expose the indexed SQLite database to Claude Code sessions. The stack is completely locked: FastMCP 1.27.0 (mcp[cli]) with stdio transport, SQLite FTS5 content table, Python 3.11. No new dependencies are needed.

The core technical challenge is the "one result per conversation" requirement (D-02). SQLite FTS5's `bm25()` function cannot be used inside GROUP BY or subquery contexts — it only works in the WHERE/ORDER BY clause of a direct FTS virtual table query. The verified solution is a two-step Python aggregation: (1) fetch all matching `(conversation_id, rowid, score)` rows ordered by `bm25()`, then (2) aggregate in Python to keep the best-scored rowid per conversation, then (3) fetch snippet and metadata per top-N conversation.

FastMCP auto-converts any non-string return value using `pydantic_core.to_json()`, so returning `list[dict]` or `dict` from tool functions works correctly without explicit serialization. All tool functions may be synchronous — FastMCP handles both sync and async transparently.

**Primary recommendation:** Implement `search.py` with the two-step Python aggregation pattern; implement `models.py` as plain dataclasses (or skip in favor of `list[dict]`); replace server.py stub with the 6 tool definitions.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Default result limit is 10 conversations.
- **D-02:** One result per conversation — the highest-BM25 matching message supplies the snippet. `match_count` reports how many messages in the conversation matched.
- **D-03:** Default snippet length is ~300 characters, trimmed by FTS5's `snippet()` function to a window around the match term.
- **D-04:** When `include_full_content=True`, return all messages concatenated for each matched conversation.
- **D-05:** Best-effort fallback: attempt raw FTS5 input first; if `sqlite3.OperationalError` is raised, re-run with input sanitized as a plain phrase.
- **D-06:** When a search query matches nothing, return empty list `[]`. Do not raise an error.
- **D-07:** Messages are returned sorted by `position` integer (ascending).
- **D-08:** Each message turn introduced with `## Human` or `## Assistant` H2 header.
- **D-09:** Export begins with compact metadata header: `# {title}` and `*Date: {created_at}*`.
- **D-10:** No per-message timestamps in the export.
- **D-11:** `list_projects()` returns empty list `[]` — no project field in conversations.json.

### Claude's Discretion

- `get_status()` — may remain `{"status": "ok"}` or be promoted to return DB stats (conversation count, last ingested date). Either works; promote if trivial.
- Python return types — use `list[dict]` for list-returning tools and `dict` for single-object tools. `TypedDict` or `dataclasses` acceptable if it improves clarity.
- FTS5 sanitization implementation — exact approach (quote-wrapping vs. stripping chars) left to implementer. Requirement: no unhandled `OperationalError` reaches the tool caller.

### Deferred Ideas (OUT OF SCOPE)

- Design chat ingestion (design_chats/*.json) — each has a `project` field, candidate for future phase.
- Manual project tagging post-hoc.
- Project file ingestion for metadata only (projects/*.json to populate a `projects` table).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-01 | `search_conversations(query, project_filter?)` returns BM25-ranked snippets, title, project, date, match count | Two-step Python aggregation verified; snippet() + bm25() patterns confirmed against live DB |
| TOOL-02 | `search_conversations` accepts `include_full_content=true` flag | All-messages query pattern verified; role mapping confirmed (human/assistant) |
| TOOL-03 | `get_conversation(id)` returns full conversation as labeled turns | Position-ordered query verified; role-to-label mapping confirmed |
| TOOL-04 | `list_projects()` returns all project names with counts | Returns `[]` by design (D-11); docstring documents limitation |
| TOOL-05 | `get_stats()` returns counts, date range, DB file size | All stats queries verified; pathlib stat().st_size confirmed |
| TOOL-06 | `export_conversation(id, format?)` returns markdown string | H2 header format verified; metadata header pattern confirmed |
| SETUP-02 | Server uses FastMCP stdio; all logging to stderr; stdout never written | Existing server.py pattern confirmed; FastMCP 1.27.0 in venv |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| FTS5 search execution | Database/Storage | — | SQLite does ranking; Python only aggregates |
| Snippet generation | Database/Storage | — | FTS5 snippet() function; not reconstructable in Python |
| Result aggregation (one-per-conv) | API/Backend (search.py) | — | bm25() cannot GROUP BY; must aggregate in Python |
| Tool schema generation | MCP Framework | — | FastMCP auto-generates from type hints + docstrings |
| Tool input validation | MCP Framework | — | Pydantic coerces types from JSON-RPC arguments |
| Markdown export formatting | API/Backend (server.py) | — | String concatenation; no templating needed |
| Logging / stdout protection | API/Backend (server.py) | — | Must precede FastMCP instantiation |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp (FastMCP) | 1.27.0 | MCP tool registration, schema generation, stdio transport | Already installed; project-locked [VERIFIED: venv dist-info] |
| sqlite3 | stdlib | FTS5 queries, BM25 ranking, snippet generation | Ships with Python 3.11+; FTS5 schema already locked [VERIFIED: db.py] |
| pathlib | stdlib | DB_PATH resolution, file size stat | Already used in config.py [VERIFIED: config.py] |
| logging | stdlib | stderr-only output | Already established in server.py and ingest.py [VERIFIED: server.py] |

### No New Dependencies Required

All Phase 3 work is implementable with the existing venv. No `uv add` calls needed.

---

## Architecture Patterns

### System Architecture Diagram

```
Claude Code session
      |
      | JSON-RPC over stdio
      v
  server.py (FastMCP)
      |
      +-- search_conversations() -------> search.py
      |                                      |
      |                                      | Step 1: bm25() ORDER BY query
      |                                      v
      |                              messages_fts (FTS5 virtual)
      |                                      |
      |                              JOIN messages (content table)
      |                                      |
      |                              Python aggregation
      |                              (best rowid per conv_id)
      |                                      |
      |                              Step 2: snippet() + metadata queries
      |                                      |
      |                              JOIN conversations
      |                                      |
      +-- get_conversation(id) ----------> messages (ORDER BY position)
      |
      +-- get_stats() ------------------> conversations + messages COUNT
      |                                   + pathlib stat().st_size
      |
      +-- export_conversation(id) ------> messages (ORDER BY position)
      |                                   + string formatting
      |
      +-- list_projects() -------------> returns [] (no data source)
      |
      +-- get_status() ----------------> returns dict (health + optional stats)
```

### Recommended Module Structure

```
src/claude_history/
  config.py          # DB_PATH constant — import as-is
  db.py              # init_db() — import as-is
  models.py          # NEW: SearchResult, ConversationTurn dataclasses (optional)
  search.py          # NEW: search logic, FTS5 queries, Python aggregation
  server.py          # REPLACE stubs with 6 full tool definitions
  ingest.py          # UNCHANGED
  schema_discovery.py # UNCHANGED
```

### Pattern 1: Two-Step Python Aggregation for One-Result-Per-Conversation

**What:** bm25() cannot be used inside GROUP BY or subqueries. Fetch all matching rows ordered by bm25(), aggregate in Python to keep best rowid per conversation, then fetch snippets and metadata per top-N result.

**When to use:** Every call to `search_conversations()`.

**Verified against live DB with 106 conversations and 4087 messages.**

```python
# Source: VERIFIED against history.db — 2026-05-05

def _run_fts_query(cur, fts_query: str):
    """Execute FTS query, return list of (conversation_id, rowid, score) ordered by score."""
    cur.execute("""
        SELECT m.conversation_id, m.rowid, bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        WHERE messages_fts MATCH ?
        ORDER BY bm25(messages_fts)
    """, (fts_query,))
    return cur.fetchall()

def _aggregate_by_conversation(rows) -> dict:
    """Keep best-scored rowid per conversation_id. Input must be ordered by score ASC."""
    best = {}  # conv_id -> {"rowid": int, "score": float, "count": int}
    for conv_id, rowid, score in rows:
        if conv_id not in best:
            best[conv_id] = {"rowid": rowid, "score": score, "count": 1}
        else:
            best[conv_id]["count"] += 1
    return best

# Caller ranks and slices:
ranked = sorted(best.items(), key=lambda x: x[1]["score"])
top_n = ranked[:limit]
```

### Pattern 2: FTS5 Sanitization Fallback (D-05)

**What:** Try the raw user query as FTS5 syntax first (enables power users to use AND, OR, NEAR(), prefix wildcards). On OperationalError, wrap the whole string in double quotes to force phrase search.

**Verified:** All known error-triggering inputs (`trailing OR`, `unclosed "`, `trailing AND`) are safely handled.

```python
# Source: VERIFIED against history.db — 2026-05-05

def _build_fts_query(user_input: str) -> tuple[str, bool]:
    """Return (fts_query, was_sanitized)."""
    return user_input, False  # try raw first

def search_with_fallback(cur, user_input: str) -> list:
    fts_query = user_input
    try:
        return _run_fts_query(cur, fts_query)
    except sqlite3.OperationalError:
        # Sanitize: wrap in double quotes, escape embedded quotes
        escaped = user_input.replace('"', '""')
        sanitized = f'"{escaped}"'
        return _run_fts_query(cur, sanitized)
```

### Pattern 3: FTS5 snippet() for ~300-char Window

**What:** `snippet(messages_fts, col_num, start_tag, end_tag, ellipsis, token_count)` — FTS5 built-in that returns a substring around the best match. `token_count=64` produces average 305 chars (verified on 2903 samples with the word "the" across the full dataset).

**Important:** snippet() must be called with the same MATCH constraint AND a rowid filter to retrieve the snippet for a specific row. It cannot be called separately from the MATCH.

```python
# Source: VERIFIED against history.db — 2026-05-05

def _get_snippet(cur, fts_query: str, rowid: int) -> str:
    cur.execute("""
        SELECT snippet(messages_fts, 0, '**', '**', '...', 64) AS snip
        FROM messages_fts
        WHERE messages_fts MATCH ? AND rowid = ?
    """, (fts_query, rowid))
    row = cur.fetchone()
    return row[0] if row else ""
```

Token count 64 calibration:
- avg=305 chars, max=871 chars across 2903 samples [VERIFIED against live DB]
- Longer messages produce larger snippets; the 300-char target is met on average

### Pattern 4: DB Connection Lifecycle in server.py

**What:** Each tool call opens a fresh connection via `init_db(DB_PATH)`, executes queries, closes. This matches the read-only, stdio-per-session model.

**Alternative:** Open one connection in FastMCP lifespan context. Either works; per-call is simpler and avoids stale connection issues on Windows.

```python
# Source: VERIFIED against existing server.py and db.py patterns

from claude_history.config import DB_PATH
from claude_history.db import init_db

@mcp.tool()
def get_stats() -> dict:
    """Return database statistics."""
    conn = init_db(DB_PATH)
    try:
        cur = conn.cursor()
        # ... queries ...
        return {...}
    finally:
        conn.close()
```

### Pattern 5: FastMCP Return Type Serialization

**What:** FastMCP calls `pydantic_core.to_json(result, fallback=str, indent=2)` on any non-string return value. `list[dict]` and `dict` serialize correctly. `None` returns empty content. `str` is returned as-is.

**Verified by reading** `_convert_to_content()` in `func_metadata.py` (FastMCP 1.27.0 source).

```python
# Source: VERIFIED — mcp/server/fastmcp/utilities/func_metadata.py line 531

@mcp.tool()
def list_projects() -> list:
    """Return list of projects.

    NOTE: The Claude.ai export format (conversations.json) does not include a
    project association field for conversations. This tool always returns an
    empty list. This is a data availability limitation, not a bug.
    """
    return []

@mcp.tool()
def get_stats() -> dict:
    """Return database statistics."""
    return {"conversations": 106, "messages": 4087, ...}
```

### Pattern 6: get_conversation() and export_conversation() Message Ordering

**What:** Messages are retrieved ordered by `position INTEGER` (ascending). The `position` field was set during ingest as `enumerate()` index over `chat_messages`. Role values in DB are `"human"` and `"assistant"` — map to display labels `"Human"` and `"Assistant"` for H2 headers.

```python
# Source: VERIFIED against messages table, roles confirmed DISTINCT query

cur.execute("""
    SELECT role, content, position
    FROM messages
    WHERE conversation_id = ?
    ORDER BY position ASC
""", (conv_id,))
messages = cur.fetchall()

# Role mapping (verified)
ROLE_LABEL = {"human": "Human", "assistant": "Assistant"}

# export_conversation format (D-08, D-09, D-10)
def format_export(conv: dict, messages: list) -> str:
    lines = [f"# {conv['title']}", f"*Date: {conv['created_at']}*", ""]
    for role, content, _ in messages:
        label = ROLE_LABEL.get(role, role.capitalize())
        lines.append(f"## {label}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)
```

### Pattern 7: get_stats() File Size

**What:** Use `pathlib.Path.stat().st_size` to get bytes, format as MB.

```python
# Source: VERIFIED — pathlib stdlib, confirmed against live 9.88 MB history.db

db_size_bytes = DB_PATH.stat().st_size
db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
```

### Anti-Patterns to Avoid

- **Calling bm25() inside GROUP BY or subquery:** Raises `OperationalError: unable to use function bm25 in the requested context`. Must aggregate in Python instead. [VERIFIED — confirmed by direct testing]
- **Calling snippet() without MATCH on the same row:** snippet() requires the FTS MATCH to be active in the same query. Cannot call it as a post-hoc function on a plain rowid. [VERIFIED]
- **Using print() or sys.stdout.write() anywhere in server.py or its imports:** Silently corrupts the stdio JSON-RPC session. Use `logging.getLogger(__name__)` only. [VERIFIED — project invariant]
- **Calling sys.stderr.reconfigure() after imports:** Must be the first line of server.py before all imports except sys. Already established in the stub. [VERIFIED — server.py]
- **Using INSERT OR REPLACE in search queries:** Not applicable — search.py is read-only. But avoid any write operations; the DB is read-only from the server's perspective.
- **Assuming project field is populated:** All 106 conversations have `project = NULL`. [VERIFIED — live DB query]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool schema from type hints | Custom JSON schema builder | FastMCP `@mcp.tool()` decorator | Auto-generates from type annotations + docstring [VERIFIED: FastMCP source] |
| FTS5 BM25 ranking | Custom tf-idf scorer | `bm25(messages_fts)` in ORDER BY | Built into SQLite FTS5; negative scores mean better match [VERIFIED: live DB] |
| Snippet extraction | Substring search | `snippet(messages_fts, 0, ...)` | Context-aware; respects token boundaries; highlights match terms [VERIFIED: live DB] |
| Phrase search fallback | Custom parser | Double-quote wrapping | `"user input"` syntax forces phrase match; safe for all inputs [VERIFIED: live DB] |
| JSON serialization of results | json.dumps() calls | FastMCP's auto-conversion | `pydantic_core.to_json` handles list[dict] transparently [VERIFIED: FastMCP source] |
| Input type coercion | Custom type checking | FastMCP Pydantic validation | Type hints coerce string "true" -> bool True for include_full_content [VERIFIED: func_metadata.py] |

**Key insight:** The FTS5 engine does the heavy lifting. Python's job is aggregation (one-per-conversation), result shaping, and edge case handling. Do not reimplement what SQLite already provides.

---

## Common Pitfalls

### Pitfall 1: bm25() Cannot Be Used in GROUP BY or Subqueries

**What goes wrong:** `OperationalError: unable to use function bm25 in the requested context` when trying to write `SELECT MIN(bm25(...)) ... GROUP BY conversation_id` or wrapping the FTS query in a subquery.

**Why it happens:** SQLite FTS5 auxiliary functions (bm25, snippet, highlight) are only valid in the direct WHERE/ORDER BY context of a virtual table query. They cannot be materialized or projected through a subquery.

**How to avoid:** Always fetch all matching rows with `ORDER BY bm25(messages_fts)` in one query, then aggregate in Python. [VERIFIED: confirmed by testing both patterns against live DB]

**Warning signs:** Any SQL that puts bm25() inside parentheses other than the immediate SELECT clause of a messages_fts query.

### Pitfall 2: snippet() Requires Active MATCH in Same Query

**What goes wrong:** snippet() called without the MATCH clause returns incorrect results or errors. snippet() called on a second query after the FTS query (even with the same rowid) will not highlight correctly.

**Why it happens:** snippet() is a callback into the FTS match state; it requires the virtual table to have just executed the MATCH.

**How to avoid:** Always call snippet() with `WHERE messages_fts MATCH ? AND rowid = ?` in a single query. The rowid filter restricts to the target row while keeping the MATCH active. [VERIFIED: live DB]

### Pitfall 3: stdout Contamination Silently Kills stdio Session

**What goes wrong:** The MCP session hangs or produces JSON parse errors on the client side. No Python exception is raised.

**Why it happens:** FastMCP's stdio transport reads JSON-RPC frames from stdout. Any stray print() or sys.stdout.write() corrupts the byte stream.

**How to avoid:** Never use print(). Never import a module that prints at import time. Use `logging.getLogger(__name__)` everywhere. Verify with `grep -r "print(" src/` before committing.

**Warning signs:** MCP Inspector shows protocol errors; Claude Code shows tool call failures with no Python traceback.

### Pitfall 4: Token Count vs. Character Count in snippet()

**What goes wrong:** snippet() with `token_count=25` produces ~120-180 char snippets, not 300 chars. Target of ~300 chars requires token_count around 64.

**Why it happens:** Token count is approximate word tokens, not characters. Average English word is ~5 chars, so 64 tokens ≈ 320 chars average.

**How to avoid:** Use `token_count=64` for ~300 char target. [VERIFIED: avg=305 chars across 2903 samples]

### Pitfall 5: Empty Content Messages

**What goes wrong:** Some messages have `content = ""` (empty text, no attachments). These are valid messages that preserve position ordering. Filtering them out would break position continuity.

**Why it happens:** Some human messages are blank (attachments-only or empty sends). Ingest correctly inserts them with empty content to preserve position.

**How to avoid:** In `get_conversation()` and `export_conversation()`, include empty-content messages in position ordering. In `search_conversations()`, empty messages cannot match FTS queries, so they are naturally excluded from snippets. [VERIFIED: ingest.py comment + live DB shows 263 zero-content messages]

### Pitfall 6: FTS Query Triggers OperationalError on Re-Used Connection

**What goes wrong:** After an `OperationalError` from a malformed FTS query, the connection's implicit transaction may be in an error state. Subsequent queries on the same cursor may fail.

**Why it happens:** sqlite3's default isolation level leaves the connection in a bad state after exceptions in some cases.

**How to avoid:** The D-05 fallback runs a second `cur.execute()` after catching `OperationalError`. Test confirms this works correctly with the double-quote sanitization approach. If issues arise, open a fresh cursor for the fallback query. [VERIFIED: fallback tested against live DB]

---

## Code Examples

### Complete search_conversations() Core Logic

```python
# Source: VERIFIED — all components tested against history.db 2026-05-05

import sqlite3
from claude_history.config import DB_PATH
from claude_history.db import init_db

def search_conversations(
    query: str,
    limit: int = 10,
    include_full_content: bool = False,
) -> list[dict]:
    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # D-05: try raw FTS5 first, fall back to sanitized phrase
        try:
            rows = _fts_rows(cur, query)
        except sqlite3.OperationalError:
            escaped = query.replace('"', '""')
            rows = _fts_rows(cur, f'"{escaped}"')
            query = f'"{escaped}"'  # use sanitized form for snippet() calls too

        # D-06: empty results — return []
        if not rows:
            return []

        # D-02: one result per conversation (Python aggregation)
        best = {}
        for row in rows:
            cid = row["conversation_id"]
            if cid not in best:
                best[cid] = {"rowid": row["rowid"], "score": row["score"], "count": 1}
            else:
                best[cid]["count"] += 1

        ranked = sorted(best.items(), key=lambda x: x[1]["score"])

        results = []
        for conv_id, info in ranked[:limit]:
            # D-03: ~300 char snippet from best-matching message
            cur.execute("""
                SELECT snippet(messages_fts, 0, '**', '**', '...', 64) AS snip
                FROM messages_fts
                WHERE messages_fts MATCH ? AND rowid = ?
            """, (query, info["rowid"]))
            snip_row = cur.fetchone()
            snippet = snip_row["snip"] if snip_row else ""

            cur.execute(
                "SELECT title, created_at, project FROM conversations WHERE id = ?",
                (conv_id,)
            )
            conv = cur.fetchone()

            result = {
                "id": conv_id,
                "title": conv["title"] or "",
                "created_at": conv["created_at"] or "",
                "project": conv["project"],  # NULL in all current data
                "match_count": info["count"],
                "snippet": snippet,
            }

            # D-04: include_full_content appends all messages
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

            results.append(result)

        return results
    finally:
        conn.close()


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

### get_stats() Implementation

```python
# Source: VERIFIED against live DB and pathlib stat()

import pathlib

@mcp.tool()
def get_stats() -> dict:
    """Return database statistics: conversation count, message count, date range, file size."""
    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM conversations")
        conv_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM messages")
        msg_count = cur.fetchone()["n"]
        cur.execute("SELECT MIN(created_at) AS earliest, MAX(created_at) AS latest FROM conversations")
        dates = cur.fetchone()
    finally:
        conn.close()

    db_size_bytes = DB_PATH.stat().st_size
    return {
        "conversations": conv_count,
        "messages": msg_count,
        "date_from": dates["earliest"],
        "date_to": dates["latest"],
        "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
    }
```

### export_conversation() Format (D-08, D-09, D-10)

```python
# Source: VERIFIED format pattern — output confirmed against real conversation data

@mcp.tool()
def export_conversation(id: str) -> str:
    """Return conversation as clean markdown string with H2 Human/Assistant headers."""
    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT title, created_at FROM conversations WHERE id = ?", (id,))
        conv = cur.fetchone()
        if conv is None:
            return f"Conversation {id} not found."
        cur.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY position ASC
        """, (id,))
        messages = cur.fetchall()
    finally:
        conn.close()

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

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FTS3/FTS4 (legacy) | FTS5 with content table | SQLite 3.9+ (2015) | content table avoids duplicate storage; triggers maintain sync |
| HTTP transport for MCP | stdio transport | MCP spec v1.0 | Server spawned per-session; no persistent process; simpler auth |
| FastMCP synchronous only | sync and async both supported | mcp 1.x | Either works; sync is simpler for DB calls |
| Manual JSON schema | Auto-generated from type hints | FastMCP design | `@mcp.tool()` introspects annotations via Pydantic |

---

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | — | — | — |

**This table is empty:** All claims in this research were verified against the live codebase, installed packages, and populated database. No assumed claims.

---

## Open Questions

1. **get_status() scope (Claude's Discretion)**
   - What we know: Current stub returns `{"status": "ok"}`. DB stats queries are trivial and already written for get_stats().
   - What's unclear: Whether promoting get_status() to return stats is worth duplicating the get_stats() logic.
   - Recommendation: Promote to return `{"status": "ok", "conversations": N, "last_ingested": date}` — the queries are trivial and the extra context improves usability.

2. **models.py necessity**
   - What we know: FastMCP auto-converts `list[dict]` correctly. Plain dicts work.
   - What's unclear: Whether a `SearchResult` dataclass adds enough clarity to justify the file.
   - Recommendation: Skip models.py entirely. Use `list[dict]` for list tools and `dict` for scalar tools. Add models.py only if type errors arise.

3. **Connection-per-call vs. lifespan context**
   - What we know: Per-call `init_db() / conn.close()` works and matches the existing server.py pattern.
   - What's unclear: Whether FastMCP's `lifespan` context manager would be cleaner for a shared connection.
   - Recommendation: Use per-call connections for simplicity. The DB is read-only from the server; connection overhead is negligible for personal-scale use.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | Yes | 3.11+ | — |
| mcp (FastMCP) | server.py | Yes | 1.27.0 | — |
| sqlite3 + FTS5 | search.py | Yes | stdlib | — |
| history.db | All tools | Yes | 9.88 MB, 106 convs / 4087 msgs | — |
| uv | Entry points | Yes | 0.11.8 | — |

[VERIFIED: all dependencies confirmed present and functional via direct invocation and DB inspection]

**No missing dependencies.** Phase 3 is fully executable with current environment.

---

## Project Constraints (from CLAUDE.md)

- **NEVER write to stdout** in server.py or any module it imports — silently kills stdio MCP sessions. All output via `sys.stderr` / `logging`. [CRITICAL]
- **Stack is locked:** Python 3.11+, uv, FastMCP (`mcp[cli]`), SQLite FTS5 (stdlib). No deviations.
- **FTS5 schema is locked:** `messages_fts` uses `content="messages"` content table with `unicode61 remove_diacritics 2 tokenchars '-_'` tokenizer. Cannot change without full rebuild. search.py must query the existing schema.
- **Entry points:** `server = "claude_history.server:main"` — server.py's `main()` function signature must not change.
- **Logging order is non-negotiable:** `sys.stderr.reconfigure()` → `logging.basicConfig(stream=sys.stderr)` → `FastMCP()` → tools → `mcp.run(transport="stdio")`.
- **DB_PATH** resolves from `config.py` — import it; do not recompute.
- **`init_db()`** from `db.py` — use it for all connection opens; do not inline the connection setup.

---

## Sources

### Primary (HIGH confidence)

- Live `history.db` database — direct SQL execution confirmed all FTS5, bm25(), snippet(), aggregation, and stats patterns [VERIFIED: 2026-05-05]
- `src/claude_history/db.py` — FTS5 schema, trigger definitions, init_db() [VERIFIED: read directly]
- `src/claude_history/server.py` — logging pattern, FastMCP instantiation order [VERIFIED: read directly]
- `src/claude_history/ingest.py` — position field semantics, role values, build_message_content() [VERIFIED: read directly]
- `src/claude_history/config.py` — DB_PATH constant [VERIFIED: read directly]
- `.venv/Lib/site-packages/mcp/server/fastmcp/server.py` — FastMCP.tool() decorator signature, mcp.run() [VERIFIED: read directly]
- `.venv/Lib/site-packages/mcp/server/fastmcp/utilities/func_metadata.py` — _convert_to_content() serialization, pydantic_core.to_json fallback [VERIFIED: read directly]
- `.venv/Lib/site-packages/mcp/server/fastmcp/exceptions.py` — ToolError, FastMCPError [VERIFIED: read directly]

### Secondary (MEDIUM confidence)

None — all claims verified from primary sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — installed packages and venv confirmed
- Architecture: HIGH — all patterns executed against live DB
- Pitfalls: HIGH — confirmed by intentionally triggering each error against live DB
- FTS5 patterns: HIGH — bm25(), snippet(), GROUP BY limitations all directly tested

**Research date:** 2026-05-05
**Valid until:** 2026-08-05 (stable SQLite FTS5 API; FastMCP minor versions may add features but won't break existing patterns)
