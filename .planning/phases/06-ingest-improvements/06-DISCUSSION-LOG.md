# Phase 6: Ingest Improvements - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-17
**Phase:** 6-ingest-improvements
**Areas discussed:** Scope (ATTACH-01 removal), Incremental scan strategy

---

## Scope Decision — ATTACH-01 Removal

User questioned whether PDF attachment indexing (ATTACH-01) was actually valuable for the project or had "snuck in as a big deal." Key exchange:

**User:** "what's the focus on pdf about? i feel like we're really focused on it for some reason... Is it a pathfinder for general artifact import or did it sneak in as a big deal when we don't really need it?"

**Claude's assessment:** ATTACH-01 snuck in. It requires a new dependency, binary ZIP extraction, and failure handling for a narrow use case (searching PDF content rather than conversation text). FTS on conversation text already surfaces the right conversations. Not a pathfinder for anything.

**Decision:** ATTACH-01 explicitly removed from Phase 6. Phase 6 is INGEST-01 only.

---

## Incremental Scan Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Scan all conversations | Every conversation processed; INSERT OR IGNORE deduplicates per message | ✓ |
| Only scan changed conversations | Compare `updated_at` to skip unchanged; faster but has silent-drop failure mode | |
| You decide | Defer to Claude | |

**User's choice:** Scan all conversations (recommended option)
**Notes:** At personal-history scale (~100 conversations), speed is not a real concern. Correctness guarantee (no silent drops) matters more.

---

## Claude's Discretion

- `message_count` update strategy: delta tracking via `cur.rowcount` per message, then `UPDATE conversations SET message_count = message_count + N` — no extra COUNT query
- `updated_at` refresh: update `conversations.updated_at` from export value when new messages found
- Logging format: report new conversations, updated conversations, and unchanged conversations separately
- Loop structure and variable naming inside `ingest_zip`

## Deferred Ideas

- **ATTACH-01 — PDF attachment indexing**: Removed from Phase 6. Defer to Phase 7 or later if the concrete need arises (user uploads PDFs to Claude and needs to search by PDF content rather than conversation text).
