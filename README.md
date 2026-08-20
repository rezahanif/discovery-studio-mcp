# Discovery Studio MCP — AiConnect Connector (BIOVIA Discovery Studio)

Adaptation of [`discovery-studio-mcp`](https://github.com/rezahanif/discovery-studio-mcp)
(MIT, v0.1.0) into an AiConnect connector.
Integration family: **HOST_PLUGIN**.

```
AiConnect Process Manager
    │  stdio
    ▼
run_server.py  (this package, spawned by the PM)
    │  license gate + envelope wrap (monkey-patches call_tool handler)
    ▼
discovery_studio_mcp.server  (upstream Python MCP server, mcp SDK)
    │  stdio transport
    ▼
discovery_studio_mcp.adapters  (DiscoveryScript / Filesystem / Mock)
    │  Perl scripts + DS API / file parsing
    ▼
BIOVIA Discovery Studio 2020 (Windows desktop)
```

This is NOT a remote/cloud execution model. Discovery Studio **runs locally**
on the user's Windows machine; the connector provides MCP tool access to its
molecular modeling capabilities.

## ⚠️ Host prerequisite (read first)

**The Process Manager does not install or provide BIOVIA Discovery Studio.**

- The user must already have a supported **Discovery Studio 2020 (20.1)**
  installation on a Windows machine.
- The server auto-detects DS at `C:\Program Files\BIOVIA\Discovery Studio 2020`.
  Set `DS_HOME` in `.env` if installed elsewhere.
- Optional: **Pipeline Pilot Server** for protocol execution. Without it,
  structure inspection and file operations still work (or use mock mode).
- The connector communicates only with the local DS installation. If
  Discovery Studio is not installed, the server starts in mock mode and
  tool calls return synthetic data.

## Authentication — two independent layers

| Layer | Authority | Question it answers |
|---|---|---|
| AiConnect license (`MCP_LICENSE_TOKEN`, HS256, minted per spawn) | AiConnect gateway | "May this agent use discovery-studio-mcp?" |
| Discovery Studio license | Dassault Systèmes (vendor) | "May this machine run Discovery Studio?" |

Different authorities. The AiConnect token governs **only** AiConnect
entitlement; it must not replace, proxy, or bypass the Discovery Studio
vendor licensing mechanism. The connector's license gate is enforced at
the MCP handler boundary: startup + per tool call.

## AiConnect adapter (`src/discovery_studio_mcp/aioconnect.py`)

- **License gate**: `MCP_LICENSE_TOKEN` validated at startup and per tool
  call (monkey-patches the MCP server's `call_tool` handler to intercept
  `CallToolRequest` before forwarding). Invalid/expired → structured
  `fail("LICENSE")` envelope; no tool call is forwarded.
- **Response envelope**: every forwarded tool result is wrapped in
  `ok(data)` XOR `fail(code, message)` (tool-response.schema.json).
- **Env-gated**: `AICONNECT_ENABLE=1` only (set by the Process Manager
  on managed spawns). Standalone (`python -m discovery_studio_mcp.server`)
  = pure upstream behaviour.
- **Zero upstream modifications**: all 12 tools preserved unchanged.
  The adapter hooks into `server.request_handlers` at runtime.

## Security assessment

| Tool module | Tools | Classification |
|---|---|---|
| Diagnostics | `ds_get_capabilities`, `ds_health_check` | NORMAL — read-only status |
| Structures | `ds_inspect_structure`, `ds_validate_structure`, `ds_convert_structure` | NORMAL — file parsing, no exec |
| Protocols | `ds_list_protocols`, `ds_describe_protocol`, `ds_run_protocol` | NORMAL — delegated to Pipeline Pilot |
| Jobs | `ds_get_job_status`, `ds_cancel_job`, `ds_list_jobs` | NORMAL — job lifecycle |
| Visualization | `ds_render_structure` | NORMAL — requires GUI session |

- **No arbitrary execution tools** — all 12 tools are domain-specific
  Discovery Studio operations.
- The upstream README explicitly documents: "No arbitrary code execution".
- Security features: path traversal protection, whitelist-based extension
  validation, output isolation, protocol whitelist, destructive action
  confirmation.
- The connector never sends credentials through the AiConnect cloud;
  all operations are local.

## Tests

- Adapter: `python3 tests/check_aioconnect.py` → **9/9** (license gate,
  per-call recheck, envelope helpers, disabled mode, patch no-op).
- Round-trip: `python3 tests/roundtrip_proxy.py` → **12/12** (initialize,
  tools/list, tools/call, license gate, envelope wrap, patch behaviour)
  against `tests/mock_ds_server.py`, a standalone mock of the DS MCP
  server — no Discovery Studio needed.
- **LIVE DS VALIDATION BLOCKED** — no BIOVIA Discovery Studio on this
  machine (Windows desktop software).

## Source mapping (upstream → AiConnect)

| Upstream | AiConnect |
|---|---|
| `python -m discovery_studio_mcp.server` | `run_server.py` (AiConnect entry, `stdio: true`) |
| `mcp.server.Server` + `stdio_server` | same — monkey-patched at runtime |
| 12 tools across 5 categories | unchanged — all tools preserved |
| 3 adapters (DiscoveryScript, Filesystem, Mock) | unchanged |
| `DS_MOCK_MODE=true` | same — for development without DS |

## Attribution

- Upstream: `discovery-studio-mcp` — MIT License, Copyright (c) 2026.
  LICENSE preserved verbatim at `./LICENSE`.
- BIOVIA Discovery Studio is a proprietary commercial product of Dassault
  Systèmes; its license is separate from this connector's MIT license.
