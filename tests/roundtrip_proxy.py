"""Round-trip proxy validation — runs WITHOUT Discovery Studio.

Tests the adapter by:
  1. Spawning mock_ds_server.py as the MCP server
  2. Sending MCP requests through stdin
  3. Reading responses from stdout
  4. Verifying tool list and tool call responses

Then validates the aioconnect adapter functions directly.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

FORK = Path(__file__).resolve().parents[1]
os.environ.setdefault("AICONNECT_SDK_DIR", str(FORK.parent / "connector-sdk" / "python"))
sys.path.insert(0, str(FORK / "src"))


def mint(entitlements, ttl=600):
    import base64, hashlib, hmac
    SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
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


# --- Test 1: Initialize handshake ---
print("=== Test 1: Initialize ===")
proc = subprocess.Popen(
    [sys.executable, os.path.join(os.path.dirname(__file__), "mock_ds_server.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)

init_msg = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test"}},
}) + "\n"
proc.stdin.write(init_msg.encode())
proc.stdin.flush()

line = proc.stdout.readline().decode().strip()
resp = json.loads(line)
check("initialize: has result", "result" in resp)
check("initialize: protocolVersion", resp.get("result", {}).get("protocolVersion") == "2025-03-26")

proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}).encode() + b"\n")
proc.stdin.flush()

# --- Test 2: tools/list ---
print("\n=== Test 2: tools/list ===")
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode() + b"\n")
proc.stdin.flush()

line = proc.stdout.readline().decode().strip()
resp = json.loads(line)
tools = resp.get("result", {}).get("tools", [])
check("tools/list: has 12 tools", len(tools) == 12)
check("tools/list: ds_get_capabilities exists", any(t["name"] == "ds_get_capabilities" for t in tools))
check("tools/list: ds_run_protocol exists", any(t["name"] == "ds_run_protocol" for t in tools))

# --- Test 3: tools/call ---
print("\n=== Test 3: tools/call ===")
proc.stdin.write(json.dumps({
    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
    "params": {"name": "ds_get_capabilities", "arguments": {}},
}).encode() + b"\n")
proc.stdin.flush()

line = proc.stdout.readline().decode().strip()
resp = json.loads(line)
text = resp.get("result", {}).get("content", [{}])[0].get("text", "")
caps = json.loads(text)
check("tools/call: capabilities has mock", caps.get("mock") is True)

proc.terminate()
proc.wait(timeout=5)

# --- Test 4: Adapter functions (enabled, valid token) ---
print("\n=== Test 4: Adapter (enabled, valid token) ===")
SECRET = "0123456789abcdef0123456789abcdef"
os.environ["JWT_SECRET"] = SECRET
os.environ["AICONNECT_ENABLE"] = "1"
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"])

from discovery_studio_mcp import aioconnect

result = aioconnect.check_tool_license()
check("adapter: valid token -> None", result is None)

wrapped = aioconnect.wrap_result([{"success": True, "data": {"v": 42}}])
env = json.loads(wrapped)
check("adapter: wrap_result -> ok envelope", env.get("success") is True)

# --- Test 5: Adapter (enabled, expired token) ---
print("\n=== Test 5: Adapter (enabled, expired token) ===")
os.environ["MCP_LICENSE_TOKEN"] = mint(["discovery-studio-mcp"], ttl=-400000)
result = aioconnect.check_tool_license()
check("adapter: expired token -> LICENSE fail", result is not None)
check("adapter: fail code = LICENSE", result.get("error", {}).get("code") == "LICENSE")

# --- Test 6: Disabled mode ---
print("\n=== Test 6: Disabled mode ===")
os.environ.pop("AICONNECT_ENABLE", None)
result = aioconnect.check_tool_license()
check("adapter: disabled -> None (bypass)", result is None)

# --- Test 7: patch_server_call_tool no-op when disabled ---
print("\n=== Test 7: Patch no-op ===")
os.environ.pop("AICONNECT_ENABLE", None)

from mcp.server import Server
s = Server("test-patch")
original_handlers = dict(s.request_handlers)
aioconnect.patch_server_call_tool(s)
check("patch: no-op when disabled (handlers unchanged)", s.request_handlers == original_handlers)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} round-trip checks passed")
sys.exit(1 if failed else 0)
