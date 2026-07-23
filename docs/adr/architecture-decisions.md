# Architecture Decision Records for Discovery Studio MCP

## ADR-001: Choice of Programming Language

**Status**: Accepted

**Context**:
The MCP server needs to integrate with BIOVIA Discovery Studio, which provides
a Perl-based scripting API (DiscoveryScript). The MCP SDK for Python is mature
and well-supported.

**Decision**: Python 3.11+

**Rationale**:
- Official MCP Python SDK (`mcp>=1.0.0`) provides robust stdio transport support
- Pydantic enables strict typing for tool inputs/outputs
- Python's subprocess module allows calling the bundled Perl interpreter
- Wide ecosystem for testing, linting, and packaging
- Python 3.11 is available in the working environment

**Consequences**:
- Perl scripts must be invoked via subprocess, not natively
- Type safety provided by Pydantic models


## ADR-002: Choice of MCP SDK

**Status**: Accepted

**Context**:
Two official Python MCP SDKs exist: `mcp` (from Anthropic) and `fastmcp`
(higher-level wrapper). The `mcp` package v1.26.0 is available in the
environment; `fastmcp` is not installed.

**Decision**: Use `mcp` (v1.26.0) directly, not `fastmcp`.

**Rationale**:
- `mcp` v1.26.0 is installed and proven in the local environment
- Direct use of the lower-level SDK gives full control over tool registration
- `fastmcp` is not available and would require additional installation
- The `mcp` package provides the `@server.list_tools()` and `@server.call_tool()`
  decorator pattern that maps well to our adapter architecture

**Consequences**:
- Slightly more boilerplate than `fastmcp` for tool registration
- More explicit control over the MCP protocol interaction


## ADR-003: Choice of Primary Adapter

**Status**: Accepted

**Context**:
Discovery Studio 2020 provides three automation paths:
1. DiscoveryScript (bundled Perl 5.26.1 API)
2. Pipeline Pilot Server (protocol execution, requires license)
3. UI Automation (computer use fallback)

**Decision**: Use DiscoveryScript adapter as primary, with adapter fallback chain:
DiscoveryScript -> Filesystem -> Mock

**Rationale**:
- DiscoveryScript API is documented, tested, and part of the standard installation
- Perl modules (MdmDiscoveryScript, ForceFieldDiscoveryScript, ProtocolDiscoveryScript,
  DSScript) provide rich functionality for structure manipulation
- No additional server infrastructure required unlike Pipeline Pilot
- Protocol execution delegates to Pipeline Pilot when available
- Mock adapter enables development without live DS installation

**Consequences**:
- Structure inspection can work without DS client running (CLI Perl mode)
- Protocol execution requires DS_PIPELINE_PILOT_URL configuration
- Rendering requires active GUI session or remains unavailable


## ADR-004: Security Model

**Status**: Accepted

**Context**:
The MCP server must prevent:
- Arbitrary code execution
- Path traversal attacks
- Access to unauthorized directories
- Uncontrolled file overwrites

**Decision**: Multi-layer security model.

**Rules**:
1. **Path validation**: All file paths resolved to absolute and checked against
   allowed input directories
2. **Extension whitelist**: Only known scientific file formats accepted
3. **File size limits**: Configurable max file size (default 500 MB)
4. **Output isolation**: All outputs go to a configured workspace directory
5. **No arbitrary code**: No tool accepts raw Perl, Python, PowerShell, or shell
6. **Protocol whitelist**: Only explicitly listed protocols can be executed
7. **Destructive action confirmation**: Dangerous operations require explicit
   `confirm_destructive_action: true`
8. **Job isolation**: Each job gets a unique subdirectory under workspace/jobs/

**Consequences**:
- Users must pre-configure allowed input directories
- Some operations require explicit confirmation


## ADR-005: Job Management

**Status**: Accepted

**Context**:
Long-running Discovery Studio operations (docking, minimization, simulation)
can take minutes to hours. Synchronous MCP tool calls would block.

**Decision**: Jobs tracked in-memory with status polling.

**Rationale**:
- For MVP, in-memory job tracking with dict-based storage
- Each job gets a unique UUID-based job_id
- Client polls via `ds_get_job_status`
- Output files stored in workspace/jobs/<job_id>/
- `manifest.json` records full reproducibility metadata

**Consequences**:
- Jobs lost on server restart (acceptable for MVP)
- Future: could add persistent job storage (SQLite)


## ADR-006: UI Fallback Strategy

**Status**: Accepted

**Context**:
Some operations (rendering, binding site visualization) may only be possible
through Discovery Studio's GUI. UI automation via pyautogui/pywinauto could
fill these gaps.

**Decision**: UI fallback disabled by default (`DS_ENABLE_UI_FALLBACK=false`),
isolated in separate adapter.

**Rationale**:
- UI automation is fragile and version-dependent
- Should not be the default path for any operation
- Must be explicitly enabled by the user
- Must verify active window, version, resolution before actions
- Must take before/after screenshots
- Must stop immediately on UI mismatch

**Consequences**:
- Rendering and some visualization functions will report "requires GUI"
  when `DS_ENABLE_UI_FALLBACK=false`
- Users who need these features must either use Discovery Studio interactively
  or enable UI fallback with understanding of its limitations
