---
phase: "04"
plan: "01"
subsystem: integration-readme
tags: [readme, mcp-registration, user-scope, documentation]
dependency_graph:
  requires: [03-02]
  provides: [SETUP-03, SETUP-05]
  affects: [~/.claude.json, README.md]
tech_stack:
  added: []
  patterns: [uv --directory for user-scope portable registration]
key_files:
  created:
    - README.md
  modified:
    - .gitignore
decisions:
  - "User-scope registration uses `uv --directory <abs-path> run server` so it works from any Claude Code session directory"
  - "Project-scope .mcp.json kept on disk (gitignored) for convenience when working inside project dir"
  - "Added .claude/ to .gitignore (Claude Code local settings, machine-specific)"
metrics:
  duration: "~8min"
  completed: "2026-05-06"
  tasks_completed: 2
  files_changed: 3
---

# Phase 4 Plan 1: Integration + README Summary

**One-liner:** User-scope MCP registration via `uv --directory` flag and full README covering install, ingest workflow, and all 6 tool signatures.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | User-scope MCP registration + .gitignore .claude/ | 3150a70 | .gitignore |
| 2 | README.md with installation, ingest workflow, tool reference | 87d992e | README.md |

## Verification

- `~/.claude.json` contains `mcpServers.claude-history` with `uv --directory <abs-path> run server`
- `search_conversations("sqlite")` returns 3 ranked results with snippets and match_count
- `get_stats()` confirms 106 conversations, 4087 messages in history.db
- README accurately documents all 6 tools, installation steps, and registration command

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added .claude/ to .gitignore**
- **Found during:** Task 1
- **Issue:** Claude Code creates a `.claude/` directory with local settings (`settings.local.json`, `worktrees/`) that was untracked and not gitignored
- **Fix:** Added `.claude/` to `.gitignore`
- **Files modified:** `.gitignore`
- **Commit:** 3150a70

## Known Stubs

None — all tools are wired to real SQLite data; README reflects verified counts from real export.

## Threat Flags

None — no new network endpoints, no new auth paths. User-scope registration only writes to `~/.claude.json`.

## Self-Check: PASSED

- README.md exists: FOUND
- .gitignore updated: FOUND
- Task 1 commit 3150a70: FOUND in git log
- Task 2 commit 87d992e: FOUND in git log
- user-scope registration in ~/.claude.json: VERIFIED
- search_conversations against real DB: VERIFIED (3 results for "sqlite")
- 106 conversations in DB: VERIFIED
