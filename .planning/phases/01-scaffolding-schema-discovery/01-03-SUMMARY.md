---
phase: 01-scaffolding-schema-discovery
plan: 03
subsystem: infra
tags: [python, zipfile, schema, sqlite, markdown, schema-discovery]

# Dependency graph
requires:
  - phase: 01-01
    provides: uv package scaffold with schema-discovery entry point in pyproject.toml
provides:
  - src/claude_history/schema_discovery.py — standalone CLI that inspects Claude.ai export ZIP
  - .planning/SCHEMA.md — field reference document for Phase 2 ingest.py authoring
  - Project Association Gap documented: conversations.json has no project field
affects:
  - 02 (ingest.py field extraction driven by SCHEMA.md — must read this before planning)
  - 03 (search.py FTS field selection informed by message object fields in SCHEMA.md)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pattern: schema_discovery.py reads ZIP members in-memory via zipfile.ZipFile + json.load(zf.open())
    - Pattern: SCHEMA.md path computed as Path(__file__).parent.parent.parent / ".planning" / "SCHEMA.md"
    - Pattern: print() to stdout is acceptable in CLI tools (not server.py); stderr for diagnostics
    - Pattern: _infer_type() + _truncate() helpers produce clean Markdown field tables from any dict

key-files:
  created:
    - src/claude_history/schema_discovery.py
    - .planning/SCHEMA.md
  modified: []

key-decisions:
  - "ZIP contains 11 files: 1 conversations (106), 7 projects, 2 design_chats, 1 users — RESEARCH.md noted 6 projects; actual is 7"
  - "design_chats DOES have project field: {uuid, name} object — confirmed, documented in SCHEMA.md"
  - "Primary text field for FTS is message['text'] (direct string) — not content array — confirmed present in real data"
  - "Project association gap confirmed: conversations.json has no project field; Phase 2 must decide NULL vs. inference"
  - "Both timestamp formats confirmed: Z suffix in conversations, +00:00 in projects; datetime.fromisoformat() handles both"

patterns-established:
  - "Pattern: schema_discovery.py is standalone (no claude_history.config or server imports) — stays importable without MCP deps"
  - "Pattern: SCHEMA.md is the single source of truth for export field names; Phase 2 must read it before writing ingest.py"

requirements-completed: [INGEST-01]

# Metrics
duration: 1min
completed: 2026-05-04
---

# Phase 1 Plan 03: Schema Discovery Summary

**schema_discovery.py CLI inspects real Claude.ai export ZIP (11 files, 106 conversations) and writes .planning/SCHEMA.md with field tables, timestamp variants, and Project Association Gap warning**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-05-04T13:58:18Z
- **Completed:** 2026-05-04T13:59:26Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Wrote schema_discovery.py as a standalone CLI tool (no MCP/server imports) that reads ZIP via stdlib zipfile in-memory
- Ran the tool against the real export ZIP — confirmed 11 files, 106 conversations, 7 project files, 2 design chats
- Generated .planning/SCHEMA.md (4975 bytes) covering all 5 data categories with field types, truncated examples, timestamp docs, and Project Association Gap warning
- Confirmed zero database writes — script is strictly read-only; no history.db created

## Task Commits

Each task was committed atomically:

1. **Task 1: Write schema_discovery.py** - `390629f` (feat)
2. **Task 2: Run schema_discovery.py against the real export ZIP** - `848fff9` (feat)

**Plan metadata:** (committed below after SUMMARY creation)

## Files Created/Modified

- `src/claude_history/schema_discovery.py` - Standalone ZIP inspection CLI; entry point: main(); uses zipfile.ZipFile + json.load; writes .planning/SCHEMA.md; prints to stdout (D-03)
- `.planning/SCHEMA.md` - Field reference document for Phase 2 ingest.py authoring; 4975 bytes; all required sections present

## Decisions Made

- ZIP contained 7 project files (not 6 as noted in RESEARCH.md — the export grew by 1 project between research and execution). SCHEMA.md reflects the actual count.
- design_chats fully documented: uuid, title, project (object: uuid+name), created_at, updated_at, messages. The `project` field is confirmed present, which enables Phase 2 to make an informed decision about project association.
- Primary text field confirmed as `message["text"]` — direct string, always present. The `content` array is present but `text` is the reliable FTS target.

## Project-Association Gap Text (verbatim from SCHEMA.md)

```
**WARNING for Phase 2:** `conversations.json` entries do NOT contain a `project` field.
There is no direct way to associate a conversation with a project from conversations.json alone.

- `projects/UUID.json` contains project metadata but no list of conversation UUIDs
- `design_chats/UUID.json` DOES contain a `project` field (object with uuid and name)
- Regular conversations in conversations.json are NOT linked to projects in this export format

**Phase 2 decision required:** Either (a) skip project association for conversations and store NULL,
or (b) attempt to infer project association from design_chats. Document the chosen approach in Phase 2 planning.
```

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written.

---

**Total deviations:** 0
**Impact on plan:** N/A

## Issues Encountered

- RESEARCH.md noted 6 project files; actual count is 7. No fix needed — the script discovers them dynamically. SCHEMA.md reflects the actual count (7 projects). This is an expected discrepancy as export data can change between research and execution.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 2 (ingest.py) is fully unblocked: SCHEMA.md provides all field names, types, and structural quirks needed to write ingest.py without re-opening the ZIP
- Phase 2 planner must decide on project association strategy (NULL vs. inference from design_chats)
- Phase 2 FTS schema can use `message["text"]` as the primary FTS target (confirmed present)
- design_chats have a different message schema — Phase 2 must decide whether to ingest them separately or skip

---
*Phase: 01-scaffolding-schema-discovery*
*Completed: 2026-05-04*

## Self-Check: PASSED

- FOUND: src/claude_history/schema_discovery.py
- FOUND: .planning/SCHEMA.md
- FOUND: .planning/phases/01-scaffolding-schema-discovery/01-03-SUMMARY.md
- FOUND commit: 390629f (Task 1 — schema_discovery.py)
- FOUND commit: 848fff9 (Task 2 — SCHEMA.md)
