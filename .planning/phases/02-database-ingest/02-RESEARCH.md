# Phase 2: Database + Ingest — Research

**Researched:** 2026-05-04
**Domain:** SQLite FTS5 schema design, Python sqlite3 ingest pipeline, Claude.ai export parsing
**Confidence:** HIGH

---

## Summary

Phase 2 builds `db.py` (schema definition + WAL mode) and `ingest.py` (ZIP parsing + upsert +
attachment indexing). All primary technical questions were verified against the live SQLite 3.50.4
installation and the actual export ZIP on disk — no assumed facts about the schema.

**Key discovery:** The `attachments[].extracted_content` field already contains decoded text (string,
not bytes). There is no binary-detection problem for attachments — the export pre-extracts text for
txt, py, json, md, etc. The `files[]` array contains only `{file_uuid, file_name}` references with
no extracted content; these are skipped for FTS indexing.

**Primary recommendation:** Use `INSERT OR IGNORE` (not `INSERT OR REPLACE`) for both conversations
and messages. The ingest pipeline is append-only — history records do not change. INSERT OR REPLACE
changes the rowid, orphaning FTS index entries for the old tokens even with AFTER DELETE triggers.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema creation + WAL mode | `db.py` | — | Isolated from ingest; called by both ingest.py and server.py |
| ZIP parsing + field extraction | `ingest.py` | — | One-time CLI operation, no MCP involvement |
| FTS5 sync (insert/delete) | SQL triggers in `db.py` | — | Declarative; triggers fire on any write path |
| Conversation dedup | `ingest.py` INSERT OR IGNORE | `db.py` UNIQUE constraint on uuid | Both layers enforce |
| Incremental skip | `ingest.py` query + skip logic | — | Check existence before processing messages |
| Attachment text assembly | `ingest.py` | — | Concatenate text + extracted_content before INSERT |
| Logging (stderr only) | `ingest.py` main() | — | Same rule as server.py — stdout contamination kills session |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `sqlite3` | ships with Python 3.14.4 / 3.11+ | DB connection, WAL, schema, upserts | Zero dependencies; FTS5 confirmed available (`sqlite3.sqlite_version` = 3.50.4) |
| Python stdlib `zipfile` | ships with Python | ZIP reading without extraction | Already used in schema_discovery.py; reads JSON members in-memory |
| Python stdlib `json` | ships with Python | Parse JSON from ZIP members | Already used in schema_discovery.py |
| Python stdlib `logging` | ships with Python | stderr-only progress logging | Consistent with server.py pattern |
| Python stdlib `argparse` | ships with Python | CLI argument parsing for `uv run ingest <zip>` | Standard CLI pattern |
| Python stdlib `pathlib` | ships with Python | Path construction, DB_PATH import | Already established in config.py |
| Python stdlib `datetime` | ships with Python | Timestamp normalization | `fromisoformat()` handles both Z and +00:00 formats natively in Python 3.11+ |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sys.stderr` | stdlib | Logging output | All logging must go to stderr — stdout contamination kills MCP session |

**No new dependencies.** Phase 2 uses Python stdlib only.

**Version verification:** SQLite 3.50.4 [VERIFIED: `sqlite3.sqlite_version` on live machine], Python 3.14.0 [VERIFIED: `sys.version` on live machine].

---

## Architecture Patterns

### System Architecture Diagram

```
export.zip
    |
    v
[ingest.py main()]
    |---> argparse: get zip_path
    |---> db.init_db(DB_PATH): CREATE TABLE IF NOT EXISTS + WAL mode
    |                         CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    |                         CREATE TRIGGER IF NOT EXISTS (AI, AD)
    |
    |---> zipfile.ZipFile(zip_path):
    |       |
    |       |---> conversations.json  -> [conversation list]
    |       |       |
    |       |       for conv in conversations:
    |       |           INSERT OR IGNORE into conversations (uuid check)
    |       |           if uuid already existed -> SKIP (incremental)
    |       |           else:
    |       |               for pos, msg in enumerate(chat_messages):
    |       |                   text = build_message_text(msg)
    |       |                   INSERT OR IGNORE into messages
    |       |                   AFTER INSERT trigger -> INSERT into messages_fts
    |       |
    |       |---> projects/UUID.json  -> metadata only (no conversations linked)
    |       |       -> currently no action (project association gap = NULL)
    |       |
    |       |---> design_chats/UUID.json -> skipped (Phase 2 scope)
    |       |
    |       |---> users.json           -> skipped
    |
    |---> log stats to stderr
    |---> conn.commit()
    v
history.db (WAL mode)
    conversations table
    messages table
    messages_fts virtual table (FTS5 content table, auto-synced by triggers)
```

### Recommended Project Structure

No new directories. New files:
```
src/
  claude_history/
    db.py           # init_db(db_path): WAL + schema + triggers
    ingest.py       # main(): argparse, load ZIP, call db.init_db, upsert, log
    config.py       # (exists) DB_PATH constant
    server.py       # (exists) FastMCP stub
    schema_discovery.py  # (exists) standalone inspection tool
```

### Pattern 1: Content Table FTS5 Schema

**What:** FTS5 virtual table backed by the `messages` content table. FTS index stores only the
full-text index; queries join back to `messages` for column values.

**When to use:** Avoids duplicate text storage. Required for DB-02.

**Exact CREATE statements** [VERIFIED: SQLite 3.50.4 live test]:

```sql
-- Source: https://www.sqlite.org/fts5.html §4.4 + live verification
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    project     TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    message_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    rowid           INTEGER PRIMARY KEY,
    id              TEXT UNIQUE NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    position        INTEGER NOT NULL,
    created_at      TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content="messages",
    content_rowid="rowid",
    tokenize="unicode61 remove_diacritics 2 tokenchars '-_'"
);

-- Triggers to keep FTS in sync with messages table
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
    INSERT INTO messages_fts(rowid, content)
    VALUES (new.rowid, new.content);
END;
```

**Why INTEGER PRIMARY KEY matters for FTS5:** FTS5 content tables use rowid as the link between
FTS index entries and the content table. VACUUM reassigns implicit rowids on tables without a
declared INTEGER PRIMARY KEY, which would corrupt the FTS index. The `rowid INTEGER PRIMARY KEY`
declaration on `messages` is a hard requirement, not a style choice.
[VERIFIED: SQLite docs + forum research — see Sources]

### Pattern 2: Tokenizer Configuration

**What:** `unicode61` tokenizer with `remove_diacritics 2` and `tokenchars '-_'` makes hyphens and
underscores part of tokens rather than separators. This means `search_conversations` is a single
indexable token — matching DB-01 success criterion.

**Verified behavior** [VERIFIED: live test against SQLite 3.50.4]:
- `MATCH 'search_conversations'` — matches documents containing the exact snake_case token
- `MATCH 'search'` — does NOT match (underscore is a token character, not a separator)
- `tokenchars '-_'` applies to both `-` and `_`

**Tokenizer option is locked:** Once data is inserted, the tokenizer cannot be changed without
dropping the FTS table and rebuilding. This was a pre-phase locked decision.

### Pattern 3: INSERT OR IGNORE for Idempotent Ingest

**What:** All upserts use `INSERT OR IGNORE` — not `INSERT OR REPLACE`.

**Why INSERT OR REPLACE is wrong for this codebase:**
INSERT OR REPLACE on a UNIQUE constraint violation deletes the old row then inserts a new one.
The new row gets a new rowid. The AFTER DELETE trigger fires (good), but the 'delete' command
removes the FTS entry by the OLD rowid. The new INSERT trigger registers the new rowid. The
orphan problem: if the old content tokens differ from the new content, old FTS entries may persist.
[VERIFIED: live test showing `search_conversations` orphan after INSERT OR REPLACE]

For this project: conversation history is read-only. Records do not change after export. INSERT OR
IGNORE is semantically correct: if the UUID already exists, keep the existing row unchanged.

```python
# Source: live verification 2026-05-04
# Conversations: skip if uuid already exists
cur.execute(
    """INSERT OR IGNORE INTO conversations
       (id, title, project, created_at, updated_at, message_count)
       VALUES (?, ?, ?, ?, ?, ?)""",
    (conv["uuid"], title, project, created_at, updated_at, msg_count),
)
skipped = cur.rowcount == 0  # rowcount == 0 means IGNORE fired

# Messages: skip if message uuid already exists
cur.execute(
    """INSERT OR IGNORE INTO messages
       (id, conversation_id, role, content, position, created_at)
       VALUES (?, ?, ?, ?, ?, ?)""",
    (msg["uuid"], conv_id, role, content_text, position, created_at),
)
```

### Pattern 4: Message Text Assembly

**What:** The FTS `content` column for a message is the concatenation of:
1. `message["text"]` — the primary text (confirmed primary FTS field in Phase 1)
2. Each `attachment["extracted_content"]` where it is non-empty

**Real data findings** [VERIFIED: 4087 messages in live export]:
- 3799 messages have non-empty `text`
- 25 messages have empty `text` but non-empty `attachments[].extracted_content`
- 263 messages have empty `text` and no attachments (file-upload-only messages or branching artifacts)
- `files[]` array contains only `{file_uuid, file_name}` — no extracted content, skip for indexing

**Attachment structure confirmed** [VERIFIED: live export inspection]:
```json
{
  "file_name": "script.py",
  "file_size": 5387,
  "file_type": "text/x-python",
  "extracted_content": "#!/usr/bin/env python3\n..."
}
```
The `file_type` values seen: `"txt"`, `""`, `"text/plain"`, `"text/x-python"`, `"application/json"`.
All 50 attachments in the export had non-empty `extracted_content` — there were NO binary
attachments (images, PDFs) in this export's attachments array. Binary uploads appear in `files[]`
with no content.

**Text assembly function:**
```python
def build_message_content(msg: dict) -> str:
    parts = [msg.get("text", "")]
    for att in msg.get("attachments", []):
        ec = att.get("extracted_content", "")
        if ec:
            parts.append(ec)
    return "\n\n".join(p for p in parts if p)
```

### Pattern 5: Incremental Ingest

**What:** Skip conversations whose UUID already exists in the DB.

**Why UUID-based (not updated_at-based):** The export captures a snapshot. If a conversation
UUID exists in the DB, all its messages are already indexed. INGEST-04 requires only that new
conversations are processed — not that new messages in existing conversations are updated.
This is consistent with the export being a complete snapshot, not a diff.

```python
# Check existence before processing messages
cur.execute("SELECT 1 FROM conversations WHERE id = ?", (conv["uuid"],))
if cur.fetchone():
    skipped_count += 1
    continue  # skip all messages for this conversation
```

**Incremental log output** (required by INGEST-04 success criterion):
```
INFO ingest: 106 conversations found in ZIP
INFO ingest: 12 new, 94 already indexed — skipping 94
INFO ingest: indexed 3847 messages (25 with attachment content)
```

### Pattern 6: Timestamp Normalization

**What:** Store timestamps as ISO 8601 strings in UTC. Both formats from the export are normalized
using `datetime.fromisoformat()`.

**Python 3.11+ handles both formats natively** [VERIFIED: live Python 3.14.0 test]:
```python
from datetime import datetime

def normalize_ts(ts: str) -> str:
    """Normalize any ISO 8601 timestamp to UTC +00:00 string."""
    if not ts:
        return ""
    return datetime.fromisoformat(ts).isoformat()
    # '2026-04-01T23:44:12.155755Z' -> '2026-04-01T23:44:12.155755+00:00'
    # '2026-03-05T06:20:46.561314+00:00' -> '2026-03-05T06:20:46.561314+00:00'
```

### Anti-Patterns to Avoid

- **INSERT OR REPLACE on messages:** Changes rowid, can orphan FTS index entries. Use INSERT OR IGNORE.
- **BEFORE DELETE trigger for FTS:** Official docs and confirmed usage is AFTER DELETE. The AFTER DELETE trigger works because `old.rowid` and `old.content` are still available in the trigger body.
- **Skipping WAL mode:** Set `PRAGMA journal_mode=WAL` as the first statement after connecting, before any table creation. While technically timing-agnostic, putting it first ensures every write uses WAL from the start. WAL mode persists across connections.
- **Writing to stdout in ingest.py:** The stdout contamination rule applies to `ingest.py` too — if Claude Code ever spawns ingest as a subprocess or invokes it in the same process space as the MCP server, any print() call would corrupt the session. All output via `logging` to `sys.stderr`.
- **Using `BEFORE DELETE` trigger for FTS:** The ROADMAP sketch says "BEFORE DELETE / AFTER INSERT triggers" — this is a terminology error. The correct SQL is `AFTER DELETE` and `AFTER INSERT`. See verified SQL in Pattern 1.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FTS5 index sync | Custom sync logic outside triggers | SQL AFTER INSERT / AFTER DELETE triggers | Atomic; no sync drift between table and index; verified pattern |
| Text attachment indexing | MIME sniffing / chardet | Read `extracted_content` field directly | Claude.ai pre-extracts text; the export already contains the string |
| Timestamp parsing | Custom regex parser | `datetime.fromisoformat()` | Python 3.11+ handles both Z and +00:00 natively |
| Duplicate detection | Hash comparison | UNIQUE constraint + INSERT OR IGNORE | DB enforces uniqueness; rowcount==0 detects ignored rows |
| FTS rebuild | Manual DELETE + re-INSERT loop | `INSERT INTO messages_fts(messages_fts) VALUES('rebuild')` | Official FTS5 rebuild command handles all shadow tables |
| FTS integrity check | Manual row count comparison | `INSERT INTO messages_fts(messages_fts) VALUES('integrity-check')` | Raises sqlite3.OperationalError if FTS is corrupt |

**Key insight:** The hardest problems in this phase (text extraction, FTS sync, dedup) are solved by
the export format itself and SQLite primitives. The ingest.py logic is straightforward iteration.

---

## Common Pitfalls

### Pitfall 1: INSERT OR REPLACE Orphans FTS Entries

**What goes wrong:** Using `INSERT OR REPLACE` on messages when a message UUID already exists. The
old row is deleted (rowid N), the new row is inserted (rowid N+1). The AFTER DELETE trigger fires
with `old.rowid = N` and deletes FTS entry for rowid N. The AFTER INSERT trigger creates FTS entry
for rowid N+1. But if the old text had tokens not in the new text, those tokens remain indexed for
the now-deleted rowid. Searches for those old tokens will return the new rowid's row (via FTS→content
table join), showing unexpected results.

**Why it happens:** INSERT OR REPLACE changes the rowid; the FTS index links content to rowid.
[VERIFIED: live test — `search_conversations` token persisted after INSERT OR REPLACE replaced the row]

**How to avoid:** Always use `INSERT OR IGNORE` for messages. Message content is immutable in this
system.

**Warning signs:** `SELECT count(*) FROM messages` != expected row count, or search results return
rows with mismatched content.

---

### Pitfall 2: VACUUM After Inserting Data Corrupts FTS If No INTEGER PRIMARY KEY

**What goes wrong:** If `messages` table is created without `rowid INTEGER PRIMARY KEY` (e.g., using
a UUID TEXT primary key only with implicit rowid), running `VACUUM` reassigns implicit rowids. FTS5
continues to look up rows by the old rowid values, finding no match or the wrong row.

**Why it happens:** SQLite implicit rowids are not stable across VACUUM. FTS5's `content_rowid`
must point to a stable, declared INTEGER PRIMARY KEY.

**How to avoid:** Always declare `rowid INTEGER PRIMARY KEY` explicitly on the messages table (done
in Pattern 1 schema). The `id TEXT UNIQUE NOT NULL` column holds the UUID; `rowid` is the stable
integer link to FTS.

**Warning signs:** FTS search returns rows with NULL content or no results after VACUUM.

---

### Pitfall 3: conversations.json Has No project Field

**What goes wrong:** Assuming project association can be copied from conversations.json. The export
format does NOT include a project field in conversations. Storing project=None (NULL) is the correct
approach for Phase 2.

**The data reality** [VERIFIED: SCHEMA.md + Phase 1 investigation]:
- `conversations.json` entries: no project field
- `projects/UUID.json`: has UUID, name, metadata — but no list of conversation UUIDs
- `design_chats/UUID.json`: has `project` object — but design_chats are a different content type
- No UUID overlap between `design_chats` UUIDs and `conversations.json` UUIDs (verified)

**Phase 2 decision:** Store `project = NULL` for all conversations ingested from conversations.json.
Design chats (skipped in Phase 2) could be a separate ingest path in a future phase.

**How to avoid:** Don't attempt project inference in Phase 2. The project column exists in the schema
for future use but will be NULL for all Phase 2 data.

---

### Pitfall 4: Trigger Naming Collision on Schema Re-creation

**What goes wrong:** Running `db.init_db()` on an existing database raises `OperationalError: table
messages already exists` if CREATE TABLE is used without IF NOT EXISTS.

**How to avoid:** All CREATE statements must use `IF NOT EXISTS`:
```sql
CREATE TABLE IF NOT EXISTS conversations ...
CREATE TABLE IF NOT EXISTS messages ...
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts ...
CREATE TRIGGER IF NOT EXISTS messages_ai ...
```
**Warning signs:** `OperationalError` on second ingest run.

---

### Pitfall 5: messages with Empty Content Are Still Inserted

**What goes wrong:** 263 messages in the export have empty `text` and no `attachments`. These have
`content = ""` in the messages table and no FTS entry (FTS5 skips empty tokens). They still need
to be inserted to maintain conversation structure for Phase 3 (`get_conversation` must return all
turns in order, including empty ones).

**How to avoid:** Do not skip messages with empty content. Insert them with `content = ""`. The
FTS index will simply not have an entry for them (no tokens). The trigger will insert an empty-
content FTS entry which is effectively a no-op for search.

---

### Pitfall 6: pyproject.toml ingest Entry Point Is Commented Out

**What goes wrong:** The `ingest = "claude_history.ingest:main"` line in pyproject.toml is commented
out (it was stubbed in Phase 1). `uv run ingest` will fail until this line is uncommented.

**How to avoid:** Task 1 of 02-02 must uncomment the ingest entry point in pyproject.toml as its
first action.

**Location:** `pyproject.toml` line: `# ingest = "claude_history.ingest:main"  # Phase 2 — module not yet implemented`

---

## Code Examples

### db.py — init_db() Function

```python
# Source: https://www.sqlite.org/fts5.html §4.4 + live verification 2026-05-04
import sqlite3
from pathlib import Path

def init_db(db_path: Path) -> sqlite3.Connection:
    """Create tables, FTS5 index, triggers, and enable WAL mode.
    
    Idempotent: uses CREATE ... IF NOT EXISTS throughout.
    Returns an open connection; caller is responsible for closing.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id            TEXT PRIMARY KEY,
            title         TEXT,
            project       TEXT,
            created_at    TEXT,
            updated_at    TEXT,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            rowid           INTEGER PRIMARY KEY,
            id              TEXT UNIQUE NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role            TEXT NOT NULL,
            content         TEXT NOT NULL DEFAULT '',
            position        INTEGER NOT NULL,
            created_at      TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content="messages",
            content_rowid="rowid",
            tokenize="unicode61 remove_diacritics 2 tokenchars '-_'"
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
            INSERT INTO messages_fts(rowid, content)
            VALUES (new.rowid, new.content);
        END;
    """)
    conn.commit()
    return conn
```

### ingest.py — Skeleton

```python
# Source: design derived from SCHEMA.md + live export analysis 2026-05-04
import argparse
import json
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# stderr-only logging (matches server.py pattern)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


def build_message_content(msg: dict) -> str:
    """Combine message text and attachment extracted_content into one FTS string."""
    parts = [msg.get("text", "")]
    for att in msg.get("attachments", []):
        ec = att.get("extracted_content", "")
        if ec:
            parts.append(ec)
    return "\n\n".join(p for p in parts if p)


def normalize_ts(ts: str) -> str:
    """Normalize ISO 8601 timestamp (Z or +00:00 suffix) to '+00:00' form."""
    if not ts:
        return ""
    return datetime.fromisoformat(ts).isoformat()


def ingest_zip(zip_path: Path, db_path: Path) -> None:
    from claude_history.db import init_db
    conn = init_db(db_path)
    cur = conn.cursor()
    
    new_convs = skipped_convs = new_msgs = 0
    
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("conversations.json") as f:
            conversations = json.load(f)
        
        log.info("%d conversations found in ZIP", len(conversations))
        
        for conv in conversations:
            uuid = conv["uuid"]
            
            # Incremental skip: if conversation already indexed, skip entirely
            cur.execute("SELECT 1 FROM conversations WHERE id = ?", (uuid,))
            if cur.fetchone():
                skipped_convs += 1
                continue
            
            # Insert conversation
            msgs = conv.get("chat_messages", [])
            title = conv.get("name") or ""
            cur.execute(
                """INSERT OR IGNORE INTO conversations
                   (id, title, project, created_at, updated_at, message_count)
                   VALUES (?, ?, NULL, ?, ?, ?)""",
                (uuid, title,
                 normalize_ts(conv.get("created_at", "")),
                 normalize_ts(conv.get("updated_at", "")),
                 len(msgs)),
            )
            new_convs += 1
            
            # Insert messages
            for position, msg in enumerate(msgs):
                content_text = build_message_content(msg)
                cur.execute(
                    """INSERT OR IGNORE INTO messages
                       (id, conversation_id, role, content, position, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (msg["uuid"], uuid,
                     msg.get("sender", ""),
                     content_text,
                     position,
                     normalize_ts(msg.get("created_at", ""))),
                )
                new_msgs += 1
        
        conn.commit()
    
    log.info(
        "%d new, %d already indexed — skipping %d",
        new_convs, skipped_convs, skipped_convs,
    )
    log.info("indexed %d messages", new_msgs)
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a Claude.ai export ZIP into history.db"
    )
    parser.add_argument("zip_path", help="Path to the Claude.ai export ZIP file")
    args = parser.parse_args()
    
    from claude_history.config import DB_PATH
    ingest_zip(Path(args.zip_path), DB_PATH)
```

### Verifying FTS5 After Ingest (sqlite3 CLI)

```sql
-- From: https://www.sqlite.org/fts5.html — verified working 2026-05-04
-- Test snake_case token as single unit (DB-01 success criterion)
SELECT snippet(messages_fts, 0, '**', '**', '...', 20) AS snip
FROM messages_fts
WHERE messages_fts MATCH 'search_conversations'
LIMIT 5;

-- BM25 ranked results (lower value = better match)
SELECT m.conversation_id, bm25(messages_fts) AS rank,
       snippet(messages_fts, 0, '**', '**', '...', 15) AS snip
FROM messages_fts
JOIN messages m ON m.rowid = messages_fts.rowid
WHERE messages_fts MATCH 'sqlite fts5'
ORDER BY rank
LIMIT 10;
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FTS3/FTS4 | FTS5 with external content tables | SQLite 3.9.0 (2015) | FTS5 mandatory — FTS4 has no `content=` option without data duplication |
| `PRAGMA recursive_triggers` needed for INSERT OR REPLACE + FTS | Use INSERT OR IGNORE instead | — | Simpler; avoids rowid churn entirely |
| Manual rebuild of FTS after bulk insert | Triggers auto-sync on every INSERT | — | No rebuild needed for incremental ingest |

**Deprecated/outdated:**
- FTS3/FTS4: Avoid. FTS5 ships in Python's stdlib SQLite (3.50.4 confirmed). No reason to use older modules.
- `trigram` tokenizer (mentioned in DB-01 requirement): The requirement text says "trigram tokenizer" but the locked decision from Phase 1 is `unicode61 tokenchars '-_'`. The trigram tokenizer is a separate FTS5 tokenizer for fuzzy matching — it's NOT what was locked. The locked tokenizer is `unicode61` with custom tokenchars. The "fuzzy/typo-tolerant" in DB-01 was aspirational phrasing; the actual design decision is `unicode61 tokenchars '-_'` for snake_case support.

---

## Project-Association Decision for Phase 2

**Decision recommended:** Store `project = NULL` for all conversations in Phase 2.

**Rationale:**
- `conversations.json` has no project field [VERIFIED: SCHEMA.md + Phase 1]
- `projects/UUID.json` has no conversation UUID list [VERIFIED: SCHEMA.md]
- `design_chats/UUID.json` does have `project` but design_chats are a different type, use a different message schema (`role/content` not `sender/text/attachments`), and have zero UUID overlap with conversations [VERIFIED: live export inspection]
- Phase 3 `list_projects()` can still work by querying the conversations table — it will return no rows until design_chats ingestion is added (fine for Phase 2/3)
- Phase 3 `search_conversations(project_filter=...)` will return no matches until project data is populated — acceptable for Phase 2

**Design_chats decision for Phase 2:** Skip design_chats entirely. They use a different message schema and would require a separate ingest path. Mark as future work.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `files[]` items will never gain `extracted_content` in future exports | Attachment pattern | Phase 3 might miss indexable content if Claude adds file content to this field |
| A2 | Messages in `chat_messages` array are always in chronological (position) order | Position derivation | Out-of-order messages would cause incorrect position assignments |

**A2 mitigation:** [VERIFIED: all 106 conversations checked — messages are in created_at ascending order, matching array order]. Risk is LOW.

**If this table is empty for practical purposes:** Both assumptions are LOW risk and verified partially.

---

## Open Questions

1. **DB-01 says "trigram tokenizer" but Phase 1 locked unicode61**
   - What we know: DB-01 text says "trigram tokenizer enabling fuzzy/typo-tolerant search"
   - What's locked: `unicode61 tokenchars '-_' remove_diacritics 2` (Phase 1 locked decision)
   - Recommendation: Implement `unicode61` (locked decision takes precedence over requirement text).
     The planner should note this discrepancy but not block on it. The unicode61 tokenizer satisfies
     the snake_case requirement (DB-01 success criterion 4).

2. **design_chats: ingest scope for Phase 2?**
   - What we know: 2 design chats in export, different message schema (role/content dict, no sender/text/attachments)
   - What's unclear: Whether users want design_chats searchable
   - Recommendation: Skip in Phase 2. Add a `design_chats_fts` table in a future phase if needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| SQLite with FTS5 | db.py, all search | Yes | 3.50.4 | — |
| Python 3.11+ | `datetime.fromisoformat()` Z-suffix support | Yes (3.14.0) | 3.14.0 | — |
| Export ZIP on disk | ingest.py smoke test | Yes | n/a | — |
| uv | `uv run ingest` entry point | Yes | 0.11.8 | — |

**No missing dependencies.**

---

## Security Domain

> `security_enforcement` not set to false — included per protocol.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — (local CLI tool, no auth) |
| V3 Session Management | No | — (no sessions) |
| V4 Access Control | No | — (single-user local tool) |
| V5 Input Validation | Partial | Parameterized SQL queries throughout (no string interpolation) |
| V6 Cryptography | No | — (no encryption needed for local history) |

### Known Threat Patterns for Python + SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via ZIP content | Tampering | All SQL uses `?` parameterized queries — verified in code examples above |
| Path traversal in zip_path argument | Elevation | argparse receives path; `Path(zip_path)` normalizes; `zipfile.ZipFile` validates ZIP structure |
| stdout contamination corrupting MCP session | Denial of Service | All logging via `logging` module to `sys.stderr`; no `print()` in ingest.py |

---

## Sources

### Primary (HIGH confidence)
- `https://www.sqlite.org/fts5.html` — FTS5 content table pattern, trigger SQL, tokenizer config
- `https://www.sqlite.org/pragma.html#pragma_journal_mode` — WAL mode PRAGMA
- Live SQLite 3.50.4 + Python 3.14.0 verification — all SQL patterns tested against actual runtime
- Live export ZIP inspection — attachment structure, timestamp formats, message counts, file types

### Secondary (MEDIUM confidence)
- `https://sqlite.org/forum/forumpost/acdc2aa30a` — INTEGER PRIMARY KEY requirement for FTS5 content_rowid
- `https://simonh.uk/2021/05/11/sqlite-fts5-triggers/` — AFTER UPDATE trigger pattern (confirmed by official docs)

### Tertiary (LOW confidence)
- WebSearch result: "PRAGMA recursive_triggers needed for INSERT OR REPLACE" — not further verified;
  avoided entirely by using INSERT OR IGNORE instead

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all stdlib, confirmed installed
- Schema: HIGH — verified against live SQLite 3.50.4 with FTS5
- Attachment handling: HIGH — verified against real export ZIP (50 attachments, all pre-extracted)
- Pitfalls: HIGH — live tests confirmed INSERT OR REPLACE orphan behavior, rowid stability issue
- Project association: HIGH — confirmed no project field in conversations.json via Phase 1 + live inspection

**Research date:** 2026-05-04
**Valid until:** 2026-08-04 (stable — SQLite FTS5 API is stable; no fast-moving dependencies)

---

## Correction to ROADMAP Sketch

The ROADMAP plans sketch mentions "BEFORE DELETE / AFTER INSERT triggers". The correct SQL from
official SQLite FTS5 documentation (§4.4.3) is `AFTER DELETE` and `AFTER INSERT`. The planner
should use `AFTER DELETE` in all trigger definitions. [VERIFIED: https://www.sqlite.org/fts5.html]
