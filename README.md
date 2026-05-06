# Claude History MCP Server

Search your Claude.ai conversation history from any Claude Code session.

Export your full history from Claude.ai, ingest it into a local SQLite database, and query it via MCP tools — without loading the entire history into your prompt.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (package manager)
- Claude Code CLI (`claude`)
- A Claude.ai account with at least one export downloaded

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/twostar01/claude-history.git
cd claude-history
```

**2. Install dependencies**

```bash
uv sync
```

This creates a `.venv` and installs `mcp[cli]` (FastMCP + stdio transport).

**3. Export your Claude.ai history**

Go to [claude.ai](https://claude.ai) → Settings → Account → Export Data.
Claude sends a download link by email. Download the ZIP file.

**4. Ingest the export**

```bash
uv run ingest path/to/your-export.zip
```

The ingest script is idempotent — you can safely re-run it after downloading a new export to pick up recent conversations.

Example output:

```
INFO claude_history.ingest Processing 106 conversations
INFO claude_history.ingest Skipped 0 existing conversations
INFO claude_history.ingest Inserted 106 conversations, 4087 messages
```

**5. Register the server with Claude Code**

Run this command once. Replace `<abs-path>` with the absolute path to this repository.

```bash
# On Windows (PowerShell):
claude mcp add -s user claude-history -- uv --directory "C:\path\to\claude-history" run server

# On macOS/Linux:
claude mcp add -s user claude-history -- uv --directory /path/to/claude-history run server
```

The `-s user` flag registers the server in your user-scope config so it is available in every Claude Code session, not just sessions inside this project directory.

**Verify registration:**

```bash
claude mcp list
```

You should see `claude-history` in the list.

## Updating History

When Claude.ai sends you a newer export ZIP, re-run ingest:

```bash
uv run ingest path/to/newer-export.zip
```

Only new conversations are added. Existing conversations are skipped.

## Available MCP Tools

### `search_conversations`

Search indexed conversations with BM25 full-text ranking.

```
search_conversations(query, project_filter?, include_full_content?)
```

- `query` — search terms; supports FTS5 operators (`AND`, `OR`, `NEAR()`, `prefix*`)
- `project_filter` — reserved for future use (currently always null in export)
- `include_full_content` — set to `true` to return full message text instead of snippets

Returns up to 10 conversations ranked by relevance, each with:
- `id` — conversation UUID
- `title` — conversation title
- `created_at` — timestamp
- `project` — always null (export format limitation)
- `match_count` — number of matching messages
- `snippet` — ~300-character excerpt around the best matching term (with **highlights**)

**Example prompt:**

> Search my Claude history for conversations about FTS5 tokenizer configuration.

---

### `get_conversation`

Return the full content of a conversation as labeled Human/Assistant turns.

```
get_conversation(id)
```

Returns `{ id, title, created_at, project, message_count, turns[] }` where each turn has `role`, `content`, and `position`.

**Example prompt:**

> Get the full content of conversation `<uuid from search result>`.

---

### `get_stats`

Return database statistics.

```
get_stats()
```

Returns conversation count, message count, date range, and database file size.

---

### `list_projects`

Return projects with conversation counts.

```
list_projects()
```

Note: The Claude.ai export format does not include project-to-conversation associations, so this tool always returns an empty list. This is a data limitation in the export format, not a bug.

---

### `export_conversation`

Return a conversation as a clean Markdown string suitable for pasting or summarizing.

```
export_conversation(id)
```

Format:
```markdown
# Conversation Title
*Date: 2026-05-01T12:00:00+00:00*

## Human

Your message here.

## Assistant

The response here.
```

---

### `get_status`

Return server health and a quick summary of indexed data.

```
get_status()
```

Returns `{ status: "ok", conversations: N, last_ingested: "..." }`.

## Architecture

Two processes sharing one SQLite file:

```
ingest.py   — reads Claude.ai export ZIP, writes to history.db (WAL mode)
server.py   — FastMCP stdio server, reads history.db, exposes 6 tools
```

Claude Code spawns `server.py` on demand per session via stdio transport. No persistent daemon or scheduler is needed.

**Database:** SQLite FTS5 with `unicode61 tokenchars '-_' remove_diacritics 2` tokenizer. Snake_case terms like `search_conversations` are treated as single tokens. Content is stored in the `messages` table; FTS5 uses a content-table pattern to avoid duplicate storage.

**Module layout:**

```
src/claude_history/
  config.py           # DB_PATH constant
  models.py           # SearchResult, Conversation, Stats dataclasses
  db.py               # Schema creation, FTS5 setup, WAL mode
  search.py           # FTS5 query building, BM25 ranking, snippet shaping
  ingest.py           # ZIP parsing, upsert, incremental ingest
  server.py           # FastMCP tool definitions (entry point)
  schema_discovery.py # Prints export ZIP structure (diagnostic tool)
```

## Logging

All server logging goes to `stderr`. Stdout is reserved exclusively for the MCP stdio JSON-RPC framing — writing anything to stdout would silently corrupt the session.

To see server logs during a Claude Code session, there is no action needed — they appear in the Claude Code process output when debugging.

## Security

- **Local only** — no network binding; the server process is spawned and owned by Claude Code
- **Read-only** — no write tools; the MCP server never modifies the database
- **Personal data** — `history.db` and export ZIPs are gitignored; never commit them

## License

MIT
