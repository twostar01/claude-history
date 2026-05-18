"""Ingest a Claude.ai export ZIP into history.db.

Entry point: main() — registered as 'uv run ingest' in pyproject.toml.

Usage:
    uv run ingest <path/to/export.zip>

The ZIP must contain conversations.json. Other top-level members
(projects/, design_chats/, users.json) are silently skipped.

Incremental: safe to re-run on an updated ZIP. New messages in existing
conversations are appended; duplicate messages are silently skipped via
INSERT OR IGNORE. New conversations are inserted in full.
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

    Incremental behavior: ALL conversations in the ZIP are scanned regardless
    of whether they already exist in the DB. INSERT OR IGNORE on individual
    messages handles deduplication — existing messages are silently skipped,
    new messages are appended. After processing each conversation, if any new
    messages were inserted, message_count and updated_at are updated on the
    conversations row.

    Uses INSERT OR IGNORE throughout — history records are immutable.
    INSERT OR REPLACE is explicitly avoided because it changes the rowid,
    which orphans FTS5 content table index entries.

    Logs progress and final counts to stderr.
    """
    from claude_history.db import init_db

    conn = init_db(db_path)
    try:
        cur = conn.cursor()

        new_convs = 0
        skipped_convs = 0
        updated_convs = 0
        unchanged_convs = 0
        total_new_msgs = 0
        attachment_msgs = 0

        with zipfile.ZipFile(zip_path) as zf:
            # Only conversations.json is processed in Phase 2.
            # projects/, design_chats/, users.json are silently skipped.
            if "conversations.json" not in zf.namelist():
                log.error(
                    "conversations.json not found in %s. "
                    "Is this a Claude.ai export ZIP?", zip_path
                )
                sys.exit(1)
            with zf.open("conversations.json") as f:
                try:
                    conversations = json.load(f)
                except json.JSONDecodeError as exc:
                    log.error("conversations.json is not valid JSON: %s", exc)
                    sys.exit(1)

        log.info("%d conversations found in ZIP", len(conversations))

        for conv in conversations:
            uuid = conv.get("uuid")
            if not uuid:
                log.warning("Skipping conversation with missing uuid: %r", conv.get("name"))
                skipped_convs += 1
                continue

            msgs = conv.get("chat_messages", [])
            title = conv.get("name") or ""

            # INSERT OR IGNORE: no-op when UUID already exists; rowcount==0 means
            # existing conversation, rowcount==1 means newly inserted.
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
            is_new_conv = bool(cur.rowcount)
            if is_new_conv:
                new_convs += 1
            else:
                skipped_convs += 1  # race-condition duplicate or existing conversation

            conv_new_msgs = 0

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
                if cur.rowcount:
                    conv_new_msgs += 1
                    if has_attachment:
                        attachment_msgs += 1

            # Update message_count and updated_at if new messages were appended to an
            # existing conversation. New conversations already have the correct initial counts.
            if conv_new_msgs > 0 and not is_new_conv:
                cur.execute(
                    """UPDATE conversations
                       SET message_count = message_count + ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (
                        conv_new_msgs,
                        normalize_ts(conv.get("updated_at", "")),
                        uuid,
                    ),
                )
                updated_convs += 1
                total_new_msgs += conv_new_msgs
            elif not is_new_conv and conv_new_msgs == 0:
                unchanged_convs += 1

        conn.commit()
    finally:
        conn.close()

    log.info("%d new conversations", new_convs)
    log.info(
        "%d existing conversations updated (%d new messages)",
        updated_convs,
        total_new_msgs,
    )
    log.info("%d conversations unchanged", unchanged_convs)
    if attachment_msgs:
        log.info("%d messages had attachment content", attachment_msgs)


def main() -> None:
    """CLI entry point: parse zip_path argument and run ingest."""
    parser = argparse.ArgumentParser(
        description="Ingest a Claude.ai export ZIP into history.db"
    )
    parser.add_argument("zip_path", help="Path to the Claude.ai export ZIP file")
    args = parser.parse_args()

    from claude_history.config import DB_PATH

    ingest_zip(Path(args.zip_path), DB_PATH)
