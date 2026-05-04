# Requirements: Claude History MCP Server

**Defined:** 2026-05-03
**Core Value:** Any Claude Code session can search past conversations and retrieve relevant context with a single tool call.

## v1 Requirements

### Ingestion

- [x] **INGEST-01**: User can run a schema discovery script against a Claude.ai export ZIP that prints the JSON field structure without modifying the database
- [ ] **INGEST-02**: User can run the ingest script against a Claude.ai export ZIP to load all conversations and messages into SQLite
- [ ] **INGEST-03**: Re-running ingest on the same or updated export does not create duplicate conversations (INSERT OR REPLACE on conversation UUID)
- [ ] **INGEST-04**: Ingest script skips conversations already in the database when running incrementally (only processes newer conversations)
- [ ] **INGEST-05**: Ingest script indexes content of text and code attachments (.txt, .py, .js, .md, etc.) alongside conversation messages; skips binary files gracefully

### Database

- [ ] **DB-01**: SQLite database uses FTS5 virtual table with trigram tokenizer enabling fuzzy/typo-tolerant search
- [ ] **DB-02**: FTS5 table uses content table pattern (no duplicate text storage) with BEFORE DELETE / AFTER INSERT triggers to stay in sync
- [ ] **DB-03**: Database uses WAL journal mode to allow concurrent reads during ingest
- [ ] **DB-04**: Schema stores conversations (id, title, project, created_at, message_count) and messages (id, conversation_id, role, content, position, created_at)

### MCP Tools

- [ ] **TOOL-01**: `search_conversations(query, project_filter?)` returns matching conversations with BM25-ranked snippets, title, project, date, and match count
- [ ] **TOOL-02**: `search_conversations` accepts `include_full_content=true` flag to return complete message text instead of snippets
- [ ] **TOOL-03**: `get_conversation(id)` returns full conversation content formatted as labeled turns (Human/Assistant)
- [ ] **TOOL-04**: `list_projects()` returns all project names with conversation counts and date ranges
- [ ] **TOOL-05**: `get_stats()` returns total conversation count, total message count, date range of indexed data, and database file size
- [ ] **TOOL-06**: `export_conversation(id, format?)` returns the conversation formatted as a markdown string suitable for pasting or summarizing

### Server & Integration

- [x] **SETUP-01**: Project is structured as a uv package with `pyproject.toml`, entry points for `server` and `ingest` commands
- [ ] **SETUP-02**: Server uses FastMCP with stdio transport; all logging goes to stderr; stdout is never written to directly
- [ ] **SETUP-03**: MCP server is registered with Claude Code via `claude mcp add --scope user --transport stdio` so it is available in every session
- [x] **SETUP-04**: `.gitignore` excludes the SQLite database file and any Claude.ai export ZIPs (contain personal conversation history)
- [ ] **SETUP-05**: README documents installation steps, ingest workflow, and Claude Code registration command

## v2 Requirements

### Search Enhancements

- **SRCH-01**: `search_conversations` supports `date_from` / `date_to` parameters for date range filtering
- **SRCH-02**: `search_conversations` supports `role_filter` parameter to search only human or assistant turns

### Export Enhancements

- **EXP-01**: `export_conversation` can optionally write the markdown to a file at a user-specified path

### Attachments

- **ATTACH-01**: Ingest script indexes content of PDF attachments (requires third-party PDF parser)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated Claude.ai export download | Claude.ai has no export API; requires manual action in account settings |
| Scheduled/automatic re-ingestion | Manual ingest after each export is deliberate — simpler, no background process |
| Remote access / multi-machine | Personal local tool; no network exposure needed |
| Vector / semantic search | Significant complexity (local model or API); FTS5 + trigram handles personal-history use case |
| Web UI | Claude Code is the interface |
| Write operations to Claude.ai | Read-only tool; no upstream API exists |
| Task Scheduler auto-start | stdio transport means Claude Code spawns the server on demand — no persistent process |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 1 | Complete |
| INGEST-02 | Phase 2 | Pending |
| INGEST-03 | Phase 2 | Pending |
| INGEST-04 | Phase 2 | Pending |
| INGEST-05 | Phase 2 | Pending |
| DB-01 | Phase 2 | Pending |
| DB-02 | Phase 2 | Pending |
| DB-03 | Phase 2 | Pending |
| DB-04 | Phase 2 | Pending |
| TOOL-01 | Phase 3 | Pending |
| TOOL-02 | Phase 3 | Pending |
| TOOL-03 | Phase 3 | Pending |
| TOOL-04 | Phase 3 | Pending |
| TOOL-05 | Phase 3 | Pending |
| TOOL-06 | Phase 3 | Pending |
| SETUP-01 | Phase 1 | Complete |
| SETUP-02 | Phase 3 | Pending |
| SETUP-03 | Phase 4 | Pending |
| SETUP-04 | Phase 1 | Complete |
| SETUP-05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20/20 ✓
- Unmapped: 0

---
*Requirements defined: 2026-05-03*
*Last updated: 2026-05-03 — traceability populated after roadmap creation*
