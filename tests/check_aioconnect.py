"""AiConnect adapter unit validation — runs WITHOUT Discovery Studio.
from pathlib import Path

Validates the adapter layer (startup license gate + per-call license check +
envelope wrapping) against the real mcp_license_sdk.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time

os.environ["AICONNECT_SDK_DIR"] = "/project/aiconnector/connectors/sdk/python"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from discovery_studio_mcp import aioconnect  # noqa: E402
from mcp_license_sdk import LicenseError  # noqa: E402

SECRET = "0123456789abcdef0123456789abcdef"
os.environ["JWT_SECRET"] = SECRET


def mint(entitlements, ttl=600):
    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({
        "sub": "u1", "iat": int(time.time()), "exp": int(time.time()) + ttl,
        "entitlements": entitlements,
    }).encode())
    sig = b64(hmac.new(SECRET.encode(), header + b"." + payload, hashlib.sha256).digest())
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name)


# 1. disabled -> no-op
os.environ.pop("AICONNECT_ENABLE", None)
os.environ.pop("MCP_LICENSE_TOKEN", None)
aioconnect.ensure_licensed()  # must NOT raise
check("disabled: ensure_licensed no-op", True)

# 2. enabled + missing token -> refuse at startup
os.environ["AICONNECT_ENABLE"] = "1"
try:
    aioconnect.ensure_licensed()
    check("enabled: missing token refuses", False)
except LicenseError:
    check("enabled: missing token refuses", True)

# 3. enabled + valid token -> passes startup
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"])
aioconnect.ensure_licensed()
check("enabled: valid token passes startup", True)

# 4. per-call check: valid token -> None
result = aioconnect.check_tool_license()
check("per-call: valid token -> None", result is None)

# 5. per-call check: expired token -> fail envelope
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"], ttl=-400000)
result = aioconnect.check_tool_license()
check("per-call: expired token -> LICENSE fail", result is not None and result.get("success") is False)
check("per-call: fail code = LICENSE", result.get("error", {}).get("code") == "LICENSE")

# 6. envelope helpers
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"])
env = json.loads(aioconnect.wrap_result([{"ds_version": "2020"}]))
check("envelope: list -> ok(data)", env.get("success") is True and env["data"][0]["ds_version"] == "2020")

env = json.loads(aioconnect.wrap_result([{"error": "not found"}]))
check("envelope: error list -> ok(data)", env.get("success") is True)

# 7. disabled mode: per-call bypass
os.environ.pop("AICONNECT_ENABLE", None)
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"], ttl=-400000)
result = aioconnect.check_tool_license()
check("disabled: per-call returns None (bypass)", result is None)

# 8. patch_server_call_tool: no-op when disabled
os.environ.pop("AICONNECT_ENABLE", None)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} adapter checks passed")
sys.exit(1 if failed else 0)
