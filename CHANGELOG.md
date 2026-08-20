# Changelog

All notable changes to the Discovery Studio MCP project are documented here.

## 1.0.0 — AiConnect adaptation

- Added `src/discovery_studio_mcp/aioconnect.py`: AiConnect license gate
  (startup + per-call interception of `CallToolRequest` via monkey-patch)
  and central response-envelope wrap.
- Added `run_server.py` (AiConnect entry, `stdio: true`) and `manifest.json`.
- Tests: `tests/check_aioconnect.py` (9/9), `tests/mock_ds_server.py`,
  `tests/roundtrip_proxy.py` (12/12) — offline, no Discovery Studio required.
- README documents the host prerequisite, the two independent authentication
  layers, and the clean security posture (no arbitrary execution tools).
- All 12 upstream tools preserved unchanged — no tool surface modifications.
- Zero modifications to any upstream source files.
