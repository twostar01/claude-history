# Claude.ai Export Schema

Discovered from: data-030cd706-d473-447c-a7fe-b6d98e4f1277-1777822473-5f91f1fb-batch-0000.zip
Discovered at: 2026-05-04T13:59:20Z
Export contains: 11 files

## ZIP File Structure

| Member | Structure | Count / Note |
|--------|-----------|--------------|
| `conversations.json` | array | 11 total files in ZIP |
| `projects/019cbca7-e864-72c0-924e-ab279c7ab0f7.json` | object (single project dict) | one file per project |
| `projects/019cd101-c3cf-75d0-b16e-ece9d329ad23.json` | object (single project dict) | one file per project |
| `projects/019cd157-ec52-757d-be8c-1867ee29ad7c.json` | object (single project dict) | one file per project |
| `projects/019cdadf-4192-7738-884d-a89c2eb11eb3.json` | object (single project dict) | one file per project |
| `projects/019d1b28-8f99-7470-99a7-5f434d216ac0.json` | object (single project dict) | one file per project |
| `projects/019d507d-57ea-737d-b8ba-c4350d410202.json` | object (single project dict) | one file per project |
| `projects/019d6915-2de3-74ae-80e4-f43f6b75ed31.json` | object (single project dict) | one file per project |
| `design_chats/4cd73b30-2cb5-4e9b-a97e-8eb86051401d.json` | object (single design chat dict) | one file per design chat |
| `design_chats/36b247a6-c456-4588-88aa-4fb4aa8d8a14.json` | object (single design chat dict) | one file per design chat |
| `users.json` | array | array with 1 user object |

## conversations.json — Conversation Object

Top-level: array of 106 conversation object(s).

| Field | Type | Example |
|-------|------|---------|
| `uuid` | str | '7baea923-be88-434f-bd1c-4fe5ad300d03' |
| `name` | str | '' |
| `summary` | str | '' |
| `created_at` | str | '2026-04-01T23:44:12.155755Z' |
| `updated_at` | str | '2026-04-02T02:35:12.897827Z' |
| `account` | object | {uuid} |
| `chat_messages` | array | [...] (2 items) |

## conversations.json — Message Object (chat_messages[n])

| Field | Type | Example |
|-------|------|---------|
| `uuid` | str | '019d4b6e-e8a0-70fc-9f08-7e3ba161000d' |
| `text` | str | '' |
| `content` | array | [...] (1 items) |
| `sender` | str | 'human' |
| `created_at` | str | '2026-04-01T23:44:13.022248Z' |
| `updated_at` | str | '2026-04-02T02:35:13.551950Z' |
| `attachments` | array | [...] (0 items) |
| `files` | array | [...] (0 items) |
| `parent_message_uuid` | str | '00000000-0000-4000-8000-000000000000' |

## projects/UUID.json — Project Object

One file per project. Each file is a single dict (not an array).

| Field | Type | Example |
|-------|------|---------|
| `uuid` | str | '019cbca7-e864-72c0-924e-ab279c7ab0f7' |
| `name` | str | 'Nature Pi' |
| `description` | str | 'This is a self contained raspberry pi with solar charging po...' |
| `is_private` | bool | True |
| `is_starter_project` | bool | False |
| `prompt_template` | str | 'Project Context\nThis project involves building a monitoring ...' |
| `created_at` | str | '2026-03-05T06:20:46.561314+00:00' |
| `updated_at` | str | '2026-03-05T06:28:53.577317+00:00' |
| `creator` | object | {uuid, full_name} |
| `docs` | array | [...] (0 items) |

> **Note:** Timestamp format uses `+00:00` offset (e.g., `"2026-03-05T06:20:46.561314+00:00"`), not the `Z` suffix seen in conversations.json.

## design_chats/UUID.json — Design Chat Object

One file per design chat. Different message schema from conversations.

| Field | Type | Example |
|-------|------|---------|
| `uuid` | str | '4cd73b30-2cb5-4e9b-a97e-8eb86051401d' |
| `title` | str | 'Chat' |
| `project` | object | {uuid, name} |
| `created_at` | str | '2026-04-22T02:41:30.765229+00:00' |
| `updated_at` | str | '2026-04-22T03:48:23.875487+00:00' |
| `messages` | array | [...] (2 items) |

## users.json — User Object

| Field | Type | Example |
|-------|------|---------|
| `uuid` | str | 'fab81771-653b-405a-9d5f-e059ab02bea4' |
| `full_name` | str | 'Nash Clemens' |
| `email_address` | str | 'nclemens.cp@gmail.com' |
| `verified_phone_number` | null | None |

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
