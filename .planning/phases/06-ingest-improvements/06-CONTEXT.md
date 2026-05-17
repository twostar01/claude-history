# Phase 6: Ingest Improvements - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the incremental ingest bug in `ingest.py`: conversations already in the DB are currently skipped entirely, silently dropping new messages from continued conversations. After this phase, re-running ingest on an updated export will append any new messages to existing conversations without duplicating existing ones.

**Scope: INGEST-01 only.** ATTACH-01 (PDF attachment indexing) was explicitly removed from this phase — see Deferred Ideas.

One file changes: `src/claude_history/ingest.py`

</domain>

<decisions>
## Implementation Decisions

### Incremental Scan Strategy (INGEST-01)
- **D-01:** **Scan all conversations in the ZIP** — every conversation has its messages processed, regardless of whether the conversation UUID already exists in the DB. INSERT OR IGNORE on individual messages handles deduplication: existing messages are silently skipped, new ones are inserted. This is the correct default at personal-history scale (~100 conversations).
- **D-02:** Do NOT use `updated_at` as a skip signal — that optimization adds complexity and has a silent-drop failure mode (if the export's `updated_at` is unchanged despite new messages, those messages would be permanently missed). Scan all, let SQL dedup.

### message_count Update
- **D-03:** `message_count` on the conversations table **must** be updated after new messages are inserted. Track new-message count per conversation during iteration (delta from `cur.rowcount` after each INSERT OR IGNORE). After processing all messages for a conversation, if `new_msgs > 0`: `UPDATE conversations SET message_count = message_count + ? WHERE id = ?`.
- **D-04:** This is consistent with the existing INSERT OR IGNORE pattern — no COUNT(*) query needed.

### updated_at Refresh
- **D-05:** When new messages are found for an existing conversation (`new_msgs > 0`), also update `conversations.updated_at` from the export value. This keeps the DB in sync with reality.

### Reporting
- **D-06:** Log counts separately: "N new conversations", "M existing conversations updated (K new messages)", "P conversations unchanged". This makes re-ingest output informative without being verbose.

### Claude's Discretion
- Exact variable names and loop structure inside `ingest_zip` — follow existing style
- Whether to track `updated_convs` count in the same loop or a separate pass
- Whether `D-05` (`updated_at` refresh) uses a combined UPDATE or a separate statement from `D-03`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Core File (being modified)
- `src/claude_history/ingest.py` — `ingest_zip()` function; current skip logic at the UUID check (`if cur.fetchone(): continue`); `build_message_content()`; INSERT OR IGNORE pattern; logging style

### Schema (read-only — no schema changes)
- `src/claude_history/db.py` — `conversations` table (id, message_count, updated_at); `messages` table (id UNIQUE, conversation_id, INSERT OR IGNORE constraint); FTS5 triggers fire on INSERT automatically — no manual FTS update needed

### Planning Artifacts
- `.planning/REQUIREMENTS.md` — INGEST-01 with acceptance criteria (incremental append, no duplication, message_count updated, INSERT OR IGNORE throughout)
- `.planning/ROADMAP.md` — Phase 6 goal and 4 success criteria
- `.planning/PROJECT.md` — Constraints (stdout rule, INSERT OR IGNORE, no INSERT OR REPLACE)
- `CLAUDE.md` — Module structure, stderr-only logging rule

### Prior Phase Context
- `.planning/phases/05-search-filters-export/05-CONTEXT.md` — established patterns (INSERT OR IGNORE, conn=None guard, stderr logging)

</canonical_refs>

<code_context>
## Existing Code Insights

### The Bug (ingest.py:120-125)
```python
cur.execute("SELECT 1 FROM conversations WHERE id = ?", (uuid,))
if cur.fetchone():
    skipped_convs += 1
    continue   # ← drops ALL messages for this conversation
```
The fix removes this early-exit. Instead, the conversation INSERT OR IGNORE runs (no-op if exists), then all messages are iterated normally. The per-message INSERT OR IGNORE handles dedup.

### Reusable Assets
- `build_message_content(msg)` — unchanged; already handles text + attachment content
- `normalize_ts(ts)` — unchanged; used for all timestamp fields
- `INSERT OR IGNORE INTO messages` — already in place; works correctly for dedup
- `cur.rowcount` — already used to detect whether INSERT OR IGNORE fired; reuse for delta tracking

### Established Patterns
- **INSERT OR IGNORE on messages** — already correct; rowcount==0 when ignored (existing), rowcount==1 when inserted (new)
- **INSERT OR IGNORE on conversations** — keep as-is; no-op when UUID exists, which is fine — we just don't `continue` after it
- **stderr-only logging** — `log.info(...)` only; no `print()`
- **Commit once at the end** — `conn.commit()` after the full loop, not per-conversation

### Integration Points
- FTS5 triggers (`messages_ai`) fire automatically on INSERT — no manual `messages_fts` update needed
- `message_count` is not used by any search path (not in FTS, not in BM25 ranking) — update is for display accuracy only (used by `get_stats` tool)

</code_context>

<specifics>
## Specific Ideas

- The fix is surgical: remove the `continue` after the UUID check, add per-conversation delta tracking, add an UPDATE for `message_count` and `updated_at` when new messages were found. Estimated diff: ~15 lines changed.

</specifics>

<deferred>
## Deferred Ideas

- **ATTACH-01 — PDF attachment indexing**: Explicitly removed from Phase 6 scope. Requires new dependency (pypdf or pdfplumber), binary ZIP extraction, and failure handling for corrupted/encrypted PDFs. The value is narrow: only helps when PDF content (not conversation text) is the search target. Defer to Phase 7 or later if the need arises concretely.

</deferred>

---

*Phase: 6-Ingest Improvements*
*Context gathered: 2026-05-17*
