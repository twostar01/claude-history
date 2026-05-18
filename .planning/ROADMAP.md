# Roadmap: Claude History MCP Server

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-05-06)
- 🚧 **v1.1 Search & Ingest Improvements** — Phases 5–6 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–4) — SHIPPED 2026-05-06</summary>

- [x] Phase 1: Scaffolding + Schema Discovery (3/3 plans) — completed 2026-05-04
- [x] Phase 2: Database + Ingest (2/2 plans) — completed 2026-05-05
- [x] Phase 3: MCP Tools (2/2 plans) — completed 2026-05-05
- [x] Phase 4: Integration + README (1/1 plan) — completed 2026-05-06

See [v1.0 Roadmap Archive](milestones/v1.0-ROADMAP.md) for full phase details.

</details>

### 🚧 v1.1 Search & Ingest Improvements (In Progress)

**Milestone Goal:** Fill the gaps left by v1.0 — richer search filtering, correct incremental ingest, file export, and PDF attachment support.

- [x] **Phase 5: Search Filters + Export** - Add date/role filters to search_conversations and file-write capability to export_conversation — completed 2026-05-16
- [ ] **Phase 6: Ingest Improvements** - Incremental message append for existing conversations and PDF attachment text indexing

## Phase Details

### Phase 5: Search Filters + Export
**Goal**: Users can narrow search results by date range and sender role, and can export a conversation directly to a markdown file
**Depends on**: Phase 4
**Requirements**: SRCH-01, SRCH-02, EXP-01
**Success Criteria** (what must be TRUE):
  1. User can call `search_conversations` with `date_from` and/or `date_to` (ISO date strings) and receive only results within that window
  2. User can call `search_conversations` with `role_filter="human"` or `role_filter="assistant"` and receive only results from messages sent by that role
  3. User can call `export_conversation` with a `file_path` argument and find a valid markdown file written to that path
  4. All three parameters are optional — existing calls with no new arguments continue to work identically
**Plans**: 1 plan
Plans:
- [x] 05-01-PLAN.md — Extend search.py (role/date filters) and server.py (tool wrappers + export file write)

### Phase 6: Ingest Improvements
**Goal**: Users can re-run ingest on an updated export and get new messages indexed; users can ingest PDFs and search their content
**Depends on**: Phase 5
**Requirements**: ATTACH-01, INGEST-01
**Success Criteria** (what must be TRUE):
  1. User re-runs ingest on a ZIP where one conversation has new messages — those new messages appear in search results; existing messages are unchanged and not duplicated
  2. Per-message INSERT OR IGNORE is used throughout — conversation message_count is updated after new inserts, never via INSERT OR REPLACE on FTS content tables
  3. User ingests a ZIP containing a PDF attachment — the extracted text content of the PDF is searchable via `search_conversations`
  4. User ingests a ZIP with no PDFs — ingest completes without error (pypdf/pdfplumber absent or PDF-free ZIP handled gracefully)
**Plans**: 1 plan
Plans:
- [ ] 06-01-PLAN.md — Fix incremental skip bug in ingest_zip(): append new messages to existing conversations (INGEST-01)

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Scaffolding + Schema Discovery | v1.0 | 3/3 | Complete | 2026-05-04 |
| 2. Database + Ingest              | v1.0 | 2/2 | Complete | 2026-05-05 |
| 3. MCP Tools                      | v1.0 | 2/2 | Complete | 2026-05-05 |
| 4. Integration + README           | v1.0 | 1/1 | Complete | 2026-05-06 |
| 5. Search Filters + Export        | v1.1 | 1/1 | Complete | 2026-05-16 |
| 6. Ingest Improvements            | v1.1 | 0/1 | Not started | - |
