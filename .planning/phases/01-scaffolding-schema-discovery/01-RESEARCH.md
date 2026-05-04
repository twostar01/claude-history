# Phase 1: Scaffolding + Schema Discovery - Research

**Researched:** 2026-05-04
**Domain:** FastMCP stdio server setup, uv project scaffolding, Claude Code MCP registration, Claude.ai export ZIP schema
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** The Phase 1 server stub exposes a single `get_status` tool returning `{"status": "ok"}`. This is the smoke test target — if Claude Code can call it and nothing appears on stdout, the transport is clean.
- **D-02:** All 6 real MCP tools are added in Phase 3, not here.
- **D-03:** `schema_discovery.py` both prints to console AND writes `.planning/SCHEMA.md`.
- **D-04:** `.planning/SCHEMA.md` captures: top-level export keys, conversation object fields with types, message object fields with types, one example value per field, and the timestamp format.
- **D-05:** Output format is Markdown only (not JSON).
- **D-06:** Plan 01-02 includes running `claude mcp add --scope project` to register the server with Claude Code at project scope. Phase 4 promotes to user scope.
- **D-07:** Smoke test: open a Claude Code session and ask it to call `get_status` on the claude-history server. No MCP Inspector step in Phase 1.

### Claude's Discretion

- pyproject.toml entry point names — should follow CLAUDE.md: `uv run server`, `uv run ingest`; schema_discovery can be `uv run schema-discovery` or `uv run schema_discovery`
- The exact `claude mcp add` command flags and server name to use for project-scope registration

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | Project structured as uv package with pyproject.toml, entry points for `server` and `ingest` commands | uv init --package creates src/ layout + build system; [project.scripts] enables `uv run server` pattern |
| SETUP-02 | FastMCP with stdio transport; all logging to stderr; stdout never written to directly | `mcp.run(transport="stdio")` is the one-liner; `logging.basicConfig(stream=sys.stderr)` before mcp.run(); verified from official MCP quickstart |
| SETUP-04 | `.gitignore` excludes SQLite database file and Claude.ai export ZIPs | Standard patterns: `*.db`, `*.zip`, `.venv/`, `__pycache__/` — verified from gitignore conventions |
| INGEST-01 | User can run schema discovery script against a Claude.ai export ZIP that prints the JSON field structure without modifying the database | Export ZIP is on disk (`data-030cd706-...zip`); structure verified by inspection — see Schema Discovery section |
</phase_requirements>

---

## Summary

Phase 1 builds the project skeleton in three steps: (1) uv scaffolding with pyproject.toml and src/ layout, (2) a FastMCP stdio server stub that passes an end-to-end smoke test, and (3) a schema discovery script that inspects the real export ZIP and writes `.planning/SCHEMA.md`. All three are greenfield — no existing code to integrate.

The real Claude.ai export ZIP is already on disk at the project root (`data-030cd706-d473-447c-a7fe-b6d98e4f1277-1777822473-5f91f1fb-batch-0000.zip`). Its structure has been inspected in this research session: 11 files, three file categories (`conversations.json`, `projects/UUID.json`, `design_chats/UUID.json`). This means INGEST-01's gate condition is already met — schema_discovery.py can be run immediately after plan 01-03 is executed.

The #1 fatal risk is stdout contamination. Every plan in this phase must treat the stderr-only constraint as non-negotiable. The FastMCP stdio transport uses stdout exclusively for JSON-RPC framing; any stray print() or uncaught exception trace silently corrupts the session. `logging.basicConfig(stream=sys.stderr)` must be the first line of code executed in server.py's `main()` function.

**Primary recommendation:** Use `uv init --package` to create the src/ layout with a build system, define `[project.scripts]` entry points for clean `uv run server` / `uv run ingest` invocation, and use `claude mcp add --scope project` which writes `.mcp.json` to the project root.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MCP stdio protocol (JSON-RPC framing) | FastMCP framework | — | FastMCP owns stdin/stdout; application code must never touch stdout |
| Tool schema generation | FastMCP (auto from type hints + docstrings) | — | @mcp.tool() decorator auto-generates JSON schema |
| Application logging | Server process stderr | — | MCP protocol owns stdout; all diagnostics go to stderr only |
| Project entry points | pyproject.toml [project.scripts] | uv build backend | Entry points require a build system in pyproject.toml |
| MCP registration | Claude Code CLI (claude mcp add) | .mcp.json file | --scope project writes .mcp.json to repo root |
| Export schema inspection | schema_discovery.py (standalone script) | — | No DB writes; reads ZIP only |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp[cli]` | 1.27.0 (>=1.2.0 minimum) | MCP Python SDK — includes FastMCP, stdio transport | Official Anthropic SDK; `mcp.server.fastmcp.FastMCP` is the standard class per official MCP quickstart |
| `uv` | latest (not yet installed) | Package manager, virtual environment, entry point runner | Official MCP quickstart recommendation; needed before any other setup step |
| `sqlite3` | stdlib (3.41+ with Python 3.11+) | FTS5 database — Phase 2 only; Phase 1 imports it only in config.py for DB_PATH | Built into CPython; FTS5 verified available on this machine |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `zipfile` | stdlib | Read Claude.ai export ZIP without extracting to disk | schema_discovery.py reads ZIP members in-memory |
| `json` | stdlib | Parse JSON members from ZIP | No third-party parser needed |
| `logging` | stdlib | Stderr-only diagnostic output | Use instead of print() everywhere |
| `pathlib` | stdlib | Resolve DB_PATH relative to `__file__` in config.py | Keeps paths absolute and working-directory-independent |
| `pywin32` | 311 (auto-installed by mcp on Windows) | Windows-specific MCP SDK dependency | Installed automatically; no explicit declaration needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `mcp[cli]` FastMCP | standalone `fastmcp` package (v3.2.4) | Different package, different maintainer (Jeremiah Lowin), different import paths. `mcp[cli]` is the official Anthropic SDK. Use `mcp[cli]` per CLAUDE.md. |
| `uv init --package` | plain `uv init` | Plain init has no build system → `[project.scripts]` entry points won't work → `uv run server` fails. Use `--package`. |
| `logging` to stderr | `print(..., file=sys.stderr)` | Both are safe for stdio. `logging` is standard practice and has levels. Use `logging`. |

**Installation (after installing uv):**
```powershell
# Step 0: Install uv (not yet installed on this machine)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Restart terminal after uv install

# Step 1: Initialize package project (already in repo directory)
uv init --package .

# Step 2: Add mcp dependency
uv add "mcp[cli]>=1.2.0"
```

**Version verification:**
`mcp` 1.27.0 was verified against PyPI on 2026-05-04. Released 2026-04-02. Python >=3.10 required; system Python 3.14.4 satisfies this.

---

## Architecture Patterns

### System Architecture Diagram

```
  Claude Code session
       |
       | spawns on demand (stdio)
       v
  [server.py]  -- stdin/stdout: JSON-RPC 2.0 (MCP protocol)
       |          stderr: logging only
       |
  FastMCP instance
  - get_status() tool (Phase 1 stub)
       |
       | (Phase 2+) reads
       v
  history.db  (SQLite, not created in Phase 1)

  Separately:
  [schema_discovery.py]  -- reads ZIP, writes .planning/SCHEMA.md
       |
       v
  data-*.zip  (Claude.ai export, already on disk)
```

### Recommended Project Structure

```
claude-history/             # repo root (git already initialized)
├── src/
│   └── claude_history/     # package created by uv init --package
│       ├── __init__.py
│       ├── server.py       # FastMCP server; entry point: main()
│       ├── config.py       # DB_PATH constant (Phase 1 stub)
│       └── schema_discovery.py  # standalone script; entry point: main()
├── pyproject.toml          # [project.scripts] defines 'server', 'ingest', 'schema-discovery'
├── .python-version         # created by uv init (pins Python version)
├── .gitignore              # excludes *.db, *.zip, .venv/, __pycache__/
├── .mcp.json               # written by claude mcp add --scope project
├── .venv/                  # created by uv (gitignored)
├── .planning/              # existing planning artifacts
│   ├── SCHEMA.md           # written by schema_discovery.py (01-03)
│   └── phases/01-.../
└── data-*.zip              # export ZIP (gitignored by *.zip rule)
```

Note: `ingest.py` is not created in Phase 1. The `[project.scripts]` entry for `ingest` can be stubbed in pyproject.toml pointing at a placeholder or left for Phase 2. `schema-discovery` entry is added for plan 01-03.

### Pattern 1: FastMCP Stdio Server with Stderr Logging

**What:** Minimal FastMCP server that registers one tool and starts the MCP stdio loop.
**When to use:** Phase 1 stub; becomes the permanent server.py structure.

```python
# Source: modelcontextprotocol.io/quickstart/server (verified 2026-05-04)
import sys
import logging
from mcp.server.fastmcp import FastMCP

# MUST be first: configure all logging to stderr before anything writes to stdout
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s"
)

mcp = FastMCP("claude-history")

@mcp.tool()
def get_status() -> dict:
    """Return server status. Used to verify MCP transport is clean."""
    return {"status": "ok"}

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

Key rules:
- `logging.basicConfig(stream=sys.stderr)` before `FastMCP()` instantiation
- `mcp.run(transport="stdio")` — explicit transport argument (default is also stdio, but explicit is clearer)
- `if __name__ == "__main__"` guard — required for entry point invocation via uv

### Pattern 2: pyproject.toml with Entry Points

**What:** Package configuration that enables `uv run server`, `uv run ingest`, `uv run schema-discovery`.
**When to use:** Created in plan 01-01.

```toml
# Source: docs.astral.sh/uv (verified 2026-05-04)
[project]
name = "claude-history"
version = "0.1.0"
description = "MCP server for searching Claude.ai conversation history"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.2.0",
]

[project.scripts]
server = "claude_history.server:main"
ingest = "claude_history.ingest:main"
schema-discovery = "claude_history.schema_discovery:main"

[build-system]
requires = ["uv_build>=0.11.8,<0.12"]
build-backend = "uv_build"
```

Note: `[build-system]` is required for `[project.scripts]` to work. `uv init --package` generates this automatically with `uv_build` as the backend.

### Pattern 3: claude mcp add for Project Scope

**What:** Registers the server in `.mcp.json` at the project root for version-controlled team sharing.
**When to use:** Plan 01-02 smoke test setup.

```powershell
# Source: code.claude.com/docs/en/mcp (verified 2026-05-04)
# --scope project writes to .mcp.json in the current directory
# -- separates claude args from the server command
claude mcp add --scope project claude-history -- uv --directory "C:\Users\nclem\Claude Code\claude-history" run server
```

The resulting `.mcp.json` in the project root:
```json
{
  "mcpServers": {
    "claude-history": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\nclem\\Claude Code\\claude-history",
        "run",
        "server"
      ]
    }
  }
}
```

Important: `--scope project` (not `--scope local`, not `--scope user`). Per docs:
- `local` (default): stored in `~/.claude.json`, private to you, current project only
- `project`: stored in `.mcp.json` in project root, **shared via version control**
- `user`: stored in `~/.claude.json`, available across all your projects

Phase 1 uses `project` scope. Phase 4 upgrades to `user` scope.

### Pattern 4: Schema Discovery with zipfile

**What:** Read ZIP members in-memory without extracting, print field map, write SCHEMA.md.
**When to use:** Plan 01-03.

```python
# Source: Python stdlib docs + direct inspection of real export ZIP (verified 2026-05-04)
import zipfile
import json
import sys
from pathlib import Path

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run schema-discovery <path-to-export.zip>", file=sys.stderr)
        sys.exit(1)

    zip_path = Path(sys.argv[1])
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        print(f"ZIP contains {len(names)} files:")
        for n in names:
            print(f"  {n}")

        # Read conversations.json
        with zf.open("conversations.json") as f:
            convs = json.load(f)
        # ... inspect and format field map

    # Write .planning/SCHEMA.md
    schema_path = Path(__file__).parent.parent.parent.parent / ".planning" / "SCHEMA.md"
    schema_path.write_text(schema_content, encoding="utf-8")
    print(f"Schema written to {schema_path}")
```

### Anti-Patterns to Avoid

- **Bare `print()` in server.py:** Silently corrupts the JSON-RPC stream. Use `logging.info(...)` or `print(..., file=sys.stderr)`.
- **`uv init` without `--package`:** No build system means `[project.scripts]` won't work, so `uv run server` will fail with "No such command: server".
- **Relative paths in `.mcp.json`:** Claude Code spawns the server from an undefined working directory. Always use `--directory` with absolute path in the `uv` command.
- **`--scope local` instead of `--scope project`:** `local` stores the config in `~/.claude.json` scoped to this project path. Changes in Phase 4 become ambiguous. Use `--scope project` explicitly as decided in D-06.
- **`logger = logging.getLogger()` before `basicConfig()`:** Configuring logging after a third-party library has already called `getLogger()` may produce a root handler that sends to stdout. Call `basicConfig(stream=sys.stderr)` as the first statement in `main()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol (JSON-RPC framing, tool schema, transport) | Custom asyncio stdin/stdout handler | `mcp.server.fastmcp.FastMCP` | Protocol has dozens of edge cases (initialize handshake, capabilities negotiation, error framing). FastMCP handles all of it. |
| ZIP file reading | Custom binary parser | `zipfile.ZipFile` (stdlib) | zipfile handles ZIP64, encrypted ZIPs, in-memory streaming. One import, zero deps. |
| JSON parsing from ZIP | `f.read().decode()` + custom | `json.load(zf.open(name))` | json.load accepts a file-like object; no read-decode-parse needed. |
| Entry point installation | shell scripts | `[project.scripts]` in pyproject.toml | uv manages the entry point lifecycle; scripts become available after `uv sync`. |

**Key insight:** FastMCP's value in Phase 1 is entirely in the MCP protocol layer. Don't fight it by touching stdio directly.

---

## Discovered Export Schema (INGEST-01 Pre-Work)

The real export ZIP has been inspected. This section documents what `schema_discovery.py` will find and what `.planning/SCHEMA.md` must capture.

[VERIFIED: direct zipfile inspection of data-030cd706-...zip on 2026-05-04]

### ZIP File Structure

```
conversations.json          # all conversations (106 in this export)
projects/UUID.json          # one file per project (6 projects)
design_chats/UUID.json      # one file per design chat (2 design chats)
users.json                  # account info (1 user)
```

### conversations.json

Top-level: array of conversation objects.

**Conversation object fields:**

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `uuid` | string | `"02b2f9e6-5bc0-..."` | Primary key |
| `name` | string | `"LLMs and neural networks"` | Conversation title; may be empty string |
| `summary` | string | `""` | Often empty |
| `created_at` | string | `"2026-03-28T05:52:32.764454Z"` | ISO 8601 UTC |
| `updated_at` | string | `"2026-03-28T05:52:33.173452Z"` | ISO 8601 UTC |
| `account` | object | `{"uuid": "fab81771-..."}` | Account reference only |
| `chat_messages` | array | `[...]` | Array of message objects |

Note: No `project` field on conversation objects in this export. Project association is not available from conversations.json — only from `projects/UUID.json`.

**Message object fields (`chat_messages[n]`):**

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `uuid` | string | `"019d3300-5550-..."` | Message ID |
| `text` | string | `"How to LLMs and neural networks..."` | Plain text content (PRIMARY field for FTS) |
| `content` | array | `[{...}]` | Structured content blocks (see below) |
| `sender` | string | `"human"` or `"assistant"` | Role field |
| `created_at` | string | `"2026-03-28T05:52:33.173452Z"` | ISO 8601 UTC |
| `updated_at` | string | `"2026-03-28T05:52:33.173452Z"` | ISO 8601 UTC |
| `attachments` | array | `[]` | File attachment metadata |
| `files` | array | `[{"file_uuid": "...", "file_name": "allsky.py"}]` | Uploaded files |
| `parent_message_uuid` | string | `"00000000-0000-4000-..."` | Threading; root messages use nil UUID |

**content array item fields:**

| Field | Type | Example |
|-------|------|---------|
| `start_timestamp` | string | `"2026-03-28T05:52:33.144604Z"` |
| `stop_timestamp` | string | `"2026-03-28T05:52:33.144604Z"` |
| `flags` | null/array | `null` |
| `type` | string | `"text"` |
| `text` | string | `"How to LLMs and neural networks relate to each other?"` |
| `citations` | array | `[]` |

Note: The `text` field on the message object and `content[0].text` contain the same value for simple messages. Use `message["text"]` directly for FTS indexing — it's simpler and always present.

### projects/UUID.json

One file per project. Each file is a single dict (not an array).

| Field | Type | Example |
|-------|------|---------|
| `uuid` | string | `"019cbca7-..."` |
| `name` | string | `"Nature Pi"` |
| `description` | string | `"This is a self contained..."` |
| `is_private` | bool | `true` |
| `is_starter_project` | bool | `false` |
| `prompt_template` | string | Long text |
| `created_at` | string | `"2026-03-05T06:20:46.561314+00:00"` |
| `updated_at` | string | `"2026-03-05T06:28:53.577317+00:00"` |
| `creator` | object | Account reference |
| `docs` | array | `[]` |

Note: Timestamp format here uses `+00:00` offset notation instead of the `Z` suffix seen in conversations.json. Both are UTC but schema_discovery.py must document both formats.

### design_chats/UUID.json

One file per design chat. Different message schema from conversations.

| Field | Type | Notes |
|-------|------|-------|
| `uuid` | string | |
| `title` | string | |
| `project` | object | `{"uuid": "...", "name": "..."}` — project linkage IS present here |
| `created_at` | string | ISO 8601 with offset |
| `updated_at` | string | |
| `messages` | array | Different message format (see below) |

Design chat messages have `role` field (`"user"` / `"assistant"`) and `content` as a dict with nested `role`, `content`, `attachments`, `authorAccountUuid`, `authorName`, `id`, `timestamp` fields. Structure is considerably more complex than conversations.json messages.

### users.json

Array with one user object: `uuid`, `full_name`, `email_address`, `verified_phone_number`.

### Key Observations for Phase 2 Planning

1. **Project linkage in conversations.json is absent.** Conversations do not have a `project` field. To associate conversations with projects, Phase 2 will need to either (a) skip project association, or (b) join via design_chats (which has `project`). This must be flagged in SCHEMA.md.
2. **Primary text field is `message["text"]`** — direct string, always present. The `content` array is more structured but the `text` field is the reliable FTS target.
3. **Timestamp format variation:** `Z` suffix in conversations.json vs `+00:00` in projects. `datetime.fromisoformat()` handles both in Python 3.11+.
4. **design_chats are a separate entity** with a different message schema. Phase 2 should decide whether to ingest them.

---

## Common Pitfalls

### Pitfall 1: stdout contamination silently kills the MCP session

**What goes wrong:** Any write to stdout — `print()`, uncaught exceptions, `logging` without explicit `stream=sys.stderr` — corrupts the JSON-RPC framing. Claude Code receives malformed JSON and drops the connection silently.

**Why it happens:** The stdio transport uses stdout exclusively for JSON-RPC. It is not available for application use.

**How to avoid:** Call `logging.basicConfig(stream=sys.stderr, level=logging.INFO)` as the first statement in `main()`. Wrap `mcp.run()` in a try/except that logs to stderr. Never import a module that logs to stdout.

**Warning signs:** Claude Code reports "MCP error" or tools return nothing. The server process exits unexpectedly. These are the same symptoms as a correct empty result — the only way to distinguish is to check stderr output.

[VERIFIED: modelcontextprotocol.io/quickstart/server — "Never write to stdout. Writing to stdout will corrupt the JSON-RPC messages."]

### Pitfall 2: uv not installed

**What goes wrong:** `uv` is not currently installed on this machine (`which uv` returns None). Plan 01-01 cannot proceed without it.

**How to avoid:** Install uv as the first step of plan 01-01:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
Then restart the terminal before using `uv` commands.

[VERIFIED: uv not found in PATH on 2026-05-04; install command from official docs]

### Pitfall 3: [project.scripts] requires a build system

**What goes wrong:** If `uv init` is run without `--package`, there is no `[build-system]` section in pyproject.toml, and `[project.scripts]` entry points do not work. `uv run server` fails with "No such command: server" or falls through to looking for a file named `server` with no extension.

**How to avoid:** Use `uv init --package .` (the `.` targets the existing directory). This creates the src/ layout and adds the `uv_build` backend automatically.

[VERIFIED: docs.astral.sh/uv — "Using the entry point tables requires a build system to be defined"]

### Pitfall 4: Relative paths in .mcp.json

**What goes wrong:** Claude Code spawns the MCP server subprocess from an unspecified working directory (not the project root). Relative paths in the `command` or `args` fields silently fail.

**How to avoid:** Always use the `--directory` flag with the absolute path when invoking `uv`:
```
uv --directory "C:\Users\nclem\Claude Code\claude-history" run server
```

[VERIFIED: code.claude.com/docs/en/mcp — "Always use absolute paths in your configuration"]

### Pitfall 5: Windows console encoding for stderr

**What goes wrong:** Windows defaults to cp1252 encoding for console output. If server logs contain non-ASCII characters from conversation content, `logging` may raise `UnicodeEncodeError`.

**How to avoid:** Add at the top of `server.py`'s `main()`:
```python
sys.stderr.reconfigure(encoding='utf-8')
```

[VERIFIED: Python docs — `TextIOWrapper.reconfigure()` available since Python 3.7]

### Pitfall 6: Project-scope MCP registration prompts for approval

**What goes wrong:** When a Claude Code session first encounters a project-scoped `.mcp.json`, it prompts the user for approval before loading the servers. If the user dismisses the prompt, the MCP server is not loaded and the smoke test appears to fail.

**How to avoid:** During the smoke test (D-07), expect and accept the approval prompt. This is normal behavior for project-scoped servers and happens only once per project per machine.

[VERIFIED: code.claude.com/docs/en/mcp — "Claude Code prompts for approval before using project-scoped servers from .mcp.json files"]

---

## Code Examples

### Minimal server.py (Plan 01-02)

```python
# Source: modelcontextprotocol.io/quickstart/server + direct adaptation
import sys
import logging
from mcp.server.fastmcp import FastMCP

def main() -> None:
    # FIRST: redirect all logging to stderr before any other imports can write
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    mcp = FastMCP("claude-history")

    @mcp.tool()
    def get_status() -> dict:
        """Return server health status."""
        return {"status": "ok"}

    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

### Minimal config.py (Plan 01-01)

```python
# Source: [ASSUMED] standard pattern — verified pattern from .planning/research/STACK.md
from pathlib import Path

# Resolve DB_PATH relative to this file so it works regardless of working directory
DB_PATH = Path(__file__).parent.parent.parent / "history.db"
```

Note: With src/claude_history/config.py, the DB at project root is 3 levels up (`../../..`). Verify this path when implementing.

### .gitignore (Plan 01-01)

```gitignore
# Database files — contain personal conversation history
*.db
*.sqlite
*.sqlite3

# Claude.ai export ZIPs — contain personal conversation history
*.zip

# Python
.venv/
__pycache__/
*.py[cod]
*.egg-info/

# uv
.python-version
uv.lock
```

Note: `uv.lock` is often committed for reproducible installs. For a personal tool, committing it is fine. Add it to .gitignore only if lock file churn is unwanted.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTTP/SSE transport (deprecated) | stdio transport for local tools | MCP protocol 2025-06-18 | stdio is simpler; no port management; Claude Code spawns on demand |
| `claude_desktop_config.json` | `claude mcp add` CLI + `~/.claude.json` / `.mcp.json` | Claude Code v2.x | Use `claude mcp add` — never edit JSON config manually |
| `--scope global` | `--scope user` | Claude Code recent versions | Scope names changed: `project` (old) → `local` (new default); new `project` scope → `.mcp.json` |

**Deprecated/outdated:**
- HTTP+SSE transport: replaced by stdio for local tools. Do not implement.
- Task Scheduler for MCP: unnecessary for stdio transport. The old architecture research recommended Task Scheduler for HTTP; this was corrected in STATE.md.
- Direct `claude_desktop_config.json` editing: the `claude mcp add` CLI is the correct method.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `uv init --package .` works correctly in an existing git repo with files already present | Standard Stack / Pattern 2 | uv may refuse to init in a non-empty directory; may need `--no-readme` or manual pyproject.toml |
| A2 | `uv run server` resolves entry point after `uv sync` without explicit `uv sync` call by the user | Standard Stack | User may need to run `uv sync` before entry points work |
| A3 | `logging.basicConfig(stream=sys.stderr)` set before `FastMCP()` instantiation fully prevents any FastMCP internal logging from reaching stdout | Pitfall 1 | FastMCP may have its own logging configuration that overrides root handler |
| A4 | The `--directory` flag in `uv --directory ... run server` causes uv to treat that directory as the project root for entry point resolution | Pattern 3 | Entry points might not resolve without explicit `uv sync` first; fallback is `uv run src/claude_history/server.py` |
| A5 | `sys.stderr.reconfigure(encoding='utf-8')` is safe to call before any logging setup on Python 3.14 | Code Examples | Behavior may differ; test at startup |

---

## Open Questions (RESOLVED)

1. **Does `uv init --package .` work in a non-empty directory?**
   - RESOLVED: Plan 01-01 Task 1 uses `uv init --package . --no-readme` to skip README generation; fallback to manual pyproject.toml creation if uv refuses non-empty directory.

2. **Should `design_chats` be included in schema_discovery.py output?**
   - RESOLVED: schema_discovery.py documents ALL file types including design_chats. Phase 2 planning decides on ingest scope. SCHEMA.md flags structural differences.

3. **How does project association work for conversations?**
   - RESOLVED: Plan 01-03 documents the gap explicitly in SCHEMA.md under "Project Association Gap". Phase 2 will decide the association strategy.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All plans | Yes | 3.14.4 (at `C:/Python314/python`) | — |
| uv | 01-01, 01-02, 01-03 | **No** | — | Must install first: `irm astral.sh/uv/install.ps1 \| iex` |
| claude CLI | 01-02 (mcp add) | Yes | 2.1.126 | — |
| SQLite FTS5 | config.py check only in Phase 1 | Yes | Verified on this machine | — |
| Export ZIP | 01-03 (schema discovery) | Yes | `data-030cd706-...zip` at project root | — |
| git | All plans (commits) | Yes | In PATH | — |

**Missing dependencies with no fallback:**
- `uv` — must be installed before plan 01-01 can begin. Install command: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

**Missing dependencies with fallback:**
- None.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | stdio transport — no network, no auth needed |
| V3 Session Management | No | stdio transport — session is process lifetime |
| V4 Access Control | No | local-only tool, single user |
| V5 Input Validation | Minimal (Phase 1 only) | get_status takes no input |
| V6 Cryptography | No | no secrets, no encryption needed |

Phase 1 has minimal security surface — the stub tool takes no input and returns a hardcoded value. The significant security constraint is SETUP-04: the export ZIP and database file must be gitignored to prevent personal conversation history from being committed.

---

## Sources

### Primary (HIGH confidence)
- `modelcontextprotocol.io/quickstart/server` — FastMCP server setup, `mcp.run(transport="stdio")`, logging/stderr requirement, `mcp[cli]` install command (verified 2026-05-04)
- `code.claude.com/docs/en/mcp` — `claude mcp add` command syntax, scope meanings, `.mcp.json` format, project scope behavior (verified 2026-05-04)
- `docs.astral.sh/uv` — `uv init --package`, `[project.scripts]` entry points, build system requirement, `uv run` behavior (verified 2026-05-04)
- PyPI `mcp` package — version 1.27.0, released 2026-04-02, Python >=3.10 (verified 2026-05-04)
- Direct ZIP inspection — `data-030cd706-...zip` file schema: 11 files, conversations.json structure, message fields, project files, timestamp formats (verified 2026-05-04 via zipfile + json)

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — prior research with HIGH confidence claims on FastMCP patterns, mcp[cli] import path, FTS5 setup; verified against primary sources above (2026-05-03)

### Tertiary (LOW confidence)
- None in this research.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — mcp version verified on PyPI; uv pattern verified on official docs
- Architecture: HIGH — export schema directly inspected; FastMCP pattern from official quickstart
- Pitfalls: HIGH — stdout contamination rule from official docs; uv missing from own environment check

**Research date:** 2026-05-04
**Valid until:** 2026-06-04 (stable domain; uv and mcp release frequently but patterns are stable)
