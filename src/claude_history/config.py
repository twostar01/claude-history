"""Configuration constants for the claude-history MCP server."""

from pathlib import Path

# Resolve DB_PATH relative to this file so it works regardless of working directory.
# src/claude_history/config.py is 3 levels below the project root:
#   config.py -> claude_history/ -> src/ -> project root
DB_PATH: Path = Path(__file__).parent.parent.parent / "history.db"
