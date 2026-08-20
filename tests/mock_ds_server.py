"""Mock Discovery Studio MCP server for proxy testing.

Implements a minimal MCP JSON-RPC server over stdio that responds to:
  - initialize
  - tools/list (returns the 12 ds_* tools)
  - tools/call (returns mock data)

Used by roundtrip_proxy.py to test the adapter without Discovery Studio.
"""

import json
import sys


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


TOOLS = [
    {"name": "ds_get_capabilities", "description": "Get DS capabilities", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ds_health_check", "description": "Health check", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ds_inspect_structure", "description": "Inspect structure", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "ds_validate_structure", "description": "Validate structure", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "workflow": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "ds_convert_structure", "description": "Convert structure", "inputSchema": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_format": {"type": "string"}}, "required": ["input_path", "output_format"]}},
    {"name": "ds_list_protocols", "description": "List protocols", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ds_describe_protocol", "description": "Describe protocol", "inputSchema": {"type": "object", "properties": {"protocol_name": {"type": "string"}}, "required": ["protocol_name"]}},
    {"name": "ds_run_protocol", "description": "Run protocol", "inputSchema": {"type": "object", "properties": {"protocol_name": {"type": "string"}}, "required": ["protocol_name"]}},
    {"name": "ds_get_job_status", "description": "Get job status", "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "ds_cancel_job", "description": "Cancel job", "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "ds_list_jobs", "description": "List jobs", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ds_render_structure", "description": "Render structure", "inputSchema": {"type": "object", "properties": {"molecule_path": {"type": "string"}}, "required": ["molecule_path"]}},
]


def handle(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "mock-discovery-studio", "version": "0.1.0"},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = msg.get("params", {}).get("name", "")
        if tool_name == "ds_get_capabilities":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps({"mock": True, "version": "2020", "adapters": ["mock"]})}]},
            }
        elif tool_name == "ds_inspect_structure":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps({"mock": True, "format": "pdb", "chains": ["A"], "atoms": 1000})}]},
            }
        else:
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps({"mock": True, "tool": tool_name})}]},
            }
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(msg)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
