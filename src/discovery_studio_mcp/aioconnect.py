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

The shared AiConnect Python SDK (connector-sdk/python in the AiConnect
monorepo) is located by walking up from this file, or via AICONNECT_SDK_PATH
(the name every other connector in the portfolio uses; AICONNECT_SDK_DIR is
accepted too, for anything already relying on this file's original name).

If the SDK genuinely cannot be found, the module still imports (so upstream
usage without AICONNECT_ENABLE stays fully standalone-usable — no security
module needs to exist for that path at all), but `ensure_licensed()` and
`check_tool_license()` FAIL CLOSED the moment `_enabled()` is true: they
raise/refuse rather than silently behaving as if the gate passed. An earlier
version of this file used no-op stub classes here, which meant any host
missing the SDK - or, worse, any host where only the portfolio-standard
AICONNECT_SDK_PATH was set instead of this file's then-unique
AICONNECT_SDK_DIR - would run with AICONNECT_ENABLE=1 and serve every
request as if a valid license had been presented. Confirmed live: the
server started and began accepting calls with AICONNECT_ENABLE=1 set and no
MCP_LICENSE_TOKEN at all, exit 0, no warning anywhere.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SDK_IMPORT_ERROR: Exception | None = None
try:
    _here = Path(__file__).resolve()
    _sdk = None
    for p in _here.parents:
        cand = p / "sdk" / "python"
        if (cand / "mcp_license_sdk").is_dir():
            _sdk = cand
            break
        cand = p / "connector-sdk" / "python"
        if (cand / "mcp_license_sdk").is_dir():
            _sdk = cand
            break
    if _sdk is None:
        _env = os.environ.get("AICONNECT_SDK_PATH") or os.environ.get("AICONNECT_SDK_DIR")
        if _env and (Path(_env) / "mcp_license_sdk").is_dir():
            _sdk = Path(_env)
    if _sdk is not None and str(_sdk) not in sys.path:
        sys.path.insert(0, str(_sdk))

    from mcp_license_sdk import LicenseError, LicenseValidator, fail, ok  # noqa: E402
except ImportError as _e:
    _SDK_IMPORT_ERROR = _e

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
    if _SDK_IMPORT_ERROR is not None:
        raise LicenseError(
            "AiConnect enabled (AICONNECT_ENABLE=1) but the license SDK could "
            f"not be imported ({_SDK_IMPORT_ERROR}); refusing to serve rather "
            "than silently disabling the license gate. Set AICONNECT_SDK_PATH "
            "to the connector-sdk/python directory."
        )
    LicenseValidator(_secret()).ensure_licensed()


def check_tool_license() -> dict | None:
    """Per-call license check. Returns fail envelope or None if OK."""
    if not _enabled():
        return None
    if _SDK_IMPORT_ERROR is not None:
        return fail("LICENSE", f"License SDK unavailable: {_SDK_IMPORT_ERROR}")
    try:
        LicenseValidator(_secret()).ensure_licensed()
        return None
    except LicenseError as e:
        return fail("LICENSE", str(e))


def _is_error_payload(value) -> bool:
    """True for the shape every `call_tool` `except` block returns on
    failure: `{"error": str, "type": str, "suggested_actions": [...]}` - a
    normal, successful Python return, never a raised exception. Shared by
    `wrap_result` (picks ok() vs fail()) and `patch_server_call_tool`
    (sets CallToolResult.isError to match)."""
    return isinstance(value, dict) and "error" in value and set(value) <= {
        "error", "type", "suggested_actions"
    }


def wrap_result(result_list) -> str:
    """Wrap a tool result value in the AiConnect envelope.

    Detects the connector's own `{"error": ...}` failure shape (see
    `_is_error_payload`) and produces a real `fail()` envelope instead of
    `ok()` wrapping error data as if it were a successful result. Every
    other shape is a genuine success and gets `ok(data)` as before.
    """
    if _is_error_payload(result_list):
        return json.dumps(fail(
            str(result_list.get("type", "TOOL_ERROR")).upper(),
            str(result_list["error"]),
            suggested_actions=result_list.get("suggested_actions"),
        ))
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
        from mcp.types import CallToolResult, ServerResult, TextContent

        # License gate: check before forwarding
        license_fail = check_tool_license()
        if license_fail is not None:
            # request_handlers[CallToolRequest] must return ServerResult, the
            # same contract original_handler (the low-level call_tool()
            # decorator's own handler) uses - a bare CallToolResult here is a
            # type-contract violation the dispatch layer wasn't built for.
            return ServerResult(
                CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(license_fail))],
                    isError=True,
                )
            )

        # Forward to original handler. Returns ServerResult (a pydantic
        # RootModel) - the actual CallToolResult is at .root, never a direct
        # attribute of the ServerResult itself. Checking hasattr(result,
        # "content") directly is always False; the whole envelope wrap below
        # silently never ran until this was unwrapped correctly.
        result = await original_handler(req)
        inner = getattr(result, "root", result)

        # Envelope wrap: wrap the result content
        try:
            if hasattr(inner, "content") and inner.content:
                text_parts = []
                for block in inner.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                if text_parts:
                    raw = "".join(text_parts)
                    parsed = json.loads(raw) if raw.startswith("[") or raw.startswith("{") else raw
                    wrapped = wrap_result(parsed)
                    inner.content = [TextContent(type="text", text=wrapped)]
                    if _is_error_payload(parsed):
                        inner.isError = True
        except Exception:
            pass  # Keep original result on envelope failure

        return result

    server.request_handlers[CallToolRequest] = _wrapped_handler
