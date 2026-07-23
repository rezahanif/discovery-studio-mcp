# Discovery Studio MCP Server

MCP (Model Context Protocol) server for programmatic automation of BIOVIA Discovery Studio.
Enables AI agents to safely control Discovery Studio operations without constant computer use.

## Supported Versions

- Discovery Studio 2020 (20.1) - **tested**
- Other DS versions (2019, 2021+) - likely compatible with path adjustments

## Requirements

- Python 3.11+
- BIOVIA Discovery Studio 2020 (or compatible version)
- Optional: Pipeline Pilot Server (for protocol execution)
- Optional: DS Client license (for licensed protocols)

## Installation

```powershell
cd discovery-studio-mcp
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
# Required
DS_HOME=C:\Program Files\BIOVIA\Discovery Studio 2020
DS_PERL_EXECUTABLE=C:\Program Files\BIOVIA\Discovery Studio 2020\bin\perl.exe

# Optional (for protocol execution)
DS_PIPELINE_PILOT_URL=localhost:9943
DS_PIPELINE_PILOT_USERNAME=your_username
DS_PIPELINE_PILOT_PASSWORD=your_password

# Security
DS_ALLOWED_INPUT_DIRS=C:\Users\%USERNAME%\Documents
DS_OUTPUT_DIR=./workspace
DS_MAX_FILE_SIZE_MB=500
DS_JOB_TIMEOUT_SECONDS=3600

# Development
DS_MOCK_MODE=true   # Set to false for real Discovery Studio
```

### Finding Your Discovery Studio Installation

The server auto-detects Discovery Studio at `C:\Program Files\BIOVIA\Discovery Studio 2020`.
To find your installation:

1. Run: `tools/discover_environment.py`
2. Check the generated `reports/environment-report.md`
3. Update `.env` with the detected paths

### Pipeline Pilot Setup

Protocol execution requires a Pipeline Pilot Server. If you don't have one:

1. Set `DS_MOCK_MODE=true` for development
2. Structure inspection and file operations still work
3. Contact your BIOVIA administrator for Pipeline Pilot access

## Running the MCP Server (stdio)

```powershell
python -m discovery_studio_mcp.server
```

The server communicates via stdin/stdout using the MCP JSON-RPC protocol.

## MCP Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "discovery-studio": {
      "command": "python",
      "args": ["-m", "discovery_studio_mcp.server"],
      "cwd": "C:\\Users\\yourname\\discovery-studio-mcp",
      "env": {
        "DS_MOCK_MODE": "true",
        "PYTHONPATH": "src"
      }
    }
  }
}
```

### OpenCode / Codex

```json
{
  "mcpServers": {
    "discovery-studio": {
      "command": "python",
      "args": ["-m", "discovery_studio_mcp.server"],
      "cwd": "/path/to/discovery-studio-mcp",
      "env": {
        "DS_MOCK_MODE": "true",
        "PYTHONPATH": "src"
      }
    }
  }
}
```

## Available Tools

### Diagnostics

| Tool | Description |
|------|-------------|
| `ds_get_capabilities` | Get DS version, adapters, formats, license status |
| `ds_health_check` | Safety check of all components |

### Structures

| Tool | Description |
|------|-------------|
| `ds_inspect_structure` | Inspect file: chains, residues, atoms, ligands, waters, metals |
| `ds_validate_structure` | Check structure suitability for a workflow |
| `ds_convert_structure` | Convert between supported formats |

### Protocols

| Tool | Description |
|------|-------------|
| `ds_list_protocols` | List available protocols |
| `ds_describe_protocol` | Get protocol parameters, defaults, requirements |
| `ds_run_protocol` | Execute a protocol (requires Pipeline Pilot) |

### Jobs

| Tool | Description |
|------|-------------|
| `ds_get_job_status` | Poll job progress and results |
| `ds_cancel_job` | Cancel a running job |
| `ds_list_jobs` | List recent jobs |

### Visualization

| Tool | Description |
|------|-------------|
| `ds_render_structure` | Render structure to image (requires GUI) |

## Working Directory Structure

```
workspace/
  jobs/
    <job_id>/
      input/          # Input files (copied)
      output/         # Output files
      logs/           # Job logs
      manifest.json   # Full reproducibility record
```

## Mock Mode

Set `DS_MOCK_MODE=true` for development without Discovery Studio. All responses
are marked `"mock": true`. The mock adapter returns synthetic data for testing.

## Security

See [SECURITY.md](SECURITY.md) for the full security model.

Key points:
- No arbitrary code execution
- Path traversal protection
- Whitelist-based extension validation
- Output isolation in workspace directory
- Protocol whitelist
- Destructive action confirmation

## Limitations

1. **Protocol execution requires Pipeline Pilot Server** - not available locally
2. **Rendering requires GUI session** - no headless rendering API
3. **Discovery Script runs inside DS Client** - CLI mode is limited
4. **License-dependent features** - some protocols require specific licenses
5. **Windows path handling** - Unix-style paths may need conversion

## Troubleshooting

### "Perl executable not found"
Update `DS_PERL_EXECUTABLE` in `.env` to the correct perl.exe path.

### "Pipeline Pilot Server not configured"
Set `DS_PIPELINE_PILOT_URL` for protocol execution, or use mock mode.

### "Path not in allowed directories"
Add the directory to `DS_ALLOWED_INPUT_DIRS` (semicolon-separated on Windows).

### "Discovery Studio not found"
Set `DS_HOME` to your Discovery Studio installation root.

## Removing the Project

```powershell
pip uninstall discovery-studio-mcp
Remove-Item -Recurse discovery-studio-mcp
```

## Health Check

```powershell
# Verify environment
python tools/discover_environment.py

# Run tests
pytest tests/ -v

# Check MCP server startup
python -m discovery_studio_mcp.server
```

## License

MIT. See LICENSE file.

This project is not affiliated with, endorsed by, or sponsored by Dassault Systèmes or BIOVIA.
Discovery Studio is a registered trademark of Dassault Systèmes.

## Next Steps

For the full roadmap and current status, see:
- `reports/environment-report.md` - Environment details
- `reports/automation-capabilities.md` - Capability matrix and test status
- `docs/adr/architecture-decisions.md` - Architecture decisions
- `skills/discovery-studio/SKILL.md` - Agent usage guidelines
