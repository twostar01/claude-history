"""Claude History MCP Server — FastMCP stdio."""

import sys
sys.stderr.reconfigure(encoding="utf-8")  # must precede ALL other imports

import logging
import sqlite3
from pathlib import Path

# STDOUT CONTAMINATION RULE: logging.basicConfig() MUST be called before any
# FastMCP instantiation. The FastMCP stdio transport uses stdout exclusively for
# JSON-RPC framing. Any write to stdout silently corrupts the session.

from mcp.server.fastmcp import FastMCP
from claude_history.config import DB_PATH
from claude_history.db import init_db
from claude_history.search import search_conversations as _search


def main() -> None:
    """Entry point for `uv run server`."""

    # Step 1: Route ALL logging to stderr (must be before FastMCP() instantiation)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    log = logging.getLogger(__name__)
    log.info("claude-history MCP server starting")

    # Step 2: Create FastMCP instance AFTER logging is configured
    mcp = FastMCP("claude-history")

    # ── Tool: search_conversations ───────────────────────────────────────────
    @mcp.tool()
    def search_conversations(
        query: str,
        project_filter: str | None = None,
        include_full_content: bool = False,
    ) -> list[dict]:
        """Search indexed conversations using FTS5 BM25 ranking.

        Returns up to 10 conversations ranked by relevance. Each result includes:
        id, title, created_at, project (currently always null — export format
        limitation), match_count (messages matching in the conversation), and
        snippet (~300 chars around the best matching term, with **highlights**).

        Supports FTS5 operators: AND, OR, NEAR(), prefix wildcards (e.g. claude*).
        Natural-language queries are also safe — malformed FTS5 syntax falls back
        to phrase search automatically.

        Set include_full_content=True to receive all messages concatenated instead
        of snippets.
        """
        # project_filter kept in signature for schema compatibility; not applied
        # (all project fields are NULL — see list_projects() for explanation)
        return _search(query, limit=10, include_full_content=include_full_content)

    # ── Tool: get_conversation ───────────────────────────────────────────────
    @mcp.tool()
    def get_conversation(id: str) -> dict:
        """Return full conversation content as labeled Human/Assistant turns.

        Messages are returned in original order (position ASC). Empty messages
        (attachments-only) are included to preserve position continuity.

        Returns {"error": "..."} when the conversation ID is not found.
        """
        conn = init_db(DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT title, created_at, project, message_count FROM conversations WHERE id = ?",
                (id,),
            )
            conv = cur.fetchone()
            if conv is None:
                return {"error": f"Conversation {id!r} not found."}

            # D-07: sort by position INTEGER ascending
            cur.execute("""
                SELECT role, content, position
                FROM messages
                WHERE conversation_id = ?
                ORDER BY position ASC
            """, (id,))
            messages = cur.fetchall()
        finally:
            conn.close()

        role_label = {"human": "Human", "assistant": "Assistant"}
        turns = [
            {
                "role": role_label.get(msg["role"], msg["role"].capitalize()),
                "content": msg["content"],
                "position": msg["position"],
            }
            for msg in messages
        ]
        return {
            "id": id,
            "title": conv["title"] or "",
            "created_at": conv["created_at"] or "",
            "project": conv["project"],
            "message_count": conv["message_count"],
            "turns": turns,
        }

    # ── Tool: list_projects ──────────────────────────────────────────────────
    @mcp.tool()
    def list_projects() -> list:
        """Return list of projects with conversation counts and date ranges.

        NOTE: The Claude.ai export format (conversations.json) contains no
        project association field for conversations. This tool always returns
        an empty list. This is a data availability limitation in the export
        format, not a bug. The 7 project metadata files in the export
        (projects/*.json) hold descriptions only — no conversation UUIDs.
        """
        return []

    # ── Tool: get_stats ──────────────────────────────────────────────────────
    @mcp.tool()
    def get_stats() -> dict:
        """Return database statistics: conversation count, message count, date range, file size."""
        conn = init_db(DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM conversations")
            conv_count = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM messages")
            msg_count = cur.fetchone()["n"]
            cur.execute(
                "SELECT MIN(created_at) AS earliest, MAX(created_at) AS latest FROM conversations"
            )
            dates = cur.fetchone()
        finally:
            conn.close()

        db_size_bytes = DB_PATH.stat().st_size
        return {
            "conversations": conv_count,
            "messages": msg_count,
            "date_from": dates["earliest"],
            "date_to": dates["latest"],
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
        }

    # ── Tool: export_conversation ────────────────────────────────────────────
    @mcp.tool()
    def export_conversation(id: str) -> str:
        """Return conversation as a clean markdown string suitable for pasting or summarizing.

        Format:
          # {title}
          *Date: {created_at}*

          ## Human
          {message content}

          ## Assistant
          {message content}
          ...

        No per-message timestamps (D-10). Returns an error string when ID not found.
        """
        conn = init_db(DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT title, created_at FROM conversations WHERE id = ?", (id,)
            )
            conv = cur.fetchone()
            if conv is None:
                return f"Conversation {id!r} not found."

            # D-07: position ASC
            cur.execute("""
                SELECT role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY position ASC
            """, (id,))
            messages = cur.fetchall()
        finally:
            conn.close()

        # D-09: compact metadata header (title + date only — no UUID, no message count)
        lines: list[str] = [
            f"# {conv['title'] or '(Untitled)'}",
            f"*Date: {conv['created_at']}*",
            "",
        ]
        # D-08: ## Human / ## Assistant H2 headers; D-10: no per-message timestamps
        for msg in messages:
            label = "Human" if msg["role"] == "human" else "Assistant"
            lines.append(f"## {label}")
            lines.append("")
            lines.append(msg["content"])
            lines.append("")

        return "\n".join(lines)

    # ── Tool: get_status ─────────────────────────────────────────────────────
    @mcp.tool()
    def get_status() -> dict:
        """Return server health and database statistics.

        Promoted from Phase 1 stub to include conversation count and last
        ingested date for a quick at-a-glance view of the indexed data.
        """
        conn = init_db(DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM conversations")
            conv_count = cur.fetchone()["n"]
            cur.execute("SELECT MAX(created_at) AS latest FROM conversations")
            latest = cur.fetchone()["latest"]
        finally:
            conn.close()

        return {
            "status": "ok",
            "conversations": conv_count,
            "last_ingested": latest,
        }

    # Step 3: Start the MCP stdio loop (blocks until client disconnects)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
