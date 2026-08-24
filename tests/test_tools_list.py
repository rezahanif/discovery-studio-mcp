"""Integration test: spawn MCP server, send tools/list, verify 15 tools."""

import json
import subprocess
import sys
from pathlib import Path


def test_tools_list():
    """Spawn run_server.py, exchange initialize + tools/list, assert 15 tools."""
    server_script = Path(__file__).resolve().parent.parent / "run_server.py"

    proc = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**__import__("os").environ, "DS_MOCK_MODE": "true"},
    )

    def send(msg):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        return json.loads(line)

    try:
        # 1. initialize
        send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1.0"},
            },
        })
        init_resp = recv()
        assert "result" in init_resp, f"initialize failed: {init_resp}"

        # 2. initialized notification
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. tools/list
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_resp = recv()
        assert "result" in tools_resp, f"tools/list failed: {tools_resp}"
        tools = tools_resp["result"]["tools"]
        assert len(tools) == 15, f"expected 15 tools, got {len(tools)}"
        names = {t["name"] for t in tools}
        assert "ds_get_capabilities" in names
        assert "ds_list_api_categories" in names
    finally:
        proc.terminate()
        proc.wait(timeout=5)
