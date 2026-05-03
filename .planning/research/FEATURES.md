# Features Research: Claude History MCP Server

**Domain:** Local MCP server for personal conversation history retrieval
**Researched:** 2026-05-03
**Confidence:** HIGH for MCP tool patterns (official spec verified); MEDIUM for Claude.ai export schema (no public documentation found — must reverse-engineer from actual export file); HIGH for SQLite FTS5 capabilities

---

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Full-text search across all conversations | Core value prop — useless without it | Low | SQLite FTS5; combine FTS MATCH with SQL WHERE for date/project filtering |
| Snippet/excerpt in results | LLMs cannot afford to load entire conversations per result; they need enough context to decide relevance | Low | FTS5 `snippet()` function; 20-40 tokens is the usable range (FTS5 max is 64 tokens per call) |
| Result count and metadata alongside snippets | LLM needs to know "3 of 47 results shown" to reason about whether to broaden or narrow | Low | Return `total_matches`, `returned_count`, `has_more` |
| Per-result conversation ID | Required for the follow-up `get_conversation(id)` call | Trivial | Must be stable across re-ingestions |
| Conversation title in results | Primary human-readable identifier; Claude.ai auto-generates titles | Low | Title comes from export; fall back to first N chars of first user message if absent |
| Conversation date (created_at / updated_at) | Users frequently recall "something I talked about last month" — date is the primary recall axis | Low | ISO 8601 string; store both created and last-updated |
| `list_projects()` tool | Enables the LLM to enumerate available project names before filtering | Low | Returns list of {name, conversation_count} |
| `get_conversation(id)` tool | Full content retrieval for conversations found via search | Low | Returns all messages in order with role labels |
| Project filter on search | Claude.ai organizes conversations by project; this is the primary organizational unit | Low | Optional string parameter; NULL = search all projects |
| Graceful empty-result response | Tool must not error on zero results; return empty list + "no matches found" message | Trivial | isError: false; empty results array |
| Read-only enforcement | All operations are SELECT only; no INSERT/UPDATE/DELETE via MCP | Trivial | SQLite opened in read-only mode (`uri=true&mode=ro`) |

---

## Differentiators

Features that set this tool apart from a naive implementation.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| BM25 relevance ranking (not just date-sorted) | Surfaces the most relevant past conversation, not just the most recent one that mentions the term | Low | FTS5 `ORDER BY bm25(fts_table)` — lower score = better match; use negative bm25 for DESC |
| `include_full_content` flag on search | Saves a round-trip `get_conversation` call for simple lookups; the LLM gets everything in one shot when it knows it wants full content | Low | Default false; when true, embed full message list in each result object |
| Role filter on `search_conversations` | Lets LLM ask "find places where I (human) described X" vs "find Claude's recommendations about X" | Low | Optional `role` enum: `human`, `assistant`, `all` (default) |
| Date range filter on `search_conversations` | "What did I figure out about Docker last week?" — temporal scoping is very natural for recall | Low | `after` and `before` as optional ISO 8601 date strings; implemented via SQL WHERE, not FTS |
| `get_stats()` tool | Gives LLM a fast orientation: total conversations, date range of history, project list with counts | Low | Returns {total_conversations, total_messages, date_range: {oldest, newest}, projects: [{name, count}]} |
| Phrase search syntax pass-through | Users (via LLM) can use `"exact phrase"` and `term*` prefix queries naturally in the query string | Low | FTS5 MATCH supports these natively; document in tool description |
| Snippet with highlight markers | Surround matched terms in results like `<<<term>>>` so LLM can identify exactly why a result matched | Low | FTS5 `snippet(table, col_idx, '<<<', '>>>', '...', 32)` |
| `limit` parameter on search | Let LLM control how many results to request — small for quick lookups, larger when doing comprehensive review | Low | Default 10, max 50; prevents context window overflow |

---

## Anti-Features

Things to deliberately not build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Fuzzy/typo-tolerant search | FTS5 has no native fuzzy match; implementing it requires trigram tokenizer which is significantly slower and adds complexity disproportionate to value for a personal tool | Use FTS5 prefix search (`term*`) which handles partial matches; document this in the tool description so LLMs use it naturally |
| Vector/semantic search | Requires embedding model, vector index (sqlite-vec or external), non-trivial setup — this is "zero infra" by design | BM25 FTS5 is good enough for personal history where users know roughly what they said; semantic search is scope creep |
| Web UI or search interface | Out of scope per PROJECT.md; Claude Code IS the interface | None |
| Write operations (create/update/delete conversations) | Claude.ai is the source of truth; MCP writes would create a confusing two-source problem | Keep server strictly read-only |
| Automated export fetching | Claude.ai export requires manual trigger in account settings (no API); any automation would require browser automation which is fragile and a security risk | Ingest script is run manually post-download |
| Authentication / API key | This is a personal local tool on localhost; auth adds friction with zero security benefit (localhost-only, single user) | Localhost binding is the security boundary |
| Pagination cursor | Cursor-based pagination adds state complexity; for a personal history server with limit/offset this is unnecessary | Use `offset` integer parameter on search_conversations for sequential page retrieval if needed |
| Multi-machine sync | Scope is single-machine; sync requires a server, auth, conflict resolution — a different product | Design schema so it could be ported later, but do not build sync |
| Real-time / live index updates | History is ingested from periodic manual exports; the index is always a snapshot | Re-run ingest script after each export |
| Conversation summarization | Tempting but an LLM capability, not a data-layer capability; the MCP server should return raw data, not generate summaries | Let Claude Code do summarization on retrieved content |

---

## Claude.ai Export Format

**Confidence: LOW — no official public documentation found.** The schema must be reverse-engineered from the actual export file when it is available. The following is inferred from community discussion patterns, the nature of Claude.ai's data model, and comparison with similar tools (OpenAI's export format, which is public).

### What We Know With Confidence

Claude.ai's data export (accessible via account Settings > Privacy > Export Data) produces a ZIP archive. Inside is at minimum one JSON file containing conversations.

### Inferred Structure (MUST VERIFY against actual export)

Based on the Claude.ai product model (projects, conversations, human/assistant message pairs) and analogy with OpenAI's documented export format:

```json
// Top level: array of conversations
[
  {
    "uuid": "string — stable unique ID per conversation",
    "name": "string — auto-generated or user-set title",
    "created_at": "ISO 8601 timestamp",
    "updated_at": "ISO 8601 timestamp",
    "project": {
      "uuid": "string",
      "name": "string"
    },
    "chat_messages": [
      {
        "uuid": "string",
        "sender": "human | assistant",
        "created_at": "ISO 8601 timestamp",
        "text": "string — message body",
        "content": [
          {
            "type": "text | tool_use | tool_result | thinking",
            "text": "string (for type: text)"
          }
        ]
      }
    ]
  }
]
```

### Key Uncertainties to Resolve on First Import

- Field name for conversation ID: `uuid` vs `id` vs `conversation_id`
- Field name for project: `project` vs `project_uuid` vs flat `project_name`
- Whether conversations without a project have `null` or a missing key
- Whether `text` is a top-level field or only inside the `content` array
- Whether tool_use blocks (Claude Code tool calls) are included in the export
- Whether `thinking` blocks (extended thinking) are in the export
- Exact timestamp format and timezone (UTC assumed)
- Whether attachments/files are referenced or embedded
- File name of the JSON inside the ZIP (likely `conversations.json`)

### Ingest Script Strategy

The ingest script should:
1. Parse defensively — use `.get()` with defaults everywhere, never assume a field exists
2. Log every unknown field/type encountered for schema learning
3. Store the raw JSON blob per conversation alongside the extracted fields, so the schema can be re-queried without re-importing
4. Handle both `text` at message level and `text` inside `content[].text` — extract whichever is present

---

## Similar Tools / Prior Art

**Note:** WebSearch and most GitHub URLs were blocked during this research session. The following is based on confirmed public sources plus training knowledge. Confidence varies per item.

### OpenAI / ChatGPT History Export (HIGH confidence — documented format)

ChatGPT's export format is publicly documented and used by many open-source tools. It is the best analog for Claude.ai's format. Structure:

```json
[
  {
    "title": "conversation title",
    "create_time": 1700000000.0,
    "update_time": 1700000000.0,
    "conversation_id": "uuid",
    "mapping": {
      "node-uuid": {
        "id": "uuid",
        "message": {
          "id": "uuid",
          "author": { "role": "user | assistant | system | tool" },
          "create_time": 1700000000.0,
          "content": {
            "content_type": "text",
            "parts": ["message text here"]
          }
        },
        "parent": "parent-uuid",
        "children": ["child-uuid"]
      }
    }
  }
]
```

Key difference from Claude: ChatGPT uses a **tree structure** (mapping with parent/child) because branching conversations are supported. Claude.ai conversations are linear (no branching), so the export is likely a simple array of messages. This simplifies ingestion significantly.

### MCP Memory Server (Official Reference — HIGH confidence)

The official `@modelcontextprotocol/server-memory` exposes a knowledge-graph-based persistent memory. Tools it exposes (confirmed from MCP reference docs):
- `create_entities` — add nodes
- `create_relations` — add edges
- `search_nodes` — full-text search across entities
- `read_graph` — return full graph

Lesson for this project: Even the official memory server keeps search simple (one required `query` string, no complex filter parameters). Simpler tool signatures are better — the LLM can iterate with multiple calls rather than needing a complex single call.

### MCP Git Server (Official Reference — HIGH confidence from spec docs)

Exposes: `git_log`, `git_diff`, `git_search_code`, `git_read_file`, `git_status`, etc. Relevant lesson: It separates "search/list" tools from "get full content" tools. `git_log` returns commit summaries; `git_diff` returns full content for a specific commit. This is exactly the pattern this project uses (`search_conversations` returns snippets, `get_conversation` returns full content).

### Obsidian Smart Connections / Note Search MCP Servers (MEDIUM confidence)

Several community MCP servers for note search (Obsidian, Notion) follow a consistent pattern:
- `search_notes(query, limit?, tags?)` — returns list of {title, excerpt, last_modified, id}
- `get_note(id)` — returns full content
- `list_tags()` or `list_folders()` — enumerate filter options

This "search returns list, get returns full" two-tool pattern is the established idiom for document retrieval via MCP.

### ChatGPT History Viewer Projects (MEDIUM confidence)

Multiple open-source projects process ChatGPT exports for offline viewing. Common patterns they use:
- Extract all `parts` text from messages, concatenate for FTS indexing
- Store `create_time` as Unix timestamp, convert to ISO for display
- Index by conversation title + all message text
- Filter by date range and author role as the primary dimensions

---

## MCP Tool Design Patterns

Drawn from the official MCP specification (2025-11-25), SEP-986, and the FastMCP Python SDK build guide. All HIGH confidence.

### Tool Naming

Per SEP-986 (Final status, 2025-07-16): tool names should be 1-64 characters, case-sensitive, using `[a-zA-Z0-9_\-./]`. No spaces or commas. Convention in the wild is `snake_case` for Python servers. The project's existing names (`search_conversations`, `list_projects`, `get_conversation`) are well-formed.

**Recommendation:** Keep `snake_case` throughout. Add `get_stats` as a fourth tool.

### FastMCP Decorator Pattern

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("claude-history")

@mcp.tool()
async def search_conversations(
    query: str,
    project: str | None = None,
    role: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 10,
    include_full_content: bool = False,
) -> str:
    """Search past Claude conversations by full-text query.

    Args:
        query: Full-text search query. Supports FTS5 syntax:
               phrases in quotes ("exact phrase"), prefix search (term*),
               boolean operators (AND, OR, NOT).
        project: Filter to a specific project name. Omit to search all projects.
        role: Filter matches by message author. One of: human, assistant, all.
              Default: all (matches in any message).
        after: Return only conversations updated after this date (YYYY-MM-DD).
        before: Return only conversations updated before this date (YYYY-MM-DD).
        limit: Maximum results to return. Default: 10. Maximum: 50.
        include_full_content: If true, include all messages in each result.
                              Default: false (returns snippets only).
    """
```

FastMCP uses type hints to generate the JSON Schema automatically and docstrings for the tool description. The Args block in the docstring maps to individual parameter descriptions in the schema.

### Return Shape: Snippets-First (Recommended)

Return as a JSON-serialized string (for backward compatibility) AND as `structuredContent`. Per the MCP spec, when returning structured content, also include the serialized JSON in a TextContent block:

```python
import json

result = {
    "total_matches": 47,
    "returned": 10,
    "results": [
        {
            "conversation_id": "uuid",
            "title": "Docker networking troubleshooting",
            "project": "DevOps",
            "created_at": "2025-12-01T14:32:00Z",
            "updated_at": "2025-12-15T09:11:00Z",
            "snippet": "...<<<Docker>>> bridge network was causing <<<port>>> conflicts on...",
            "messages": []  # populated only when include_full_content=True
        }
    ]
}
return json.dumps(result, indent=2)
```

### Tool Count: Keep It Small

The official Memory server has ~5 tools. The Git server has ~10. For this domain, 4 tools is the right number — each call is cheap (SQLite is fast) so the LLM can iterate. Do not combine concerns into one "mega-tool" with many optional parameters; it confuses tool selection.

Recommended final tool set:
1. `search_conversations(query, project?, role?, after?, before?, limit?, include_full_content?)` — primary search
2. `list_projects()` — enumerate projects with counts
3. `get_conversation(id)` — full content retrieval
4. `get_stats()` — total counts, date range, project summary

### Error Handling

Per MCP spec, use `isError: true` for tool execution errors (bad input, DB not found) — not Python exceptions which become protocol errors. FastMCP handles this via returning a string; for errors, raise a `ValueError` or return an error dict. The LLM receives the error text and can self-correct.

### STDIO vs HTTP Transport

Per the build guide, this server uses `mcp.run(transport="stdio")` — STDIO transport. This means:
- Never write to stdout (use `sys.stderr` for logging, or Python's `logging` module)
- Task Scheduler launches the process; Claude Code manages the subprocess lifecycle
- No port management required

### Snippet Token Budget

FTS5 `snippet()` accepts 1-64 tokens. For LLM consumption, 32 tokens (approximately 24 words) is the sweet spot — enough context to assess relevance without burning context window budget. Use `<<<` and `>>>` as highlight markers (distinctive, low ASCII character overhead).

```sql
snippet(conversations_fts, 2, '<<<', '>>>', ' ... ', 32)
-- col index 2 = the indexed message text column
```
