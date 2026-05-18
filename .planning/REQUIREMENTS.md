# Requirements: Claude History MCP Server

**Defined:** 2026-05-16
**Milestone:** v1.1 — Search & Ingest Improvements
**Core Value:** Any Claude Code session can search past conversations and retrieve relevant context with a single tool call.

## v1.1 Requirements

### Search Enhancements

- [x] **SRCH-01**: User can filter `search_conversations` results to a date range via optional `date_from` and `date_to` parameters (ISO date strings; either or both may be omitted)
- [x] **SRCH-02**: User can filter `search_conversations` results to messages from a specific sender role via optional `role_filter` parameter ("human" or "assistant")

### Export

- [x] **EXP-01**: User can export a conversation to a local markdown file by passing an optional `file_path` parameter to `export_conversation`; tool returns the written path on success

### Ingest

- [ ] **ATTACH-01**: User can ingest a ZIP containing PDF attachments and have the extracted text content indexed and searchable alongside message text
- [x] **INGEST-01**: User can re-run ingest on an updated ZIP and have new messages appended to existing conversations rather than the entire conversation being silently skipped

## Future Requirements

Nothing deferred — all v1.0 deferred items are included in v1.1.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated Claude.ai export download | No API available; manual export is deliberate |
| Semantic / vector search | FTS5 + BM25 sufficient at personal history scale |
| Full-text re-index of existing messages | No use case; existing messages are immutable |
| Web UI | Claude Code is the interface |
| Write operations via MCP | Read-only server by design |
| Multi-machine sync | Local personal tool; no network exposure needed |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SRCH-01 | Phase 5 | Complete |
| SRCH-02 | Phase 5 | Complete |
| EXP-01 | Phase 5 | Complete |
| ATTACH-01 | Phase 6 | Deferred (out of v1.1 scope) |
| INGEST-01 | Phase 6 | Complete |

**Coverage:**
- v1.1 requirements: 5 total
- Mapped to phases: 5
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-16*
*Last updated: 2026-05-18 — INGEST-01 complete (06-01); SRCH-01, SRCH-02, EXP-01 complete (05-01)*
