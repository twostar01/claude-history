"""FTS5 search logic for the claude-history MCP server."""

import logging
import sqlite3
from claude_history.config import DB_PATH
from claude_history.db import init_db

log = logging.getLogger(__name__)


def _fts_rows(cur: sqlite3.Cursor, fts_query: str, role: str | None = None) -> list:
    sql = """
        SELECT m.conversation_id, m.rowid, bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        WHERE messages_fts MATCH ?
    """
    params: list = [fts_query]
    if role is not None:
        sql += " AND m.role = ?"
        params.append(role)
    sql += " ORDER BY score"
    cur.execute(sql, params)
    return cur.fetchall()


def _get_snippet(cur: sqlite3.Cursor, fts_query: str, rowid: int) -> str:
    cur.execute("""
        SELECT snippet(messages_fts, 0, '**', '**', '...', 64) AS snip
        FROM messages_fts
        WHERE messages_fts MATCH ? AND rowid = ?
    """, (fts_query, rowid))
    row = cur.fetchone()
    return row["snip"] if row else ""


def _passes_date_filter(
    created_at: str,
    date_from: str | None,
    date_to: str | None,
) -> bool:
    """Return True if created_at falls within [date_from, date_to] inclusive.

    created_at is a full ISO timestamp ('2026-03-05T04:12:59.485807+00:00').
    date_from and date_to are bare date strings ('YYYY-MM-DD').
    Comparison uses the 10-char date prefix to avoid lexicographic boundary
    issues — the 'T' in a full timestamp sorts after a bare date string,
    which would silently exclude same-day conversations for date_to filters.
    """
    if not created_at:
        return True  # NULL/empty: include defensively
    prefix = created_at[:10]  # 'YYYY-MM-DD'
    if date_from is not None and prefix < date_from:
        return False
    if date_to is not None and prefix > date_to:
        return False
    return True


def search_conversations(
    query: str,
    limit: int = 10,
    include_full_content: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    role_filter: str | None = None,
) -> list[dict]:
    """Search indexed conversations using FTS5 BM25 ranking.

    Returns up to `limit` conversations (default 10), one per conversation,
    with the best-matching message supplying the snippet. match_count reports
    how many messages in the conversation matched the query.

    D-05: Attempts raw FTS5 input first (supports AND, OR, NEAR(), prefix wildcards).
    Falls back to phrase search (double-quoted) on sqlite3.OperationalError.

    D-06: Returns [] when no conversations match — never raises.

    Args:
        query: FTS5 search query string.
        limit: Maximum number of conversations to return (default 10).
        include_full_content: When True, full message content is returned
            instead of snippets.
        date_from: Optional ISO date string (YYYY-MM-DD). When provided, only
            conversations started on or after this date are returned. None
            (default) applies no lower bound.
        date_to: Optional ISO date string (YYYY-MM-DD). When provided, only
            conversations started on or before this date are returned. None
            (default) applies no upper bound.
        role_filter: Optional role filter. "human" returns only conversations
            where a human message matched the query; "assistant" similarly
            filters to assistant messages. None (default) applies no role filter.
            Malformed values return [] without raising an error.
    """
    VALID_ROLES = {"human", "assistant"}
    if role_filter is not None and role_filter not in VALID_ROLES:
        return []  # reject fast -- documented contract

    conn = init_db(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # D-05: try raw FTS5 first, fall back to sanitized phrase on OperationalError
        active_query = query
        try:
            rows = _fts_rows(cur, active_query, role=role_filter)
        except sqlite3.OperationalError:
            escaped = query.replace('"', '""')
            active_query = f'"{escaped}"'
            try:
                rows = _fts_rows(cur, active_query, role=role_filter)
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

        # SRCH-01 (D-01/D-02/D-03): apply date filter post-dedup, pre-limit-slice.
        # Fetch created_at for each ranked candidate to avoid per-item DB round-trips.
        if date_from is not None or date_to is not None:
            # Collect all conv_ids in ranked order, fetch their created_at in one query
            ranked_ids = [cid for cid, _ in ranked]
            placeholders = ",".join("?" * len(ranked_ids))
            cur.execute(
                f"SELECT id, created_at FROM conversations WHERE id IN ({placeholders})",
                ranked_ids,
            )
            date_map = {r["id"]: r["created_at"] or "" for r in cur.fetchall()}
            ranked = [
                (cid, info) for cid, info in ranked
                if _passes_date_filter(date_map.get(cid, ""), date_from, date_to)
            ]

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
                    f"{'Human' if r['role'] == 'human' else 'Assistant'}: {r['content'] or ''}"
                    for r in msg_rows
                )

            results.append(result)

        return results

    finally:
        conn.close()
