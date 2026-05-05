"""schema_discovery.py — Inspect a Claude.ai export ZIP and write .planning/SCHEMA.md.

Usage:
    uv run schema-discovery <path-to-export.zip>

Standalone script: does NOT import from claude_history.config or claude_history.server.
Makes NO database writes — read-only inspection only.
"""

from __future__ import annotations

import json
import sys
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _infer_type(value: object) -> str:
    """Return a human-readable type label for a JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _truncate(value: object, max_len: int = 60) -> str:
    """Return a short string representation of any value."""
    if isinstance(value, str):
        if len(value) > max_len:
            return repr(value[:max_len] + "...")
        return repr(value)
    if isinstance(value, list):
        return f"[...] ({len(value)} items)"
    if isinstance(value, dict):
        keys = list(value.keys())
        keys_preview = ", ".join(keys[:4])
        if len(keys) > 4:
            keys_preview += ", ..."
        return "{" + keys_preview + "}"
    return repr(value)


def _fields_table(obj: dict) -> str:
    """Render a Markdown table of field | type | example for a dict object."""
    rows = ["| Field | Type | Example |", "|-------|------|---------|"]
    for field, value in obj.items():
        rows.append(f"| `{field}` | {_infer_type(value)} | {_truncate(value)} |")
    return "\n".join(rows)


def main() -> None:
    """Entry point for the schema-discovery command."""
    if len(sys.argv) < 2:
        print("Usage: uv run schema-discovery <path-to-export.zip>", file=sys.stderr)
        sys.exit(1)

    zip_path = Path(sys.argv[1])
    if not zip_path.exists():
        print(f"Error: file not found: {zip_path}", file=sys.stderr)
        sys.exit(1)

    try:
        _run(zip_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def _run(zip_path: Path) -> None:
    """Core logic: inspect the ZIP and write SCHEMA.md."""
    discovered_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with zipfile.ZipFile(zip_path) as zf:
        all_members = zf.namelist()
        print(f"ZIP contains {len(all_members)} files:", file=sys.stderr)
        for name in all_members:
            print(f"  {name}", file=sys.stderr)

        # --- Categorise members ---
        project_members = [n for n in all_members if n.startswith("projects/")]
        design_chat_members = [n for n in all_members if n.startswith("design_chats/")]

        # --- ZIP structure table ---
        zip_rows = ["| Member | Structure | Count / Note |",
                    "|--------|-----------|--------------|"]

        def _add_zip_row(member: str, structure: str, note: str) -> None:
            zip_rows.append(f"| `{member}` | {structure} | {note} |")

        _add_zip_row(
            "conversations.json",
            "array",
            f"{len(all_members)} total files in ZIP",
        )
        for pm in project_members:
            _add_zip_row(pm, "object (single project dict)", "one file per project")
        for dm in design_chat_members:
            _add_zip_row(dm, "object (single design chat dict)", "one file per design chat")
        if "users.json" in all_members:
            _add_zip_row("users.json", "array", "array with 1 user object")

        # --- conversations.json ---
        print("Inspecting conversations.json ...", file=sys.stderr)
        with zf.open("conversations.json") as f:
            convs = json.load(f)

        conv_count = len(convs) if isinstance(convs, list) else 1
        first_conv = convs[0] if (isinstance(convs, list) and convs) else convs

        conv_table = _fields_table(first_conv)

        # --- Message object (chat_messages[n]) ---
        first_msg = None
        for conv in (convs if isinstance(convs, list) else [convs]):
            msgs = conv.get("chat_messages", [])
            if msgs:
                first_msg = msgs[0]
                break

        msg_table = _fields_table(first_msg) if first_msg else "_No messages found in sample_"

        # --- projects/UUID.json ---
        project_table = ""
        project_ts_note = ""
        if project_members:
            print(f"Inspecting {project_members[0]} ...", file=sys.stderr)
            with zf.open(project_members[0]) as f:
                project_obj = json.load(f)
            project_table = _fields_table(project_obj)
            project_ts_note = (
                "\n\n> **Note:** Timestamp format uses `+00:00` offset "
                "(e.g., `\"2026-03-05T06:20:46.561314+00:00\"`), "
                "not the `Z` suffix seen in conversations.json."
            )

        # --- design_chats/UUID.json ---
        design_chat_table = ""
        if design_chat_members:
            print(f"Inspecting {design_chat_members[0]} ...", file=sys.stderr)
            with zf.open(design_chat_members[0]) as f:
                dc_obj = json.load(f)
            design_chat_table = _fields_table(dc_obj)

        # --- users.json ---
        user_table = ""
        if "users.json" in all_members:
            print("Inspecting users.json ...", file=sys.stderr)
            with zf.open("users.json") as f:
                users = json.load(f)
            first_user = users[0] if (isinstance(users, list) and users) else users
            user_table = _fields_table(first_user)

    # --- Build SCHEMA.md ---
    zip_structure_table = "\n".join(zip_rows)

    schema_content = f"""# Claude.ai Export Schema

Discovered from: {zip_path.name}
Discovered at: {discovered_at}
Export contains: {len(all_members)} files

## ZIP File Structure

{zip_structure_table}

## conversations.json — Conversation Object

Top-level: array of {conv_count} conversation object(s).

{conv_table}

## conversations.json — Message Object (chat_messages[n])

{msg_table}

## projects/UUID.json — Project Object

One file per project. Each file is a single dict (not an array).

{project_table}{project_ts_note}

## design_chats/UUID.json — Design Chat Object

One file per design chat. Different message schema from conversations.

{design_chat_table}

## users.json — User Object

{user_table}

## Timestamp Formats

- `conversations.json`: ISO 8601 with Z suffix (e.g., `"2026-03-28T05:52:32.764454Z"`)
- `projects/UUID.json`: ISO 8601 with +00:00 offset (e.g., `"2026-03-05T06:20:46.561314+00:00"`)
- `datetime.fromisoformat()` in Python 3.11+ handles both formats without a custom parser.

## Project Association Gap

**WARNING for Phase 2:** `conversations.json` entries do NOT contain a `project` field.
There is no direct way to associate a conversation with a project from conversations.json alone.

- `projects/UUID.json` contains project metadata but no list of conversation UUIDs
- `design_chats/UUID.json` DOES contain a `project` field (object with uuid and name)
- Regular conversations in conversations.json are NOT linked to projects in this export format

**Phase 2 decision required:** Either (a) skip project association for conversations and store NULL,
or (b) attempt to infer project association from design_chats. Document the chosen approach in Phase 2 planning.
"""

    # Write SCHEMA.md
    schema_path = Path(__file__).parent.parent.parent / ".planning" / "SCHEMA.md"
    schema_path.write_text(schema_content, encoding="utf-8")

    print(f"\nSchema written to: {schema_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
