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

## Milestone: v1.1 — Search & Ingest Improvements

**Shipped:** 2026-05-18
**Phases:** 2 | **Plans:** 2
**Timeline:** 2 days (2026-05-16 → 2026-05-18)
**Source:** +200 / -45 lines across ingest.py, search.py, server.py

### What Was Built

1. `search.py` — `date_from`/`date_to` post-dedup filtering using `[:10]` prefix comparison; `role_filter` as SQL parameterized predicate in FTS JOIN
2. `server.py` — three new optional params wired to `search_conversations` tool; `file_path` optional write added to `export_conversation`
3. `ingest.py` — removed early-exit UUID skip; per-conversation `is_new_conv`/`conv_new_msgs` delta tracking; three-count log output

### What Worked

- **Tight scope.** Two phases, two plans, four requirements. No scope creep. ATTACH-01 was cleanly deferred before Phase 6 started rather than discovered as a gap at the end.

- **TDD on the filter boundary condition.** Writing the failing test for `_passes_date_filter` with same-day `date_to` first (the T-separator bug) forced the correct `[:10]` implementation before it could silently produce wrong results in production.

- **Live UAT before archiving.** The 10/10 UAT run caught nothing unexpected — but it validated the incremental ingest on a fresh real export with new conversations, which no unit test could have verified. The CLAUDE.md note requiring live UAT before milestone close is the right policy.

- **Three-count log format.** The D-06 log format ("N new / M updated (K msgs) / P unchanged") surfaced the `total_new_msgs` scoping bug during Task 2 smoke test — the contradictory "0 updated (2 new messages)" output was immediately obvious. A single-count log would have hidden the bug.

### What Was Inefficient

- **ATTACH-01 carried into Phase 6 then immediately deferred.** The requirement was in the ROADMAP.md Phase 6 goals but the plan only addressed INGEST-01. Should have updated the Phase 6 roadmap entry at plan-time rather than leaving the mismatch for the milestone close review.

- **wp-sync initialization mid-milestone.** Commits `9929e06` and `4648632` (WordPress documentation publishing) were mixed into the v1.1 git range. Unrelated infrastructure work is cleaner when done between milestones or on a separate branch.

### Patterns Established

- **`[:10]` for ISO date comparison:** Always slice `conversations.created_at[:10]` before comparing against bare `YYYY-MM-DD` strings. The full ISO timestamp is lexicographically greater than the date-only string, which silently excludes same-day conversations.
- **Delta tracking per conversation:** `is_new_conv` + `conv_new_msgs` local variables cleanly separate new-conversation inserts from existing-conversation appends. The `total_new_msgs` accumulator belongs inside the `not is_new_conv` branch.
- **Three-count ingest log:** "N new / M updated (K msgs) / P unchanged" is the right format — the three counts are independent and contradictions are immediately visible.

### Key Lessons

1. **Validate log output semantics in the smoke test.** The `total_new_msgs` bug produced "0 existing conversations updated (2 new messages)" — correct counts but wrong assignment. The smoke test caught it because the log format made the contradiction visible.
2. **Update phase roadmap entries at plan-time.** When a requirement is deferred during planning, update the ROADMAP.md phase entry before executing — not as a clean-up after the fact.
3. **Separate infrastructure commits from feature work.** wp-sync setup belongs in its own session or branch, not interspersed in a feature milestone.

### Cost Observations

- Model: claude-sonnet-4-6 throughout
- Sessions: ~3 (Phase 5 plan+execute, Phase 6 plan+execute, UAT+close)
- Total execution time: ~6 min of active plan execution; 2 days elapsed
- Notable: Both phases completed in ~2 min each — tight requirements with no ambiguity, clean data layer from v1.0, and TDD on the boundary case kept execution fast

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Days | LOC delta | Key Constraint |
|-----------|--------|-------|------|-----------|----------------|
| v1.0 MVP  | 4      | 8     | 3    | +910      | stdio stdout invariant |
| v1.1 Improvements | 2 | 2  | 2    | +155      | INSERT OR IGNORE on FTS content tables |
