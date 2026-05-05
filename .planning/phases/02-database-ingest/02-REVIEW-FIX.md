---
phase: 02-database-ingest
fixed_at: 2026-05-05T00:00:00Z
review_path: .planning/phases/02-database-ingest/02-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-05-05T00:00:00Z
**Source review:** .planning/phases/02-database-ingest/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (3 Critical + 6 Warning; Info excluded by fix_scope=critical_warning)
- Fixed: 9
- Skipped: 0

## Fixed Issues

### WR-05: Foreign key constraint on messages.conversation_id never enforced

**Files modified:** `src/claude_history/db.py`
**Commit:** b8f2394
**Applied fix:** Added `conn.execute("PRAGMA foreign_keys = ON")` immediately after `PRAGMA journal_mode=WAL` in `init_db`. SQLite ignores REFERENCES constraints unless this PRAGMA is set per-connection; the constraint on `messages.conversation_id` is now enforced at runtime.

---

### WR-03: normalize_ts raises ValueError on malformed timestamps

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 647917f
**Applied fix:** Wrapped `datetime.fromisoformat(ts)` in `try/except ValueError`. Malformed timestamps (e.g. `"unknown"`, `"0000-00-00"`) now log a warning and return the raw string rather than propagating an uncaught exception that aborts the entire ingest run.

---

### CR-02: Unguarded KeyError on conv["uuid"] and msg["uuid"]

**Files modified:** `src/claude_history/ingest.py`
**Commit:** ba73502
**Applied fix:** Replaced `conv["uuid"]` with `conv.get("uuid")` guarded by a not-falsy check that logs a warning, increments `skipped_convs`, and continues. Replaced `msg["uuid"]` with `msg.get("uuid")` guarded by a not-falsy check that logs a warning and continues to the next message. The resolved `msg_uuid` local is used for the INSERT rather than re-reading the dict key.

---

### WR-01: new_convs counter incremented before confirming INSERT succeeded

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 204dc3b
**Applied fix:** Replaced unconditional `new_convs += 1` with `if cur.rowcount: new_convs += 1 else: skipped_convs += 1`. When `INSERT OR IGNORE` silently skips a race-condition duplicate, `rowcount` is 0 and the conversation is counted as skipped rather than new.

---

### WR-02: new_msgs counter incremented unconditionally

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 7e25411
**Applied fix:** Replaced unconditional `new_msgs += 1` with `if cur.rowcount: new_msgs += 1`. Consistent with the WR-01 fix; message counts now accurately reflect rows actually inserted by `INSERT OR IGNORE`.

---

### WR-04: zf.open("conversations.json") raises KeyError with no user-friendly error

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 51976e3
**Applied fix:** Added a `namelist()` check before `zf.open()`. If `conversations.json` is absent, logs an actionable error (`"Is this a Claude.ai export ZIP?"`) and calls `sys.exit(1)` rather than raising an unhandled `KeyError` traceback.

---

### WR-06: json.load on conversations.json raises JSONDecodeError with no handling

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 38662f9
**Applied fix:** Wrapped `json.load(f)` in `try/except json.JSONDecodeError`. A corrupted or truncated `conversations.json` now logs a clear error message and calls `sys.exit(1)` instead of surfacing a raw traceback with no guidance.

---

### CR-01: Connection leak on exception — ingest_zip never closes conn on error path

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 714f5c5
**Applied fix:** Wrapped the entire `ingest_zip` body after `conn = init_db(db_path)` in `try/finally: conn.close()`. The `conn.commit()` call remains inside the `try` block; `conn.close()` in `finally` fires on any exception (KeyError, ValueError, SQLite error, SystemExit) as well as on the happy path. All loop logic was indented one level to sit inside the `try` block.

---

### CR-03: Log summary format string passes wrong argument — skipped_convs duplicated

**Files modified:** `src/claude_history/ingest.py`
**Commit:** 72390f8
**Applied fix:** Replaced the three-arg format string `"%d new, %d already indexed — skipping %d"` (which passed `skipped_convs` twice) with a clear two-arg message: `"%d new conversations, %d already indexed (skipped)"` receiving `(new_convs, skipped_convs)`.

---

_Fixed: 2026-05-05T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
