---
title: Claude History MCP Server
type: software
status: working
wp_page_id: 237
github_url: https://github.com/twostar01/claude-history
---

## What It Does

A local MCP server that makes Claude.ai conversation history queryable from any Claude Code session. Export your full history from Claude.ai, run an ingest script that loads it into a local SQLite database with FTS5 full-text search, then query it via MCP tools. Any Claude Code session can pull relevant context from past conversations without loading the full history into the prompt.

## How It Works

Two processes share one SQLite database file. An ingest script parses Claude.ai export ZIPs and loads conversations and messages into an FTS5 full-text search table using the BM25 ranking model. A FastMCP stdio server exposes six tools — search, retrieve, list, stats, export, and status — that Claude Code can call from any session. The server runs over stdio transport so Claude Code manages the process lifecycle; no daemon or scheduler required.

v1.1 adds date/role search filters, file export, and incremental ingest so only new messages are appended on re-run.
