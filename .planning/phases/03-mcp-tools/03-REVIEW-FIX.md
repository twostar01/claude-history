---
phase: 03-mcp-tools
fixed_at: 2026-05-06T00:00:00Z
review_path: .planning/phases/03-mcp-tools/03-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-05-06
**Source review:** .planning/phases/03-mcp-tools/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: `get_stats` crashes with unhandled `FileNotFoundError` when DB is absent

**Files modified:** `src/claude_history/server.py`
**Commit:** d10ab22
**Applied fix:** Wrapped `DB_PATH.stat().st_size` in a `try/except FileNotFoundError` block after the `finally: conn.close()` section, returning `db_size_bytes = 0` when the file does not exist. This ensures `get_stats` returns a valid response even before `ingest` has been run.

---

### WR-01: FTS5 fallback can still raise `OperationalError` — error escapes to caller

**Files modified:** `src/claude_history/search.py`
**Commit:** 19a3217
**Applied fix:** Wrapped the fallback `_fts_rows(cur, active_query)` call in its own `try/except sqlite3.OperationalError` block. On second failure, logs a warning and returns `[]`, preserving the D-06 never-raises contract for queries consisting entirely of FTS5-illegal characters.

---

### WR-02: `project_filter` is silently ignored — callers receive unfiltered results

**Files modified:** `src/claude_history/server.py`
**Commit:** 6746fd0
**Applied fix:** Added an explicit `Args:` section to the `search_conversations` docstring documenting that `project_filter` is accepted for schema compatibility but has no effect because all project fields are NULL in the export format.

---

### WR-03: Inconsistent return type between `get_conversation` and `export_conversation` on not-found

**Files modified:** `src/claude_history/server.py`
**Commit:** 72758d7
**Applied fix:** Changed the bare `f"Conversation {id!r} not found."` string in `export_conversation` to `f"## Error\n\nConversation {id!r} not found."` — a markdown-formatted error string with a consistent `## Error` prefix that callers can detect reliably.

---

### WR-04: `msg["content"]` may be `None` — silent data corruption in `search.py` and crash in `server.py`

**Files modified:** `src/claude_history/search.py`, `src/claude_history/server.py`
**Commit:** 4ad48b3
**Applied fix:** Applied `r['content'] or ''` in `search.py` line 117 (full_content join) and `msg["content"] or ""` in `server.py` line 215 (`lines.append`) at both sites cited by the reviewer. Prevents the `"... None"` string corruption and the `TypeError` from `"\n".join` on a `None` value.

---

### WR-05: `get_status` returns `"status": "ok"` unconditionally — masks database errors

**Files modified:** `src/claude_history/server.py`
**Commit:** 76df341
**Applied fix:** Wrapped the entire `init_db` + query block in a `try/except Exception as exc` and return `{"status": "error", "error": str(exc), "conversations": 0, "last_ingested": None}` on failure. Updated the docstring to document this behavior. The inner `try/finally` for `conn.close()` is preserved inside the outer try block.

---

### WR-06: `bm25()` called twice per row in `_fts_rows` — alias not used in ORDER BY

**Files modified:** `src/claude_history/search.py`
**Commit:** ba11a0b
**Applied fix:** Changed `ORDER BY bm25(messages_fts)` to `ORDER BY score` in `_fts_rows`, referencing the alias already defined in the SELECT list. SQLite supports column aliases in ORDER BY (unlike WHERE/HAVING), so this is valid and eliminates the double evaluation.

---

_Fixed: 2026-05-06_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
