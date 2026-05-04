---
phase: 01-scaffolding-schema-discovery
plan: 02
subsystem: infra
tags: [fastmcp, mcp, stdio, server, python, logging, mcp-json]

# Dependency graph
requires:
  - phase: 01-scaffolding-schema-discovery
    plan: 01
    provides: pyproject.toml with [project.scripts] server entry point, mcp[cli] 1.27.0 installed
provides:
  - src/claude_history/server.py — FastMCP stdio server with get_status tool, stderr-only logging
  - .mcp.json — project-scope MCP registration (uv --directory absolute path)
  - claude-history registered in Claude Code, shows Connected in claude mcp list
affects:
  - 01-03 (no direct dependency but completes Phase 1 server infrastructure)
  - phase-03 (all Phase 3 tools build on this server.py structure)
  - phase-04 (user-scope registration replaces project-scope .mcp.json)

# Tech tracking
tech-stack:
  added:
    - FastMCP stdio server pattern (server.py as entry point)
    - claude mcp add --scope project (.mcp.json registration)
  patterns:
    - stderr-only logging: sys.stderr.reconfigure(encoding=utf-8) + logging.basicConfig(stream=sys.stderr) as first two actions in main()
    - FastMCP() instantiated AFTER logging setup (prevents any early stdout writes)
    - @mcp.tool() decorator defined INSIDE main() (official quickstart pattern)
    - uv --directory absolute-path run server in .mcp.json (working-directory-independent)

key-files:
  created:
    - src/claude_history/server.py
    - .mcp.json
  modified: []

key-decisions:
  - "server.py logging order: reconfigure stderr → basicConfig(stderr) → FastMCP() → tools → mcp.run() — order is non-negotiable for stdout cleanliness"
  - "claude mcp add emits 'type: stdio' and 'env: {}' in .mcp.json — extra fields vs plan template but JSON structure is valid and accepted by Claude Code"
  - ".mcp.json committed to version control (no secrets, invocation config only)"
  - "Smoke test (Task 3) deferred to human verification — requires fresh Claude Code session to reload .mcp.json"

patterns-established:
  - "Pattern: All application logging routes to sys.stderr; stdout is exclusively for MCP JSON-RPC framing"
  - "Pattern: FastMCP server entry point uses main() wrapper; @mcp.tool() decorators defined inside main() after logging setup"
  - "Pattern: MCP project registration uses absolute --directory path in uv invocation"

requirements-completed: [SETUP-02]

# Metrics
duration: 3min
completed: 2026-05-04
---

# Phase 1 Plan 02: FastMCP Server Stub + MCP Registration Summary

**FastMCP stdio server stub with stderr-only logging registered via .mcp.json at project scope — claude mcp list confirms Connected, smoke test pending human verification**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-04T13:53:23Z
- **Completed:** 2026-05-04T13:55:57Z
- **Tasks:** 2 of 3 complete (Task 3 is human checkpoint — pending)
- **Files modified:** 2

## Accomplishments

- Created server.py with the exact stderr-only logging setup order required for clean stdio transport
- Registered claude-history server at project scope — `claude mcp list` shows `Connected`
- Zero stdout writes in server.py (AST-verified via ast.parse + node walk)
- .mcp.json uses absolute `--directory` path to ensure server spawns correctly from any working directory

## Task Commits

Each task was committed atomically:

1. **Task 1: Create server.py with stderr-only logging and get_status tool** - `88fe43c` (feat)
2. **Task 2: Register server with Claude Code at project scope** - `73ec2b8` (chore)
3. **Task 3: Smoke test** - PENDING (human-verify checkpoint)

**Plan metadata:** (committed after checkpoint resolution)

## Files Created/Modified

- `src/claude_history/server.py` - FastMCP stdio server; get_status tool returns {"status": "ok"}; stderr-only logging as first two actions in main(); zero print()/sys.stdout calls
- `.mcp.json` - Project-scope MCP server registration; uv --directory with absolute path; committed to version control

## Decisions Made

- Logging order is strictly: `sys.stderr.reconfigure(encoding="utf-8")` → `logging.basicConfig(stream=sys.stderr)` → `FastMCP()` → tool decorators → `mcp.run(transport="stdio")`. This prevents any early stdout writes during framework initialization.
- `claude mcp add` generated `.mcp.json` with extra `"type": "stdio"` and `"env": {}` fields vs the plan's expected template. These are valid and accepted by Claude Code — no deviation action needed.
- `.mcp.json` is committed (contains only invocation config, no secrets).

## Deviations from Plan

None — plan executed exactly as written. The extra `"type"` and `"env"` fields added by `claude mcp add` to `.mcp.json` are additive/compatible with the expected structure and do not require correction.

## Issues Encountered

None.

## Checkpoint Status

**Task 3 (Smoke test) is a blocking human-verify checkpoint.**

What was built is ready for testing:
- server.py is written and entry point is registered
- `claude mcp list` confirms the server Connected status in this session
- A NEW Claude Code session is required to trigger the .mcp.json approval prompt and load the server

The human smoke test procedure (from the plan):
1. Start a NEW Claude Code session in this project directory
2. Accept the project-scope server approval prompt when it appears
3. Ask Claude: "Please call the get_status tool on the claude-history MCP server."
4. Expected result: `{"status": "ok"}` with no MCP errors

## User Setup Required

**Human verification required.** Open a new Claude Code session in this project directory and call the `get_status` tool to confirm the MCP transport is clean (no stdout contamination).

## Next Phase Readiness

- Plan 01-03 (schema_discovery.py) can proceed immediately — it is independent of this plan's smoke test
- Phase 3 MCP tool development requires this smoke test to pass first (confirms clean stdio transport)

---
*Phase: 01-scaffolding-schema-discovery*
*Completed: 2026-05-04 (partial — Task 3 checkpoint pending)*

## Self-Check: PASSED

- FOUND: src/claude_history/server.py
- FOUND: .mcp.json
- FOUND: .planning/phases/01-scaffolding-schema-discovery/01-02-SUMMARY.md
- FOUND commit: 88fe43c (Task 1 - server.py)
- FOUND commit: 73ec2b8 (Task 2 - .mcp.json)
