"""FTS5 search logic for the claude-history MCP server."""

import logging
import sqlite3
from claude_history.config import DB_PATH
from claude_history.db import init_db

log = logging.getLogger(__name__)


def _fts_rows(cur: sqlite3.Cursor, fts_query: str) -> list:
    cur.execute("""
        SELECT m.conversation_id, m.rowid, bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        WHERE messages_fts MATCH ?
        ORDER BY bm25(messages_fts)
    """, (fts_query,))
    return cur.fetchall()


def _get_snippet(cur: sqlite3.Cursor, fts_query: str, rowid: int) -> str:
    cur.execute("""
        SELECT snippet(messages_fts, 0, '**', '**', '...', 64) AS snip
        FROM messages_fts
        WHERE messages_fts MATCH ? AND rowid = ?
    """, (fts_query, rowid))
    row = cur.fetchone()
    return row["snip"] if row else ""


def search_conversations(
    query: str,
    limit: int = 10,
    include_full_content: bool = False,
) -> list[dict]:
    """Search indexed conversations using FTS5 BM25 ranking.

    Returns up to `limit` conversations (default 10), one per conversation,
    with the best-matching message supplying the snippet. match_count reports
    how many messages in the conversation matched the query.

    D-05: Attempts raw FTS5 input first (supports AND, OR, NEAR(), prefix wildcards).
    Falls back to phrase search (double-quoted) on sqlite3.OperationalError.

    D-06: Returns [] when no conversations match — never raises.
    """
    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # D-05: try raw FTS5 first, fall back to sanitized phrase on OperationalError
        active_query = query
        try:
            rows = _fts_rows(cur, active_query)
        except sqlite3.OperationalError:
            escaped = query.replace('"', '""')
            active_query = f'"{escaped}"'
            try:
                rows = _fts_rows(cur, active_query)
            except sqlite3.OperationalError:
                log.warning("FTS5 query failed after sanitization: %r", query)
                return []
            log.debug("FTS5 sanitization fallback used for query: %r", query)

        # D-06: empty results — return [] not an error
        if not rows:
            return []

        # D-02: one result per conversation — Python aggregation (bm25 cannot GROUP BY)
        # bm25() returns negative scores; lower (more negative) = better match
        best: dict = {}  # conv_id -> {"rowid": int, "score": float, "count": int}
        for row in rows:
            cid = row["conversation_id"]
            if cid not in best:
                best[cid] = {"rowid": row["rowid"], "score": row["score"], "count": 1}
            else:
                best[cid]["count"] += 1

        # D-01: default limit 10; sorted ascending puts best (most negative) first
        ranked = sorted(best.items(), key=lambda x: x[1]["score"])
        top_n = ranked[:limit]

        results = []
        for conv_id, info in top_n:
            # D-03: ~300 char snippet from best-matching message (token_count=64)
            snippet = _get_snippet(cur, active_query, info["rowid"])

            cur.execute(
                "SELECT title, created_at, project FROM conversations WHERE id = ?",
                (conv_id,),
            )
            conv = cur.fetchone()
            if conv is None:
                log.warning("FTS match for conv_id %r but no conversations row found", conv_id)
                continue

            result: dict = {
                "id": conv_id,
                "title": conv["title"] or "",
                "created_at": conv["created_at"] or "",
                "project": conv["project"],  # NULL in all current data
                "match_count": info["count"],
                "snippet": snippet,
            }

            # D-04: include_full_content appends all messages concatenated
            if include_full_content:
                cur.execute("""
                    SELECT role, content FROM messages
                    WHERE conversation_id = ?
                    ORDER BY position ASC
                """, (conv_id,))
                msg_rows = cur.fetchall()
                result["full_content"] = "\n\n".join(
                    f"{'Human' if r['role'] == 'human' else 'Assistant'}: {r['content']}"
                    for r in msg_rows
                )

            results.append(result)

        return results

    finally:
        conn.close()
