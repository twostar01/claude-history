# Pitfalls Research: Claude History MCP Server

**Researched:** 2026-05-03
**Confidence:** HIGH for MCP SDK and FTS5 (official docs). MEDIUM for Windows Task Scheduler and export parsing (training data + community patterns, no official verification available).

---

## MCP SDK Pitfalls

### Critical: stdout contamination silently breaks the server

**What goes wrong:** Any write to stdout — including `print()`, uncaught exceptions printed by the runtime, or third-party libraries that log to stdout — corrupts the JSON-RPC message stream. The client receives malformed JSON and either drops the connection or silently fails tool calls.

**Why it happens:** The stdio transport uses stdout exclusively for JSON-RPC framing. It is not a general-purpose logging channel. The Python runtime itself will print unhandled exception tracebacks to stdout by default unless you redirect them.

**Prevention:**
- Configure logging at the top of the server module before any other imports: `logging.basicConfig(stream=sys.stderr, level=logging.WARNING)`
- Never use bare `print()`. Use `print(..., file=sys.stderr)` if you must.
- Wrap the `mcp.run()` call in a try/except that logs to stderr: unhandled exceptions that escape to the Python runtime will otherwise print to stdout and crash the session invisibly.
- Test with the MCP Inspector (npx @modelcontextprotocol/inspector) before connecting to Claude Code. It makes stdout corruption obvious immediately.

**Source:** Official MCP quickstart and debugging docs — "Never write to stdout. Writing to stdout will corrupt the JSON-RPC messages and break your server."

---

### Critical: relative paths in MCP config cause working-directory confusion

**What goes wrong:** When Claude Code (or Claude Desktop) spawns the MCP server subprocess, the working directory is undefined — it could be `/`, `C:\`, or wherever the host application was launched from. Relative paths in `mcp-servers` config entries for `command`, database file, or log file locations will silently point to the wrong place.

**Why it happens:** The MCP client launches the server as a subprocess; it does not `cd` into the project directory first.

**Prevention:**
- Use absolute paths everywhere in `claude_desktop_config.json` / Claude Code MCP config: both for the `command` field and for any path arguments passed to the server.
- Inside the server, resolve the database path relative to `__file__` (the server script itself), not `os.getcwd()`.
- On Windows, remember that JSON requires double-backslash (`C:\\Users\\...`) or forward slashes (`C:/Users/...`).

**Source:** Official MCP debugging docs — "Always use absolute paths in your configuration and .env files."

---

### Significant: environment variables are not inherited

**What goes wrong:** The MCP server subprocess inherits only a limited subset of environment variables. Variables set in your terminal session (PATH modifications, PYTHONPATH, virtual env activation) may not be present.

**Why it happens:** The host application was not launched from a shell with your full profile. On Windows this is especially pronounced — the GUI launcher has a minimal environment.

**Prevention:**
- Do not rely on environment variables being present. Hard-code the Python interpreter path to the venv's Python binary (e.g., `.venv\Scripts\python.exe`) as the `command` in MCP config rather than relying on `python` resolving correctly.
- If you need env vars, pass them explicitly via the `env` key in the MCP server config:
  ```json
  {
    "mcpServers": {
      "claude-history": {
        "command": "C:\\path\\to\\.venv\\Scripts\\python.exe",
        "args": ["C:\\path\\to\\server.py"],
        "env": { "DB_PATH": "C:\\path\\to\\history.db" }
      }
    }
  }
  ```
- On Windows, `%APPDATA%` variable expansion does not happen in MCP config JSON — you must use the literal expanded path. There is a documented bug where `${APPDATA}` appears verbatim in paths instead of being expanded; the fix is to put the expanded value in the `env` block explicitly.

**Source:** Official MCP debugging docs — environment variables section and ENOENT / `${APPDATA}` accordion.

---

### Moderate: tool return shapes that confuse LLMs

**What goes wrong:** Tools that return raw Python dicts, lists, or complex nested structures get serialized to JSON and passed back as a text content block. The LLM sees a JSON blob with no structure hints. This causes the LLM to misinterpret fields, miss results at the bottom of long lists, or fail to follow up with `get_conversation()` when it should.

**Why it happens:** The MCP protocol's tool result `content` array is text by default. The LLM sees what the serialized text looks like, not a structured object.

**Prevention for search_conversations:**
- Return a short, human-readable text summary as the primary content, not raw JSON. Format each result as a labeled block: title, date, project, snippet — separated by `---`.
- Keep total character count bounded. If `include_full_content=False` (the default), strip message text down to snippet only. Full conversation retrieval belongs in `get_conversation()`.
- If a query returns zero results, return an explicit "No conversations matched." message — never return an empty list silently. The LLM may retry with a different tool if it gets silence.
- Avoid deeply nested return shapes. Flatten to a list of records.

**Prevention for get_conversation:**
- When returning full content, structure it clearly: conversation metadata first, then messages in order, each labeled with role and timestamp.
- Consider truncating very long messages (e.g., >2000 chars) with a note like `[truncated — 8450 chars]` to prevent context window overflow.

**Source:** MCP tools spec — tool results use a `content` array of typed blocks; no automatic structured rendering in LLM context. Training data patterns for MCP tool design.

---

### Moderate: exception handling — raise vs return isError

**What goes wrong:** If the tool handler raises an unhandled Python exception, the Python MCP SDK converts it to a protocol-level JSON-RPC error. Claude Code surfaces this as a connection error or a generic "tool call failed" message with no actionable detail.

**Prevention:**
- Catch expected errors (database not found, bad query syntax, missing conversation ID) inside the tool handler and return them as tool execution errors: return a text content block with a clear message and set `isError=True`.
- Only let truly unexpected errors propagate (they will be caught by the SDK and returned as protocol errors, which is acceptable for bugs).
- Log all errors to stderr with stack traces for post-mortem debugging.

**Source:** MCP tools spec — two error reporting mechanisms: protocol errors vs. tool execution errors with `isError: true`.

---

### Minor: MCP server must be restarted to pick up code changes

**What goes wrong:** Claude Code caches the server connection. Editing server code and expecting it to take effect immediately does not work — the old process is still running.

**Prevention:** After any server code change, fully restart Claude Code (or whatever MCP host you're using). Closing the chat window is not enough for Claude Desktop; you must quit the application.

**Source:** Official MCP debugging docs — "Server code changes: Restart the client."

---

## SQLite FTS5 Pitfalls

### Critical: stdout/stderr from sqlite3 module can't corrupt MCP, but schema mistakes are permanent

**What goes wrong:** If you create the FTS5 virtual table with the wrong schema (wrong tokenizer options, wrong column list), you cannot `ALTER TABLE` it. You must `DROP` the virtual table and recreate it, which destroys the index. The content table (conversations) is unaffected, but you lose the FTS index and must rebuild from scratch.

**Prevention:** Get the schema right before ingesting data. Pin the tokenizer config in a constants file and test it before first production use.

---

### Critical: any `print()` / debug output inside the server that reaches stdout

Already covered above in MCP SDK pitfalls. SQLite errors can sometimes generate output — ensure sqlite3 error handling is wrapped correctly and logs to stderr.

---

### Significant: unicode61 tokenizer separator defaults break technical content

**What goes wrong:** The default unicode61 tokenizer treats hyphens and underscores as separators (word boundaries). This means `search_conversations` tokenizes as `search` + `conversations`. Code identifiers, snake_case function names, and hyphenated terms will not match as whole tokens.

**Why it happens:** Unicode 6.1 classifies hyphens and underscores as punctuation (separators), not letters.

**Prevention:**
```sql
CREATE VIRTUAL TABLE conversations_fts USING fts5(
    title, content,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '-_'"
);
```
This keeps hyphens and underscores as part of tokens, so `search_conversations` remains one token and matches queries for that exact string. Tradeoff: hyphenated phrases like "well-known pattern" must be queried with quotes or with underscores.

**Confidence:** HIGH — confirmed in official FTS5 docs.

---

### Significant: `remove_diacritics=1` is a documented bug

**What goes wrong:** The default `remove_diacritics=1` setting fails to strip diacritics from codepoints that encode multiple diacritics in a single codepoint (e.g., U+1ED9 "LATIN SMALL LETTER O WITH CIRCUMFLEX AND DOT BELOW"). Searches for the ASCII base character miss these.

**Prevention:** Always use `remove_diacritics=2`:
```sql
tokenize = "unicode61 remove_diacritics 2"
```
This is the correct setting. The official SQLite docs acknowledge this is a bug kept for backwards compatibility.

**Confidence:** HIGH — cited verbatim in official FTS5 docs.

---

### Significant: snippet() token limit is hard-capped at 64

**What goes wrong:** The 5th argument to `snippet()` (the token count) must be between 1 and 64. Passing anything larger raises a runtime error, not a schema error — it will crash tool calls at query time.

**Prevention:** Always pass a value <= 64. A value of 32–48 is good for snippet previews that fit comfortably in LLM context.

```sql
SELECT snippet(conversations_fts, 0, '[', ']', '...', 40) FROM conversations_fts WHERE ...
```

**Confidence:** HIGH — confirmed in official FTS5 docs.

---

### Significant: column index in snippet() is 0-based, -1 means auto-select

**What goes wrong:** If you search across multiple columns (e.g., `title` column 0 and `content` column 1) and pass `-1` to `snippet()`, it auto-selects the best column. But if you always want the content snippet regardless of where the match scored highest, passing `-1` can silently return a title snippet that's only 5 words long.

**Prevention:** Pass column index `1` explicitly to always get a content snippet, and separately format the title from the result row.

---

### Significant: short queries (under 3 characters) return no FTS results

**What goes wrong:** FTS5 with the unicode61 tokenizer ignores query terms shorter than 3 characters. A search for `"AI"` or `"js"` or `"go"` silently returns zero results.

**Prevention:**
- Validate query length in the `search_conversations` tool handler. If the cleaned query is fewer than 3 characters, return an informative message: "Query too short for full-text search — please use 3 or more characters."
- Consider falling back to a `LIKE '%term%'` query on the content table for very short terms, with a clear warning that it will be slow.

**Confidence:** HIGH — confirmed in official FTS5 docs.

---

### Significant: FTS5 prefix queries with `*` must be outside quotes

**What goes wrong:** Writing `'\"term*\"'` (asterisk inside quotes) passes the `*` to the tokenizer, which discards it. The result is an exact match query on `term*` (which matches nothing) rather than a prefix query.

**Prevention:**
- Prefix queries: `MATCH 'term*'` — asterisk outside quotes.
- For user-supplied search strings, don't try to add wildcard behavior automatically. If the user types a full word, FTS5 already handles stemming-adjacent fuzzy matching. If you want prefix behavior, append `*` programmatically: `query_term + '*'`, but only if the query doesn't already contain FTS5 operators.

---

### Significant: bm25() ranking requires columnsize data — don't use `columnsize=0`

**What goes wrong:** Setting `columnsize=0` saves disk space by not storing document size data, but makes `bm25()` ranking extremely slow — it must re-tokenize every document on the fly to calculate sizes.

**Prevention:** Do not use `columnsize=0`. For a personal history database the disk savings are trivial (a few MB at most), and ranking quality matters for search UX.

---

### Moderate: external content table sync — triggers must be set up before first insert

**What goes wrong:** If you create the FTS5 virtual table as a content table pointing at the `conversations` table (using `content='conversations'`), but set up triggers after data is already inserted, the FTS index will be empty for all existing rows.

**Prevention:** Either:
1. Create the FTS table with triggers before ingesting any data, then ingest.
2. Or: create FTS with triggers, ingest data, then call `INSERT INTO conversations_fts(conversations_fts) VALUES('rebuild')` to sync existing rows.

The rebuild is safe and will be fast for thousands of conversations.

---

### Moderate: re-ingest leaves orphan FTS entries if you don't clean up correctly

Covered in the Re-ingestion section below.

---

### Minor: FTS5 table `optimize` — run after bulk ingest

**What goes wrong:** During bulk insert, FTS5 accumulates multiple b-tree segments. Queries work but are slower because they scan multiple segments. This doesn't matter much for reads during normal use, but it's unnecessary overhead.

**Prevention:** After bulk ingest completes, run:
```sql
INSERT INTO conversations_fts(conversations_fts) VALUES('optimize');
```
This merges all segments into one for fastest query performance. Add this as the last step of the ingest script.

---

## Windows / Task Scheduler Pitfalls

**Confidence:** MEDIUM — based on well-known Windows patterns; official Task Scheduler + Python interaction docs are sparse.

### Critical: Task Scheduler does not activate virtual environments

**What goes wrong:** A scheduled task that runs `python server.py` uses whatever Python is on the system PATH — which may not be the venv Python, may not have `mcp` installed, and may be a different version. The task fails silently or crashes with `ModuleNotFoundError`.

**Prevention:**
- Point the scheduled task's `Program/script` directly at the venv Python binary: `C:\Users\nclem\Claude Code\claude-history\.venv\Scripts\python.exe`
- Set `Arguments` to the absolute path of `server.py`: `"C:\Users\nclem\Claude Code\claude-history\server.py"`
- Never run `cmd.exe /c activate && python server.py` — `activate` is not a standalone executable; it is a batch script that modifies the current shell session. It does not work as a scheduled task command.

---

### Critical: Task Scheduler working directory defaults to `C:\Windows\System32`

**What goes wrong:** If the `Start in` field of the scheduled task is left blank or wrong, the working directory is `C:\Windows\System32`. Any relative path in the server code (log files, database path resolution based on `os.getcwd()`) will silently target the wrong location.

**Prevention:**
- Set the `Start in (optional)` field to the project root directory.
- Additionally, resolve all paths in server code relative to `Path(__file__).parent`, not `os.getcwd()`. This makes the server working-directory-independent.

---

### Significant: Task Scheduler "Run only when user is logged on" vs "Run whether user is logged on or not"

**What goes wrong:** If set to "Run whether user is logged on or not," the task runs in a non-interactive session with no access to the user's display. This is fine for a headless MCP server, but it also means the session has a minimal environment and no access to user-specific credential stores. For this project (read-only SQLite, no external auth), this is usually fine.

**Prevention:** For this project, "Run only when user is logged on" is the safer and simpler choice — the server is only needed when you're actively using Claude Code anyway. Boot-on-login is sufficient.

---

### Significant: Windows paths with spaces in Task Scheduler

**What goes wrong:** The path `C:\Users\nclem\Claude Code\claude-history\server.py` contains a space ("Claude Code"). Without quoting, Task Scheduler may split this at the space and pass `Code\claude-history\server.py` as an argument.

**Prevention:**
- In the Task Scheduler `Arguments` field, wrap paths with spaces in double quotes: `"C:\Users\nclem\Claude Code\claude-history\server.py"`
- In MCP config JSON, use double-backslash: `"C:\\Users\\nclem\\Claude Code\\claude-history\\server.py"`

---

### Significant: Windows console encoding defaults break Unicode output

**What goes wrong:** On Windows, the default console encoding is often `cp1252` (Windows-1252) rather than UTF-8. If the server writes any non-ASCII characters to stderr (e.g., conversation titles with accented characters, emojis), the logging output may fail with `UnicodeEncodeError` or produce garbled text.

**Why it matters here:** The MCP server processes conversation history that almost certainly contains non-ASCII content (code snippets with Unicode, names, foreign language text).

**Prevention:**
- At server startup, force UTF-8 output: `sys.stderr.reconfigure(encoding='utf-8')` (Python 3.7+)
- Set the `PYTHONUTF8=1` environment variable in the MCP server config's `env` block. This forces UTF-8 mode globally.
- Set `PYTHONIOENCODING=utf-8` as well for belt-and-suspenders protection.

---

### Significant: SQLite file locking on Windows

**What goes wrong:** Windows file locking is more aggressive than on Linux/macOS. If the ingest script and the MCP server both have the SQLite database open simultaneously (e.g., you run the ingest script while Claude Code is using the server), you may hit `database is locked` errors.

**Why it happens:** SQLite uses file-level locking. On Windows, exclusive write locks block all readers, unlike WAL mode behavior.

**Prevention:**
- Use WAL (Write-Ahead Logging) mode: `PRAGMA journal_mode=WAL;` — this allows concurrent reads during writes on Windows.
- In the ingest script, open with a reasonable busy timeout: `connection.execute('PRAGMA busy_timeout=5000')` — waits up to 5 seconds before failing with a lock error.
- Keep the ingest script connection open only for the duration of the ingest, not persistently.

---

### Moderate: Task Scheduler trigger on "At startup" fires before network is up

**What goes wrong:** If the MCP server depends on any network resources (this project does not — it's SQLite-only), a startup trigger may fire too early. For this project this is a non-issue, but worth noting if the design ever adds network dependencies.

---

### Minor: PowerShell execution policy may block `.ps1` helper scripts

**What goes wrong:** If any helper script (ingest, setup) is written as a `.ps1` PowerShell script, the default Windows execution policy (`Restricted`) blocks it from running.

**Prevention:** Write helper scripts as `.bat` or `.cmd` files, or instruct users to run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. For this project, plain Python scripts avoid this entirely.

---

## Export Parsing Pitfalls

**Confidence:** MEDIUM — Claude.ai export format is not officially documented. Based on: (1) community reverse-engineering reports, (2) known patterns from similar AI export formats, (3) general JSON parsing pitfalls. The PROJECT.md explicitly states "Exact schema TBD — user will provide the export file when ready."

### Critical: the schema is unknown until you have the export file

**What goes wrong:** Building the ingest script against an assumed schema that turns out to be wrong wastes the entire ingest implementation.

**Prevention:**
- Write the first version of the ingest script to be schema-discovery-first: load the JSON, print the top-level keys, then sample one conversation object. Do not assume field names.
- Build schema validation early: verify required fields exist before processing. Raise clear errors for missing fields rather than silently producing empty records.
- The ingest script should be written to fail fast with a descriptive error if the schema doesn't match expectations.

---

### Significant: export is likely a ZIP containing multiple files

**What goes wrong:** Claude.ai exports (like many services) likely deliver a ZIP file containing `conversations.json` plus possibly `projects.json`, `attachments/`, and other assets. Code that tries to read the export as a single JSON file will fail.

**Known pattern:** The ZIP typically contains:
- `conversations.json` — all conversation metadata and message content
- Possibly `projects.json` — project metadata
- Possibly an `attachments/` directory with file uploads

**Prevention:**
- Detect the format: if the export path ends in `.zip`, unzip to a temp directory first. Accept both ZIP and extracted-directory inputs.
- Use Python's `zipfile` module — it is in the stdlib and has no external dependencies.
- Do not assume the JSON file is at the root of the ZIP; use `zipfile.namelist()` to find it.

---

### Significant: conversation messages may have multiple content types

**What goes wrong:** Claude conversations can contain text, tool use, tool results, image attachments, and document attachments. Naive concatenation of message content will either crash (if content is a list of typed objects rather than a plain string) or produce garbled FTS content (tool use JSON blobs mixed into conversation text).

**Known pattern from similar exports:** Message content is often structured as:
```json
{
  "role": "human",
  "content": [
    { "type": "text", "text": "Here is the file..." },
    { "type": "document", "source": {...} }
  ]
}
```
Or in simpler exports:
```json
{
  "role": "human",
  "content": "plain text string"
}
```
Both patterns may appear in the same export file.

**Prevention:**
- Write a `extract_text(content)` helper that handles both cases:
  - If `content` is a string: return it directly.
  - If `content` is a list: concatenate only `type == "text"` items; skip tool_use, tool_result, image, document blocks.
- Index only human-readable text into FTS. Tool use JSON and base64 image data should not go into the FTS index.

---

### Significant: large export files may not fit in memory if loaded with json.load()

**What goes wrong:** A user with years of Claude conversations may have a `conversations.json` file of several hundred MB to over 1 GB. `json.load()` on a file that size will either be very slow or OOM on machines with limited RAM.

**Prevention:**
- For the initial implementation, `json.load()` is fine — test it first.
- If performance is a problem, switch to `ijson` (streaming JSON parser) for the conversations array. However, `ijson` requires an extra dependency.
- A practical middle ground: load the file, then process conversations in batches of 100, committing after each batch. This reduces peak memory somewhat.

---

### Significant: `conversations.json` contains all projects; filtering must be done in code

**What goes wrong:** If the export groups all conversations together regardless of project, the ingest script must extract project associations from the conversation objects rather than from a separate project file.

**Prevention:** When ingesting, always capture the project identifier (whatever field name it uses — likely `project_id`, `project_name`, or `workspace_id`) from each conversation and store it in a `project` column in the conversations table. This enables the `project_filter` parameter in `search_conversations`.

---

### Moderate: conversation and message IDs may be UUIDs or opaque strings

**What goes wrong:** If you use conversation IDs as SQLite primary keys and the export uses UUIDs (e.g., `"550e8400-e29b-41d4-a716-446655440000"`), these are long strings that make debugging harder and queries marginally slower than integer IDs.

**Prevention:** Store the export-provided UUID as a `TEXT` column (the natural key). Use a separate `INTEGER PRIMARY KEY` rowid for SQLite internal use and FTS5 `content_rowid`. SQLite's rowid is implicit and free; no need to invent a separate integer key explicitly.

---

### Moderate: timestamps may be in multiple formats

**What goes wrong:** Timestamps in the export may be ISO 8601 strings, Unix epoch integers, or JavaScript-style millisecond epoch values. Inconsistency within the same export is possible if the format evolved over time.

**Prevention:**
- Normalize all timestamps to Unix epoch (integer seconds) before storing.
- Write a `parse_timestamp(value)` helper that detects and handles all three formats.
- Store as `INTEGER` in SQLite (epoch seconds) — this makes date range queries simple: `WHERE created_at > ?`.

---

### Minor: conversation titles may be null or empty for untitled conversations

**What goes wrong:** Some conversations may have no title (null, empty string, or a generic auto-generated one). If FTS indexes the title column, null values will be stored as empty tokens. Queries that happen to match a conversation with a null title will have no useful snippet from the title field.

**Prevention:**
- Coalesce null titles to an empty string before storing: `title = conversation.get('name') or ''`
- In `snippet()`, use column -1 (auto-select) or explicitly fall back to the content column if the title is empty.

---

## Re-ingestion / Deduplication Pitfalls

### Critical: inserting the same conversation twice creates duplicate FTS entries

**What goes wrong:** If the user downloads a new export and reruns the ingest script without clearing old data, every conversation from the previous export gets a second row in the content table and a second FTS entry. Search results return duplicates. `get_conversation(id)` may return the wrong row if ID lookup is ambiguous.

**Why FTS5 makes this worse:** FTS5 has no concept of "update" — it only has insert and delete. An `UPDATE` on an external content table does not automatically update the FTS index. A `DELETE + INSERT` on the content table without corresponding FTS operations leaves stale FTS entries pointing at deleted rows.

**Prevention — recommended approach: full replace on conflict**

Use `INSERT OR REPLACE INTO conversations (...) VALUES (...)` with the conversation UUID as a UNIQUE constraint. This handles the content table automatically. For the FTS table, use triggers:

```sql
-- Before delete trigger removes old FTS entry
CREATE TRIGGER conversations_bd BEFORE DELETE ON conversations BEGIN
    DELETE FROM conversations_fts WHERE rowid = old.rowid;
END;

-- After insert trigger adds new FTS entry
CREATE TRIGGER conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;
```

With `INSERT OR REPLACE`, SQLite internally deletes the old row then inserts the new one. The `BEFORE DELETE` trigger fires and removes the old FTS entry. The `AFTER INSERT` trigger fires and adds the new FTS entry. No duplicates.

**Alternative approach: delete-and-rebuild**

Simpler but slower for large histories: at the start of each ingest, `DELETE FROM conversations` (triggers clean up FTS) and then insert fresh. For a personal history database this is fine — ingest will take seconds to a few minutes at most.

---

### Significant: FTS5 external content table — delete order matters

**What goes wrong:** If you delete from the content table (`conversations`) before deleting from the FTS table (`conversations_fts`), the FTS delete operation tries to read the content table to determine what to de-index — but the row is already gone. This causes incorrect FTS index state.

**Prevention:** Always update/delete FTS before the content table. Triggers handle this automatically if set up correctly (use `BEFORE DELETE` for FTS cleanup).

---

### Significant: partial ingest failure leaves inconsistent state

**What goes wrong:** If the ingest script crashes midway through (OOM, keyboard interrupt, disk full), the database will have some conversations from the new export but not others. The FTS index will be partially updated. Re-running the ingest must be idempotent.

**Prevention:**
- Wrap the entire ingest in a single database transaction: `BEGIN TRANSACTION` at the start, `COMMIT` at the end.
- If the script crashes, SQLite rolls back the transaction automatically — the database returns to the pre-ingest state.
- The `INSERT OR REPLACE` approach ensures re-running the script on a partial result is safe: already-ingested conversations are replaced, not duplicated.

---

### Moderate: conversation count drift between exports

**What goes wrong:** A new export may contain fewer conversations than expected if Claude.ai deleted conversations server-side (due to retention policies or user deletion). If the ingest only adds new rows (INSERT OR IGNORE), deleted conversations remain in the local database and appear in search results indefinitely.

**Prevention (optional):** After each ingest, compare the set of conversation UUIDs in the new export against those in the local database. Delete local records whose UUIDs are absent from the new export. This is a soft delete / sync pattern.

For the initial implementation, this is out of scope — the PROJECT.md says ingest is a simple manual script. Flag this as a known gap.

---

### Minor: ingesting while the MCP server is running

Already covered in Windows pitfalls (SQLite file locking). Use WAL mode and busy_timeout. Do not attempt to restart the MCP server mid-ingest.

---

## Phase Mapping

| Pitfall | Severity | Recommended Phase |
|---------|----------|-------------------|
| stdout contamination kills MCP server | Critical | Phase 1 (server scaffolding) — address before anything else |
| Absolute paths in MCP config | Critical | Phase 1 (server scaffolding) — wire up config correctly from the start |
| Environment variable inheritance | Significant | Phase 1 (server scaffolding) |
| Tool return shapes for LLM consumption | Significant | Phase 2 (tool implementation) — design before implementation, not after |
| Exception handling strategy | Moderate | Phase 2 (tool implementation) |
| FTS5 schema design (tokenizer options) | Critical | Phase 2 (database + FTS setup) — must get right before first ingest |
| snippet() token limit cap | Significant | Phase 2 (database + FTS setup) |
| Short query rejection (<3 chars) | Significant | Phase 2 (tool implementation) |
| unicode61 separator defaults | Significant | Phase 2 (database + FTS setup) |
| remove_diacritics=2 | Significant | Phase 2 (database + FTS setup) |
| bm25 + columnsize | Moderate | Phase 2 (database + FTS setup) |
| FTS optimize after bulk ingest | Minor | Phase 3 (ingest script) |
| Task Scheduler venv path | Critical | Phase 4 (Windows startup) |
| Task Scheduler working directory | Critical | Phase 4 (Windows startup) |
| Windows path spaces in config | Significant | Phase 4 (Windows startup) |
| Windows console encoding (UTF-8) | Significant | Phase 1 or Phase 4 — add to server startup boilerplate |
| SQLite WAL mode for concurrent access | Significant | Phase 2 (database setup) |
| Export schema unknown — schema-first parsing | Critical | Phase 3 (ingest) — do schema discovery before writing parser |
| ZIP format detection | Significant | Phase 3 (ingest) |
| Multi-type message content handling | Significant | Phase 3 (ingest) |
| Large file memory pressure | Moderate | Phase 3 (ingest) — test with real file before optimizing |
| Timestamp normalization | Moderate | Phase 3 (ingest) |
| Deduplication / INSERT OR REPLACE | Critical | Phase 3 (ingest) — design before first write |
| Transaction wrapping for partial failure | Significant | Phase 3 (ingest) |
| FTS trigger setup before insert | Critical | Phase 2 (database setup) |
| FTS delete order (BEFORE DELETE) | Significant | Phase 2 (database setup) |
