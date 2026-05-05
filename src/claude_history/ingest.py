"""Ingest a Claude.ai export ZIP into history.db.

Entry point: main() — registered as 'uv run ingest' in pyproject.toml.

Usage:
    uv run ingest <path/to/export.zip>

The ZIP must contain conversations.json. Other top-level members
(projects/, design_chats/, users.json) are silently skipped.

Idempotent: safe to re-run on the same ZIP. Existing conversations are
skipped; new conversations are appended.
"""

import argparse
import json
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# stderr-only logging — stdout contamination kills the MCP stdio session.
# This rule applies to ingest.py exactly as it does to server.py.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


def build_message_content(msg: dict) -> str:
    """Combine message text and attachment extracted_content into one FTS string.

    - msg["text"] is the primary text field (may be empty string)
    - msg["attachments"][n]["extracted_content"] contains pre-extracted text
      from txt, py, json, md, etc. files — already a decoded string in the export
    - msg["files"] entries have no extracted content — skipped
    - Empty messages (text="" and no attachments) return "" — still inserted
      to preserve conversation position ordering for Phase 3 get_conversation()

    Returns parts joined by double newline, filtering empty strings.
    """
    parts = [msg.get("text", "")]
    for att in msg.get("attachments", []):
        ec = att.get("extracted_content", "")
        if ec:
            parts.append(ec)
    return "\n\n".join(p for p in parts if p)


def normalize_ts(ts: str) -> str:
    """Normalize ISO 8601 timestamp to consistent '+00:00' form.

    Handles both formats present in the Claude.ai export:
    - Z suffix: '2026-04-01T23:44:12.155755Z'
    - +00:00 offset: '2026-03-05T06:20:46.561314+00:00'

    Python 3.11+ datetime.fromisoformat() handles both natively.
    Returns empty string for empty/None input.
    """
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).isoformat()
    except ValueError:
        log.warning("Unrecognized timestamp format, storing raw: %r", ts)
        return ts


def ingest_zip(zip_path: Path, db_path: Path) -> None:
    """Parse a Claude.ai export ZIP and upsert conversations + messages.

    Incremental behavior: conversations already in the DB are skipped
    entirely (UUID-based check). Only new conversations are inserted.

    Uses INSERT OR IGNORE throughout — history records are immutable.
    INSERT OR REPLACE is explicitly avoided because it changes the rowid,
    which orphans FTS5 content table index entries.

    Logs progress and final counts to stderr.
    """
    from claude_history.db import init_db

    conn = init_db(db_path)
    cur = conn.cursor()

    new_convs = 0
    skipped_convs = 0
    new_msgs = 0
    attachment_msgs = 0

    with zipfile.ZipFile(zip_path) as zf:
        # Only conversations.json is processed in Phase 2.
        # projects/, design_chats/, users.json are silently skipped.
        with zf.open("conversations.json") as f:
            conversations = json.load(f)

    log.info("%d conversations found in ZIP", len(conversations))

    for conv in conversations:
        uuid = conv.get("uuid")
        if not uuid:
            log.warning("Skipping conversation with missing uuid: %r", conv.get("name"))
            skipped_convs += 1
            continue

        # Incremental skip: if conversation already indexed, skip all its messages.
        # UUID uniqueness is guaranteed by the Claude.ai export format.
        cur.execute("SELECT 1 FROM conversations WHERE id = ?", (uuid,))
        if cur.fetchone():
            skipped_convs += 1
            continue

        msgs = conv.get("chat_messages", [])
        title = conv.get("name") or ""

        # INSERT OR IGNORE: if a race condition inserted this UUID between the
        # SELECT above and here, the IGNORE prevents a duplicate. rowcount==0
        # when the IGNORE fires — count it as skipped rather than new.
        cur.execute(
            """INSERT OR IGNORE INTO conversations
               (id, title, project, created_at, updated_at, message_count)
               VALUES (?, ?, NULL, ?, ?, ?)""",
            (
                uuid,
                title,
                normalize_ts(conv.get("created_at", "")),
                normalize_ts(conv.get("updated_at", "")),
                len(msgs),
            ),
        )
        if cur.rowcount:
            new_convs += 1
        else:
            skipped_convs += 1  # race-condition duplicate

        for position, msg in enumerate(msgs):
            msg_uuid = msg.get("uuid")
            if not msg_uuid:
                log.warning("Skipping message at position %d with missing uuid", position)
                continue

            content_text = build_message_content(msg)
            has_attachment = bool(
                any(att.get("extracted_content") for att in msg.get("attachments", []))
            )

            cur.execute(
                """INSERT OR IGNORE INTO messages
                   (id, conversation_id, role, content, position, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    msg_uuid,
                    uuid,
                    msg.get("sender", ""),
                    content_text,
                    position,
                    normalize_ts(msg.get("created_at", "")),
                ),
            )
            new_msgs += 1
            if has_attachment:
                attachment_msgs += 1

    conn.commit()
    conn.close()

    log.info(
        "%d new, %d already indexed — skipping %d",
        new_convs,
        skipped_convs,
        skipped_convs,
    )
    log.info(
        "indexed %d messages (%d with attachment content)",
        new_msgs,
        attachment_msgs,
    )


def main() -> None:
    """CLI entry point: parse zip_path argument and run ingest."""
    parser = argparse.ArgumentParser(
        description="Ingest a Claude.ai export ZIP into history.db"
    )
    parser.add_argument("zip_path", help="Path to the Claude.ai export ZIP file")
    args = parser.parse_args()

    from claude_history.config import DB_PATH

    ingest_zip(Path(args.zip_path), DB_PATH)
