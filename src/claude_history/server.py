"""Claude History MCP Server — FastMCP stdio stub (Phase 1)."""

import sys
sys.stderr.reconfigure(encoding="utf-8")  # must precede all other imports

import logging

# STDOUT CONTAMINATION RULE: logging.basicConfig() MUST be called before any
# FastMCP instantiation. The FastMCP stdio transport uses stdout exclusively for
# JSON-RPC framing. Any write to stdout silently corrupts the session.

from mcp.server.fastmcp import FastMCP


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

    @mcp.tool()
    def get_status() -> dict:
        """Return server health status. Smoke test target for Phase 1."""
        return {"status": "ok"}

    # Step 3: Start the MCP stdio loop (blocks until client disconnects)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
