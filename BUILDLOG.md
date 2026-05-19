## 2026-05-18 — v1.1 shipped: search filters, file export, incremental ingest

v1.0 landed in early May with the core working: 106 conversations indexed, six MCP tools live, registered in user scope so any Claude Code session could call them. The fundamental loop worked — export ZIP from Claude.ai, run ingest, search from any session.

v1.1 focused on the friction points that showed up during real use. Search had no way to narrow by date or message role, so queries against a growing history returned too much noise. The export tool only returned markdown as a string, which hit context limits on long conversations. And every re-ingest was a full reload — slow and redundant once the database had real history in it.

The search filter work (SRCH-01, SRCH-02) added `date_from`, `date_to`, and `role_filter` parameters to `search_conversations`. The date filters clip the FTS5 results against `created_at` on the conversations table. The role filter required a join against the messages table to check which role produced the matching content — human vs assistant. Both integrate cleanly with the existing BM25 ranking.

File export (EXP-01) was a one-parameter addition to `export_conversation`: pass a `file_path` and the markdown writes to disk instead of returning inline. Backward compatible — no file path means old behavior.

Incremental ingest (INGEST-01) was the trickiest piece. The FTS5 content table pattern Claude.ai's data uses means you can't use `INSERT OR REPLACE` — it breaks the FTS index. The fix was per-message `INSERT OR IGNORE` with a post-insert count to track how many messages were actually new, then updating `message_count` on the conversation row separately. A `per-conversation is_new_conv` flag kept the new-conversation path and existing-conversation update path cleanly separated without flag leakage across the loop.

Live UAT caught three bugs post-execution that automated tests missed: a path-resolution issue in file export on Windows, a missing input validation on the date filter format, and an edge case in connection cleanup when DB init fails. All fixed before tagging the milestone.

Stack: Python 3.11+, uv, FastMCP (mcp[cli]), SQLite FTS5, stdio transport. Windows 11. 910 LOC across 7 modules.
