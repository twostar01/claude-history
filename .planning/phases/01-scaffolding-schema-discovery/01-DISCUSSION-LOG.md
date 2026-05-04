# Phase 1: Scaffolding + Schema Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-03
**Phase:** 1-Scaffolding + Schema Discovery
**Areas discussed:** Stub tool scope, Schema discovery output, MCP registration scope

---

## Stub Tool Scope

| Option | Description | Selected |
|--------|-------------|----------|
| One dummy tool | A single get_status or ping tool. Just proves MCP over stdio works. All 6 real tools added in Phase 3. | ✓ |
| All 6 tool stubs | Stubs with correct signatures returning NotImplemented or placeholders. Phase 3 fills them in. | |

**User's choice:** One dummy tool

### get_status tool name + return value

| Option | Description | Selected |
|--------|-------------|----------|
| get_status → {"status": "ok"} | Natural health check name, returns a dict. Easy to grep for in stdout contamination test. | ✓ |
| ping → "pong" | Classic minimal smoke test, returns a plain string. | |
| You decide | Claude picks the name. | |

**User's choice:** `get_status` returning `{"status": "ok"}`

---

## Schema Discovery Output

### Print-only vs reference file

| Option | Description | Selected |
|--------|-------------|----------|
| Write a reference file | Writes .planning/SCHEMA.md alongside printing. Phase 2 planner reads it directly. | ✓ |
| Print to terminal only | Simpler script. Developer reads the output once. | |

**User's choice:** Write `.planning/SCHEMA.md`

### File location + format

| Option | Description | Selected |
|--------|-------------|----------|
| .planning/SCHEMA.md — Markdown | Lives alongside planning docs. Human-readable in diffs. | ✓ |
| data/schema.json — JSON | Machine-readable. | |
| Both | Human-readable + machine-parseable. | |

**User's choice:** `.planning/SCHEMA.md` (Markdown only)

### Detail level

| Option | Description | Selected |
|--------|-------------|----------|
| Field map + example values | Top-level keys, field names + types, one example value per field, timestamp format. | ✓ |
| Field map only | Key names and types, no examples. | |
| Full first-conversation dump | Full serialized conversation object. | |

**User's choice:** Field map + example values

---

## MCP Registration Scope

### Registration in Phase 1

| Option | Description | Selected |
|--------|-------------|----------|
| Full registration + call | claude mcp add --scope project in 01-02, then call get_status from Claude Code. Phase 4 promotes to user scope. | ✓ |
| Process-level only | Verify server starts + responds to stdio. No claude mcp add until Phase 4. | |

**User's choice:** Full registration + call from Claude Code in Phase 1

### Smoke test method

| Option | Description | Selected |
|--------|-------------|----------|
| Ask Claude Code directly | Open Claude Code session, ask it to call get_status. Human-driven, most realistic. | ✓ |
| MCP Inspector | npx @modelcontextprotocol/inspector to call via Inspector UI. More explicit. | |
| Both | Inspector for technical confirmation + Claude Code for realistic integration. | |

**User's choice:** Ask Claude Code directly

---

## Claude's Discretion

- pyproject.toml entry point names — `uv run server`, `uv run ingest`, and a name for schema_discovery (either `schema-discovery` or `schema_discovery`)
- Exact `claude mcp add` flags and server name for project-scope registration

## Deferred Ideas

None — discussion stayed within phase scope.
