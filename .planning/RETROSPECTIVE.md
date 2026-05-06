# Retrospective

## Milestone: v1.0 — Claude History MCP Server MVP

**Shipped:** 2026-05-06
**Phases:** 4 | **Plans:** 8 | **Timeline:** 3 days (2026-05-03 → 2026-05-06)
**Commits:** 79 | **Source:** 910 LOC Python

---

### What Was Built

1. `schema_discovery.py` — reverse-engineered Claude.ai export format against real ZIP; produced SCHEMA.md that unblocked Phase 2 without guesswork
2. `db.py` — SQLite FTS5 schema with unicode61 `tokenchars '-_'` tokenizer, WAL mode, content-table sync triggers (TDD: 16 tests)
3. `ingest.py` — ZIP parser: 106 conversations, 4087 messages, idempotent re-run, attachment content extraction (TDD: 23 tests)
4. `search.py` — FTS5 BM25 ranked search with Python dict aggregation dedup, snippet extraction, OperationalError fallback
5. `server.py` — 6 FastMCP tools wired to live SQLite; stderr-only logging; user-scope registration
6. `README.md` — install → ingest → register → query from scratch in under 5 minutes

---

### What Worked

- **Schema-first gating.** Phase 1 required actually running schema_discovery.py against the real export before Phase 2 could start. This prevented wasted plans writing an ingest.py against assumed field names. The real data had surprises (project-association gap, 7 project files not 6, design_chats having a different schema) — all caught before Phase 2.

- **TDD for the write path.** db.py and ingest.py both used red/green/refactor cycles. Both passed on first green implementation. Having 39 passing tests meant Phase 3 could iterate on search.py without fear of breaking the data layer.

- **Locking invariants early.** The stderr-only logging requirement was established in Phase 1 Plan 1 (`__init__.py` cleaned of default `print("Hello from claude-history!")`) and held through all 4 phases. No stdout contamination incidents.

- **Phase 4 user-scope registration.** The `uv --directory <abs-path> run server` pattern works from any working directory. Discovered and tested in Phase 4; should be the starting point for any future MCP server that needs to survive session changes.

---

### What Was Inefficient

- **Context exhaustion at ~75%.** The session that completed Phase 4 and started STATE.md updates hit context limits and partially overwrote STATE.md with incorrect values (completed_phases: 3, total_plans: 7). Required a manual fix commit in the next session. Milestone-closing work should happen in a fresh session, not tagged onto an execution session.

- **`uv run` Windows file-lock issue.** Discovered in Phase 2 and worked around in Phases 3 and 4 with `--no-sync`. The workaround is fine but it came up multiple times — README could be clearer about this.

- **PROJECT.md was not updated between phases.** The "Requirements → Active → Validated" cycle called out in the Evolution section didn't happen at each phase transition. Most Active requirements were still unchecked in PROJECT.md when Phase 4 completed. Doing this at each transition would have made the final milestone review lighter.

---

### Patterns Established

- **Logging order is non-negotiable:** `sys.stderr.reconfigure()` → `logging.basicConfig(stream=sys.stderr)` → `FastMCP()` → tools → `mcp.run()`. Deviation at any point risks stdout contamination that silently kills stdio sessions.
- **Connection lifecycle:** `init_db(DB_PATH)` in function body, `conn.close()` in finally block — no global connection state.
- **row_factory after init_db:** `conn.row_factory = sqlite3.Row` set after `init_db()` returns, not inside `init_db()` — keeps the schema function generic.
- **Entry points as named scripts:** `pyproject.toml [project.scripts]` with `server`, `ingest`, `schema-discovery` — cleaner than `python -m module`.
- **User-scope MCP registration:** `uv --directory <abs-path> run server` — always use absolute path and `--directory` flag.

---

### Key Lessons

1. **Gate phases on real data.** Schema discovery wasn't optional overhead — it was the only way to know what field names to use. Any future phase that processes external data should have a schema-first gate.
2. **TDD pays off at the data layer.** The 39 db + ingest tests ran in every subsequent phase and caught nothing — because the tests locked in the correct behavior from the start. Worth the upfront cost.
3. **Close milestone in a fresh session.** Context pressure at the end of a long execution session causes write-back errors. Start a new `/clear` session for milestone archival.
4. **Document the Windows `uv run` quirk prominently.** The server.exe file lock issue blocks the ingest shortcut and will confuse future users. Already in README but worth calling out in the CLAUDE.md conventions.

---

### Cost Observations

- Model: claude-sonnet-4-6 throughout
- Sessions: ~5 (research/plan, Phase 1+2 execution, Phase 3 execution, Phase 4 execution, verification+close)
- Total execution time: ~16 min of active plan execution; ~3 days elapsed
- Notable: Phase 3 Plan 01 (search.py) executed in 1 min including live DB verification — the schema + data layer being solid made tool implementation fast

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Days | LOC | Key Constraint |
|-----------|--------|-------|------|-----|----------------|
| v1.0 MVP  | 4      | 8     | 3    | 910 | stdio stdout invariant |
