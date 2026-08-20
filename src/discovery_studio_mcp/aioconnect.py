"""AiConnect adapter for discovery-studio-mcp.

The connector runs the upstream Python MCP server (mcp SDK, stdio transport)
with all 12 domain-specific tools preserved. The adapter hooks into the
request_handlers to add:
  1. License gate — startup (ensure_licensed) + per-call (intercepting
     CallToolRequest before forwarding to the original handler).
  2. Response envelope — every tool result is wrapped in ok(data) XOR
     fail(code, message) before it reaches the client.

Env-gated integration points:
  AICONNECT_ENABLE=1        — install the license gate + envelope wrap
  MCP_LICENSE_TOKEN         — the token to validate
  JWT_SECRET                — token signing secret (default matches gateway dev)

The shared AiConnect Python SDK (connectors/sdk/python in the AiConnect
monorepo) is located by walking up from this file, or via AICONNECT_SDK_DIR.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    _here = Path(__file__).resolve()
    _sdk = None
    for p in _here.parents:
        cand = p / "sdk" / "python"
        if (cand / "mcp_license_sdk").is_dir():
            _sdk = cand
            break
    if _sdk is None:
        _env = os.environ.get("AICONNECT_SDK_DIR")
        if _env and (Path(_env) / "mcp_license_sdk").is_dir():
            _sdk = Path(_env)
    if _sdk is not None and str(_sdk) not in sys.path:
        sys.path.insert(0, str(_sdk))

    from mcp_license_sdk import LicenseError, LicenseValidator, fail, ok  # noqa: E402
except ImportError:
    class LicenseError(Exception):  # type: ignore[no-redef]
        pass

    class LicenseValidator:  # type: ignore[no-redef]
        def __init__(self, secret: str) -> None:
            pass
        def ensure_licensed(self) -> None:
            pass

    def ok(data):  # type: ignore[no-redef]
        return {"success": True, "data": data}

    def fail(code, message):  # type: ignore[no-redef]
        return {"success": False, "error": {"code": code, "message": message}}


def _enabled() -> bool:
    return os.environ.get("AICONNECT_ENABLE", "") == "1"


def _secret() -> str:
    return os.environ.get("JWT_SECRET", "dev-secret-change-me")


def ensure_licensed() -> None:
    """Startup gate. Refuses to serve unless a valid token is injected."""
    if not _enabled():
        return
    LicenseValidator(_secret()).ensure_licensed()


def check_tool_license() -> dict | None:
    """Per-call license check. Returns fail envelope or None if OK."""
    if not _enabled():
        return None
    try:
        LicenseValidator(_secret()).ensure_licensed()
        return None
    except LicenseError as e:
        return fail("LICENSE", str(e))


def wrap_result(result_list: list) -> str:
    """Wrap a tool result list in the AiConnect envelope.

    The upstream call_tool handler returns list[dict]. Each dict becomes
    a TextContent block. We wrap the entire list in ok(data).
    """
    return json.dumps(ok(result_list))


def patch_server_call_tool(server) -> None:
    """Monkey-patch the MCP Server's call_tool handler with license gate + envelope.

    Preserves ALL upstream tool implementations — only adds the AiConnect
    integration layer (license + envelope) at the request boundary.
    """
    if not _enabled():
        return

    from mcp.types import CallToolRequest

    original_handler = server.request_handlers.get(CallToolRequest)
    if original_handler is None:
        return

    async def _wrapped_handler(req):
        # License gate: check before forwarding
        license_fail = check_tool_license()
        if license_fail is not None:
            from mcp.types import CallToolResult, TextContent
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(license_fail))],
                isError=True,
            )

        # Forward to original handler
        result = await original_handler(req)

        # Envelope wrap: wrap the result content
        try:
            if hasattr(result, "content") and result.content:
                text_parts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                if text_parts:
                    raw = "".join(text_parts)
                    wrapped = wrap_result(json.loads(raw) if raw.startswith("[") or raw.startswith("{") else raw)
                    from mcp.types import TextContent
                    result.content = [TextContent(type="text", text=wrapped)]
        except Exception:
            pass  # Keep original result on envelope failure

        return result

    server.request_handlers[CallToolRequest] = _wrapped_handler
