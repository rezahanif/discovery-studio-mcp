#!/usr/bin/env python3
"""AiConnect entrypoint for the discovery-studio-mcp connector.

The Process Manager spawns `python3 run_server.py` (manifest `entry`) from
this directory. Imports the upstream server, applies the AiConnect adapter
(license gate + envelope wrap), then starts the MCP stdio server.

AICONNECT_ENABLE=1 (set by the Process Manager on managed spawns) activates
the AiConnect adapter: startup license gate + per-call tool interception.
Without it the server runs exactly like upstream.

Requires: pip install -e . (from project root) or mcp + pydantic + pydantic-settings
"""
import os
import sys

# Add src/ to path so discovery_studio_mcp package is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from discovery_studio_mcp.aioconnect import ensure_licensed, patch_server_call_tool  # noqa: E402
from discovery_studio_mcp import server as server_module  # noqa: E402


def main():
    # Startup license gate
    ensure_licensed()

    # Patch the server's call_tool handler with license gate + envelope
    patch_server_call_tool(server_module.server)

    # Run the upstream server's main (stdio transport)
    import asyncio
    asyncio.run(server_module.main())


if __name__ == "__main__":
    main()
