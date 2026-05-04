# Phase 1: Scaffolding + Schema Discovery - Context

**Gathered:** 2026-05-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Create the uv project skeleton (pyproject.toml, .gitignore, config.py with DB_PATH), a FastMCP server stub with stderr-only logging that registers with Claude Code and passes an end-to-end smoke test, and a schema_discovery.py script that inspects a real Claude.ai export ZIP and writes a persistent field reference to .planning/SCHEMA.md.

This phase is gated on a real export ZIP being on disk before schema_discovery.py can be run. The schema reference it produces unblocks Phase 2 (ingest.py cannot be written without knowing field names).

</domain>

<decisions>
## Implementation Decisions

### Stub Tool Design
- **D-01:** The Phase 1 server stub exposes a single `get_status` tool (not all 6 final tools). The tool returns `{"status": "ok"}` as a hardcoded dict. This is the smoke test target — if Claude Code can call it and nothing appears on stdout, the transport is clean.
- **D-02:** All 6 real MCP tools (search_conversations, get_conversation, list_projects, get_stats, export_conversation) are added in Phase 3, not here. Phase 1 does not stub them.

### Schema Discovery Output
- **D-03:** `schema_discovery.py` both prints to console AND writes `.planning/SCHEMA.md`. Phase 2 planner reads the file directly — no need to re-run the script or hold the output in memory.
- **D-04:** `.planning/SCHEMA.md` captures: top-level export keys, conversation object fields with types, message object fields with types, one example value per field, and the timestamp format. This is enough for ingest.py to be written without re-inspecting the ZIP.
- **D-05:** Output format is Markdown only (not JSON). Human-readable, diff-friendly, rendered in editors.

### MCP Registration + Smoke Test
- **D-06:** Plan 01-02 includes running `claude mcp add --scope project` to register the server with Claude Code at project scope. This is the Phase 1 registration for testing. Phase 4 promotes it to user scope.
- **D-07:** The smoke test method is: open a Claude Code session and ask it to call `get_status` on the claude-history server. Human-driven, most realistic confirmation of end-to-end MCP + stdout cleanliness. No MCP Inspector step in Phase 1.

### Claude's Discretion
- pyproject.toml entry point names (e.g., `server`, `ingest`, `schema-discovery`) — names should follow the CLAUDE.md description (`uv run server`, `uv run ingest`; schema_discovery can be `uv run schema-discovery` or `uv run schema_discovery`)
- The exact `claude mcp add` command flags and server name to use for project-scope registration

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Requirements and Decisions
- `.planning/PROJECT.md` — Core value, requirements, key decisions (stack locked, transport confirmed stdio, stdout constraint)
- `.planning/REQUIREMENTS.md` — Full requirement list; Phase 1 covers SETUP-01, SETUP-02 (partial), SETUP-04, INGEST-01
- `.planning/ROADMAP.md` — Phase 1 goal, success criteria, and plan breakdown (01-01, 01-02, 01-03)

### Codebase Conventions
- `CLAUDE.md` — Module layout (`src/` structure), technology stack constraints, stderr-only logging rule (CRITICAL: stdout contamination silently kills stdio MCP sessions)

No external API specs — the Claude.ai export schema is unknown until schema_discovery.py inspects a real ZIP. SCHEMA.md will be created by 01-03 and becomes a canonical ref for Phase 2.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — this is a greenfield project. No existing code to reuse.

### Established Patterns
- Logging must go to `sys.stderr` only. `print()` is forbidden in server.py (and any module imported by it) because stdout contamination silently kills the stdio MCP session. This is the #1 invariant for all phases.

### Integration Points
- Phase 2 reads `.planning/SCHEMA.md` (produced by 01-03) to write ingest.py field extraction
- Phase 2 reads `src/config.py` (DB_PATH) produced by 01-01
- Phase 4 replaces the project-scope `claude mcp add` from 01-02 with a user-scope permanent registration

</code_context>

<specifics>
## Specific Ideas

- The dummy `get_status` tool name is deliberate — it could evolve into a real tool in Phase 3 (returning DB stats or server version) without renaming
- SCHEMA.md location `.planning/SCHEMA.md` keeps it alongside other planning artifacts, making it visible in the same context as ROADMAP.md and REQUIREMENTS.md when downstream agents load planning context

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Scaffolding + Schema Discovery*
*Context gathered: 2026-05-03*
