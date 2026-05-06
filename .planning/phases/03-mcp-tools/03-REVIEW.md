---
phase: 03-mcp-tools
reviewed: 2026-05-06T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/claude_history/search.py
  - src/claude_history/server.py
findings:
  critical: 1
  warning: 6
  info: 3
  total: 10
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-06
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Both `search.py` and `server.py` are structurally sound and follow the project's
stdio contamination rule correctly. The FTS5 query plumbing is logically correct.
However, six issues require attention before this code is considered shippable:
one critical crash path (`get_stats` on missing DB), two silent API contract
violations (ignored `project_filter`, inconsistent return types between tools),
and several robustness gaps around null content and unhandled second-level
OperationalError.

---

## Critical Issues

### CR-01: `get_stats` crashes with unhandled `FileNotFoundError` when DB is absent

**File:** `src/claude_history/server.py:144`

**Issue:** `DB_PATH.stat().st_size` is called outside the `try/finally` block,
after `conn.close()`. If the database file does not exist at call time,
`Path.stat()` raises `FileNotFoundError` which propagates unhandled through
FastMCP, producing an unstructured server error rather than a useful tool
response. This is a realistic path: a user could call `get_stats` before running
`ingest`.

`init_db` creates the file on connect, so the DB will exist after `conn.close()`
in the happy path — but only if `init_db` succeeds. If `init_db` raises (e.g.
permission denied, disk full), the `finally` closes a potentially-None connection
and then `DB_PATH.stat()` is reached on a nonexistent file.

**Fix:**
```python
    finally:
        conn.close()

    try:
        db_size_bytes = DB_PATH.stat().st_size
    except FileNotFoundError:
        db_size_bytes = 0

    return {
        "conversations": conv_count,
        "messages": msg_count,
        "date_from": dates["earliest"],
        "date_to": dates["latest"],
        "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
    }
```

---

## Warnings

### WR-01: FTS5 fallback can still raise `OperationalError` — error escapes to caller

**File:** `src/claude_history/search.py:55-60`

**Issue:** The fallback on line 58-60 wraps the query in FTS5 double-quote phrase
syntax. This handles syntax errors (unclosed parentheses, stray operators), but a
query consisting entirely of FTS5-illegal characters (e.g. a lone `^`) can still
fail the phrase query and raise a second `OperationalError`. That exception is not
caught and propagates out of `search_conversations`, breaking the D-06 contract
("never raises").

```python
        try:
            rows = _fts_rows(cur, active_query)
        except sqlite3.OperationalError:
            escaped = query.replace('"', '""')
            active_query = f'"{escaped}"'
            rows = _fts_rows(cur, active_query)  # <-- can still raise
```

**Fix:** Wrap the fallback call in its own try/except and return `[]` on second
failure:
```python
        except sqlite3.OperationalError:
            escaped = query.replace('"', '""')
            active_query = f'"{escaped}"'
            try:
                rows = _fts_rows(cur, active_query)
            except sqlite3.OperationalError:
                log.warning("FTS5 query failed after sanitization: %r", query)
                return []
            log.debug("FTS5 sanitization fallback used for query: %r", query)
```

---

### WR-02: `project_filter` is silently ignored — callers receive unfiltered results

**File:** `src/claude_history/server.py:38-59`

**Issue:** `search_conversations` accepts `project_filter: str | None = None` in
its MCP tool signature (making it part of the public API schema) but never applies
it. A caller passing `project_filter="MyProject"` receives all results with no
filtering — no warning, no error, no indication the parameter was ignored. This is
a silent API contract violation.

The comment on line 57 acknowledges this: "project_filter kept in signature for
schema compatibility; not applied". The docstring does not disclose this.

**Fix (option A — disclose in docstring):**
```python
        Args:
            project_filter: Accepted for schema compatibility but currently has
                no effect — all project fields are NULL in the export format.
                Use list_projects() for context.
```

**Fix (option B — remove parameter until data supports it):**
Remove `project_filter` from the signature entirely and add it back when project
data becomes available. Removing an undocumented-as-working parameter is less
harmful than silently lying about filtering.

---

### WR-03: Inconsistent return type between `get_conversation` and `export_conversation` on not-found

**File:** `src/claude_history/server.py:81` and `src/claude_history/server.py:180`

**Issue:** `get_conversation` returns `{"error": "..."}` (a dict) when the ID is
not found. `export_conversation` returns a bare error string `f"Conversation
{id!r} not found."`. A caller handling both tools cannot use a consistent
not-found detection strategy.

**Fix:** Make `export_conversation` consistent with `get_conversation`:
```python
            if conv is None:
                return f"## Error\n\nConversation {id!r} not found."
```
Or, since `export_conversation` returns `str`, document that the error case
returns a string beginning with `"Error:"` and update `get_conversation` to also
return a string. Pick one convention and apply it uniformly.

---

### WR-04: `msg["content"]` may be `None` — silent data corruption in `search.py` and crash in `server.py`

**File:** `src/claude_history/search.py:112-115` and `src/claude_history/server.py:200-203`

**Issue:** The `messages` schema declares `content TEXT NOT NULL DEFAULT ''`, but
this constraint only prevents new nulls — it does not guarantee existing rows are
non-null if the schema was applied after data existed, or if the ingest path
bypassed the constraint (e.g. via `executemany` with explicit `None`).

In `search.py` line 113, `f"... {r['content']}"` with `r['content'] = None`
silently produces the string `"... None"` — data corruption with no error.

In `server.py` line 203, `lines.append(msg["content"])` with
`msg["content"] = None` raises `TypeError: expected str instance, NoneType found`
when `"\n".join(lines)` is called at line 206. This crashes `export_conversation`
with an unhandled exception.

**Fix:** Coerce `None` content to empty string at both sites:
```python
# search.py line 113
f"{'Human' if r['role'] == 'human' else 'Assistant'}: {r['content'] or ''}"

# server.py line 203
lines.append(msg["content"] or "")
```

---

### WR-05: `get_status` returns `"status": "ok"` unconditionally — masks database errors

**File:** `src/claude_history/server.py:210-231`

**Issue:** `get_status` is described as a health check ("Return server health and
database statistics"). If the database is inaccessible, `init_db` raises an
exception that propagates out of the tool — FastMCP returns a server error, not
`{"status": "error", ...}`. A caller using `get_status` to verify the server is
healthy before running searches gets no useful signal when the DB is broken.

**Fix:**
```python
    @mcp.tool()
    def get_status() -> dict:
        """..."""
        try:
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
        except Exception as exc:
            return {"status": "error", "error": str(exc), "conversations": 0, "last_ingested": None}

        return {"status": "ok", "conversations": conv_count, "last_ingested": latest}
```

---

### WR-06: `bm25()` called twice per row in `_fts_rows` — alias not used in ORDER BY

**File:** `src/claude_history/search.py:12-18`

**Issue:** The SQL query aliases `bm25(messages_fts)` as `score` in the SELECT
list but then re-calls `bm25(messages_fts)` in `ORDER BY`. SQLite does not fold
the alias — the expression is evaluated twice per row. This is a correctness-
adjacent issue: while the two evaluations produce identical results in practice
(BM25 is deterministic per row for a given query), relying on two independent
evaluations creates a semantic gap. More concretely, if the ORDER BY expression
differed from the SELECT expression (e.g. due to copy-paste drift), ranking and
the returned score would silently diverge.

**Fix:**
```sql
SELECT m.conversation_id, m.rowid, bm25(messages_fts) AS score
FROM messages_fts
JOIN messages m ON messages_fts.rowid = m.rowid
WHERE messages_fts MATCH ?
ORDER BY score   -- reference alias, not re-evaluate
```

Note: SQLite supports referencing column aliases in ORDER BY (unlike WHERE/HAVING),
so this change is valid.

---

## Info

### IN-01: `id` parameter shadows Python builtin in two tool definitions

**File:** `src/claude_history/server.py:63` and `src/claude_history/server.py:155`

**Issue:** Both `get_conversation(id: str)` and `export_conversation(id: str)` use
`id` as a parameter name, shadowing the Python builtin `id()`. Not a runtime bug
since neither function calls `id()`, but it is a linting violation and a naming
convention issue.

**Fix:** Rename to `conversation_id: str`. Update FastMCP tool schema accordingly
(the MCP tool's JSON schema parameter name will change — verify callers).

---

### IN-02: `init_db` called on every tool invocation — DDL on every read

**File:** `src/claude_history/server.py:71, 129, 171, 218`

**Issue:** Every tool call invokes `init_db(DB_PATH)`, which runs the full
`executescript` block (CREATE TABLE IF NOT EXISTS × 3, CREATE VIRTUAL TABLE IF
NOT EXISTS × 1, CREATE TRIGGER IF NOT EXISTS × 3) plus `PRAGMA journal_mode=WAL`
on every invocation. `executescript` also issues an implicit `COMMIT` before
execution. This is architecturally incorrect: initialization belongs in `main()`
once at startup.

**Fix:** Call `init_db` once in `main()` and store the resulting `conn`, or
restructure tools to use a module-level connection. For the current stdio
single-session model, a single connection opened at startup and closed at exit is
the correct pattern.

---

### IN-03: `sys.stderr.reconfigure` at module scope — breaks import in test environments

**File:** `src/claude_history/server.py:4`

**Issue:** `sys.stderr.reconfigure(encoding="utf-8")` executes at module import
time. In test environments where `sys.stderr` is replaced with a `StringIO` or
similar object that does not implement `reconfigure`, this raises `AttributeError`
on import, preventing the module from loading at all. Guard it:

```python
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
```

---

_Reviewed: 2026-05-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
