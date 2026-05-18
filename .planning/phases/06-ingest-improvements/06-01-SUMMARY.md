---
phase: 06-ingest-improvements
plan: 01
subsystem: database
tags: [sqlite, fts5, ingest, incremental, insert-or-ignore]

# Dependency graph
requires:
  - phase: 02-database-ingest
    provides: "ingest_zip() function and INSERT OR IGNORE message pattern"
provides:
  - "Incremental message-append ingest: re-running on an updated ZIP appends new messages without duplicating existing ones"
  - "message_count and updated_at kept accurate via per-conversation delta tracking"
  - "D-06 three-count log output: new conversations / existing updated / unchanged"
affects: [server, get_stats tool, future attachment ingestion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "conv_new_msgs per-conversation delta via cur.rowcount after INSERT OR IGNORE"
    - "total_new_msgs scoped to existing-conversation updates only (not new conversation inserts)"
    - "is_new_conv local variable to branch post-loop UPDATE logic"

key-files:
  created: []
  modified:
    - src/claude_history/ingest.py

key-decisions:
  - "Scan all conversations regardless of UUID existence — INSERT OR IGNORE on messages handles dedup (D-01)"
  - "total_new_msgs accumulates only for pre-existing conversations so log line 'M updated (K msgs)' is consistent"
  - "UPDATE message_count = message_count + ? guards on conv_new_msgs > 0 and not is_new_conv to avoid touching new-conversation rows"

patterns-established:
  - "Rule 1 deviation applied: total_new_msgs initially accumulated for all conversations (including new), producing misleading '0 updated (2 new messages)' log — fixed by moving accumulation into the is_new_conv==False UPDATE branch"

requirements-completed: [INGEST-01]

# Metrics
duration: 2min
completed: 2026-05-18
---

# Phase 6 Plan 01: Ingest Improvements Summary

**Incremental message-append ingest via per-conversation INSERT OR IGNORE delta tracking — new messages appended to existing conversations without duplication, message_count updated atomically**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-18T06:58:54Z
- **Completed:** 2026-05-18T07:01:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Removed early-exit UUID check (`SELECT 1 FROM conversations WHERE id = ?` + `continue`) that silently dropped all messages for pre-existing conversations
- Added `conv_new_msgs` per-conversation counter and `is_new_conv` flag; after each message loop, UPDATE `message_count = message_count + ?` and `updated_at` when `conv_new_msgs > 0 and not is_new_conv`
- Replaced two-line final log with D-06 three-count format: "N new conversations / M existing conversations updated (K new messages) / P conversations unchanged"
- Smoke test verified end-to-end: after first ingest message_count==2, after incremental second ingest message_count==3, no duplicates for msg-1 or msg-2, msg-3 present

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove early-exit skip and restructure conversation loop for incremental append** - `f431221` (fix)
2. **Task 2: Smoke-test incremental ingest with a live DB round-trip** - `50fce96` (fix — Rule 1 deviation)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/claude_history/ingest.py` - Removed early-exit UUID check, added is_new_conv/conv_new_msgs/total_new_msgs/updated_convs/unchanged_convs tracking, added UPDATE conversations block, replaced log.info calls with D-06 three-count output

## Decisions Made

- Kept `skipped_convs` as internal counter for the race-condition INSERT OR IGNORE no-op path on conversations — not logged (effectively always 0 in practice per context notes)
- `total_new_msgs` scoped to the `updated_convs` branch only — ensures the log line "M updated (K new messages)" is internally consistent (K is 0 when M is 0)
- Combined `updated_at` refresh with `message_count` UPDATE in a single SQL statement (D-05 + D-03 in one query)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] total_new_msgs initial placement produced misleading log output**
- **Found during:** Task 2 (smoke-test run)
- **Issue:** `total_new_msgs += 1` was inside the per-message `if cur.rowcount:` block, accumulating for ALL new message inserts including those for newly-inserted conversations. First ingest logged "0 existing conversations updated (2 new messages)" — contradictory (0 updated, but 2 new messages reported).
- **Fix:** Moved `total_new_msgs += conv_new_msgs` into the post-loop `if conv_new_msgs > 0 and not is_new_conv:` branch so it only counts messages appended to pre-existing conversations.
- **Files modified:** `src/claude_history/ingest.py`
- **Verification:** Smoke test re-run: first ingest logs "0 updated (0 new messages)", second ingest logs "1 updated (1 new messages)" — consistent.
- **Committed in:** `50fce96` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - correctness bug in log output)
**Impact on plan:** Fix was essential for correct reporting. No scope creep. All acceptance criteria still pass.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- INGEST-01 complete. Incremental ingest is now the correct default behavior.
- `get_stats` tool (server.py) reads `message_count` from the conversations table — counts are now accurate after incremental runs.
- No blockers for future phases. ATTACH-01 (PDF attachment indexing) deferred to Phase 7 if needed.

---
*Phase: 06-ingest-improvements*
*Completed: 2026-05-18*
