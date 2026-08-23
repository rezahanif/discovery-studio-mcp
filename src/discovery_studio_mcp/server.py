"""Discovery Studio MCP Server - Main entry point.

Provides AI agents with programmatic access to BIOVIA Discovery Studio
through the Model Context Protocol (MCP).

Uses adapter pattern to support multiple automation backends:
- DiscoveryScript (bundled Perl + DS API)
- Filesystem (basic structure inspection)
- Mock (for development/testing)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import ServerCapabilities

from discovery_studio_mcp import __version__
from discovery_studio_mcp.adapters import get_adapter
from discovery_studio_mcp.adapters.base import DiscoveryStudioAdapter
from discovery_studio_mcp.config import settings
from discovery_studio_mcp.errors import (
    AdapterNotAvailableError,
    DiscoveryStudioError,
    LicenseRequiredError,
    ProtocolNotFoundError,
    SecurityViolationError,
    UnsupportedFormatError,
    ValidationError,
)
from discovery_studio_mcp.models import (
    ConvertStructureRequest,
    RenderStructureRequest,
    RunProtocolRequest,
)
from discovery_studio_mcp.security import is_safe_extension, validate_path
from discovery_studio_mcp.prompts import register_prompts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("discovery-studio-mcp")

adapter: DiscoveryStudioAdapter = get_adapter()
server = Server("discovery-studio-mcp")
register_prompts(server)

# --- SERVER_INSTRUCTIONS: runtime-rewritable agent guidance ---
SERVER_INSTRUCTIONS = """Discovery Studio MCP Server — Agent Workflow Guide

WORKFLOW ORDER:
1. ds_get_capabilities → understand adapter status, license, supported formats
2. ds_inspect_structure → analyze input file before any operation
3. ds_validate_structure → check fitness for target workflow
4. ds_search_api → find the right API method if dedicated tool doesn't exist
5. ds_run_protocol → execute with validated parameters

TOOL MATCHING:
- Structure operations → ds_inspect_structure, ds_validate_structure, ds_convert_structure
- Protocol discovery → ds_list_protocols → ds_describe_protocol → ds_run_protocol
- Job monitoring → ds_list_jobs → ds_get_job_status → ds_cancel_job
- API exploration → ds_search_api (keyword) → ds_function_registry (exact name)
- Rendering → ds_render_structure (requires active GUI session)

SANDBOX CONSTRAINTS:
- File access limited to configured directories (DS_FILE_WHITELIST)
- Supported formats: PDB, MOL, MOL2, SDF, XYZ, CIF, PDBQT
- Pipeline Pilot Server required for protocol execution
- Mock mode available for testing (DS_MOCK_MODE=true)

FAILURE RECOVERY:
- Protocol not found → ds_list_protocols to see available options
- Adapter unavailable → check DS_ROOT, DS_MOCK_MODE, Perl availability
- License required → check ds_get_capabilities for license status
- Format unsupported → convert first with ds_convert_structure

UNITS WARNING:
- Coordinates in Angstroms (default) or user-specified units
- Energy in kcal/mol (default for most protocols)
- Distance in Angstroms, angles in degrees
"""

# --- Layer B: API registry loaded once at startup ---
_REGISTRY_PATH = Path(__file__).parent / "api_registry.json"
_API_CATEGORIES_PATH = Path(__file__).parent / "api_categories.json"

def _load_registry() -> list[dict]:
    try:
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

def _load_categories() -> dict:
    try:
        return json.loads(_API_CATEGORIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

_API_REGISTRY: list[dict] = _load_registry()
_API_CATEGORIES: dict = _load_categories()

# Pre-build search index: lowercased name + description tokens per entry
_SEARCH_INDEX: list[dict] = []
for _entry in _API_REGISTRY:
    _tokens = set(_entry["name"].lower().split())
    _tokens.update(_entry.get("description", "").lower().split())
    _tokens.update(_entry.get("package", "").lower().split())
    _indexed = {k: v for k, v in _entry.items()}
    _indexed["_tokens"] = _tokens
    _SEARCH_INDEX.append(_indexed)


@server.list_tools()
async def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "ds_get_capabilities",
            "description": "Get Discovery Studio capabilities: version, available adapters, "
                           "supported formats, license status, Pipeline Pilot availability. "
                           "Call this first to understand what operations are possible.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "ds_health_check",
            "description": "Perform a safety check of all components. "
                           "Verifies Discovery Studio installation, Perl, Pipeline Pilot connection, "
                           "and other dependencies without running heavy computations.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "ds_inspect_structure",
            "description": "Inspect a molecular structure file and return its properties: "
                           "format, model count, chains, residues, atoms, ligands, waters, metals, "
                           "heteroatoms, and warnings.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the structure file (PDB, MOL, MOL2, SDF, XYZ, etc.)",
                    },
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "ds_validate_structure",
            "description": "Validate a structure file for suitability in downstream workflows.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the structure file",
                    },
                    "workflow": {
                        "type": "string",
                        "description": "Target workflow",
                        "enum": ["docking", "minimization", "simulation", "homology_modeling", "pharmacophore", "qsar", "protein_preparation", "general"],
                    },
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "ds_convert_structure",
            "description": "Convert a structure file between supported formats.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to input structure file",
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Target format (pdb, mol, mol2, sdf, etc.)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path for output file (optional, auto-generated if not specified)",
                    },
                },
                "required": ["input_path", "output_format"],
            },
        },
        {
            "name": "ds_list_protocols",
            "description": "List all available Discovery Studio protocols.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "ds_describe_protocol",
            "description": "Get detailed information about a protocol: parameters, defaults, "
                           "required inputs, license requirements, and constraints.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "protocol_name": {
                        "type": "string",
                        "description": "Name of the protocol to describe",
                    },
                },
                "required": ["protocol_name"],
            },
        },
        {
            "name": "ds_run_protocol",
            "description": "Run a Discovery Studio protocol with validated parameters. "
                           "Requires Pipeline Pilot Server connection.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "protocol_name": {
                        "type": "string",
                        "description": "Name of the protocol to run",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Protocol parameters as key-value pairs",
                    },
                    "input_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Input file paths",
                    },
                    "confirm_destructive_action": {
                        "type": "boolean",
                        "description": "Explicit confirmation for potentially destructive operations",
                        "default": False,
                    },
                },
                "required": ["protocol_name"],
            },
        },
        {
            "name": "ds_get_job_status",
            "description": "Get the current status of a running or completed job.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Job identifier",
                    },
                },
                "required": ["job_id"],
            },
        },
        {
            "name": "ds_cancel_job",
            "description": "Cancel a running job.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Job identifier to cancel",
                    },
                },
                "required": ["job_id"],
            },
        },
        {
            "name": "ds_list_jobs",
            "description": "List all jobs known to the server (recent and active).",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "ds_render_structure",
            "description": "Render a molecular structure to an image. "
                           "Requires active Discovery Studio GUI session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "molecule_path": {
                        "type": "string",
                        "description": "Path to structure file",
                    },
                    "representation": {
                        "type": "string",
                        "description": "Representation style",
                        "enum": ["ball_and_stick", "cartoon", "stick", "ribbon", "surface", "wireframe", "sphere"],
                    },
                    "width": {
                        "type": "integer",
                        "description": "Image width in pixels",
                        "default": 800,
                    },
                    "height": {
                        "type": "integer",
                        "description": "Image height in pixels",
                        "default": 600,
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Output image format",
                        "enum": ["png", "jpg", "tiff", "bmp"],
                    },
                },
                "required": ["molecule_path"],
            },
        },
        # --- Layer B: API guidance tools ---
        {
            "name": "ds_search_api",
            "description": "Search the Discovery Studio scripting API by keyword. "
                           "Returns matching functions with descriptions, usage examples, "
                           "and package context. Use this when you need to find the right "
                           "API method for a task but don't know the exact name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — keywords to match against function names, "
                                       "descriptions, and packages (e.g. 'create group', 'atom distance', 'pharmacophore')",
                    },
                    "package_filter": {
                        "type": "string",
                        "description": "Optional: restrict results to a specific package "
                                       "(e.g. 'MdmCommands', 'SbdCommands')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "ds_function_registry",
            "description": "Look up a specific Discovery Studio API function by name. "
                           "Returns full documentation: description, parameters, usage example, "
                           "and package. Use this when you know the function name and need details.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "function_name": {
                        "type": "string",
                        "description": "Function name to look up (e.g. 'CreateGroup', 'CalculateDistance')",
                    },
                },
                "required": ["function_name"],
            },
        },
        {
            "name": "ds_list_api_categories",
            "description": "List all Discovery Studio API categories (packages) and their function counts. "
                           "Use this to understand the API surface and browse by domain.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
    logger.info(f"Tool called: {name} with arguments: {json.dumps(arguments, default=str)[:200]}")

    try:
        if name == "ds_get_capabilities":
            caps = await adapter.get_capabilities()
            return [caps.model_dump()]

        elif name == "ds_health_check":
            result = await adapter.health_check()
            return [result.model_dump()]

        elif name == "ds_inspect_structure":
            file_path = arguments.get("file_path", "")
            if not file_path:
                return [{"error": "file_path is required"}]
            result = await adapter.inspect_structure(file_path)
            return [result.model_dump()]

        elif name == "ds_validate_structure":
            file_path = arguments.get("file_path", "")
            if not file_path:
                return [{"error": "file_path is required"}]
            workflow = arguments.get("workflow", "general")
            inspection = await adapter.inspect_structure(file_path)

            issues = []
            if workflow == "docking":
                if inspection.model_count > 1:
                    issues.append("Multiple models found - consider using first model only")
                if not inspection.chains:
                    issues.append("No protein chains found - needed for docking")

            return [{
                "valid": len(issues) == 0,
                "workflow": workflow,
                "file_path": file_path,
                "issues": issues,
                "inspection": inspection.model_dump(),
            }]

        elif name == "ds_convert_structure":
            request = ConvertStructureRequest(
                input_path=arguments["input_path"],
                output_format=arguments["output_format"],
                output_path=arguments.get("output_path"),
            )
            result_path = await adapter.convert_structure(request)
            return [{"output_path": result_path, "format": request.output_format}]

        elif name == "ds_list_protocols":
            protocols = await adapter.list_protocols()
            return [{
                "protocols": [p.model_dump() for p in protocols],
                "total": len(protocols),
                "note": "Protocol execution requires Pipeline Pilot Server connection. "
                        "These are available protocol names - use ds_describe_protocol for details.",
            }]

        elif name == "ds_describe_protocol":
            protocol_name = arguments.get("protocol_name", "")
            if not protocol_name:
                return [{"error": "protocol_name is required"}]
            description = await adapter.describe_protocol(protocol_name)
            return [description.model_dump()]

        elif name == "ds_run_protocol":
            request = RunProtocolRequest(
                protocol_name=arguments["protocol_name"],
                parameters=arguments.get("parameters", {}),
                input_files=arguments.get("input_files", []),
                confirm_destructive_action=arguments.get("confirm_destructive_action", False),
            )
            result = await adapter.run_protocol(request)
            return [result.model_dump()]

        elif name == "ds_get_job_status":
            job_id = arguments.get("job_id", "")
            if not job_id:
                return [{"error": "job_id is required"}]
            result = await adapter.get_job_status(job_id)
            return [result.model_dump()]

        elif name == "ds_cancel_job":
            job_id = arguments.get("job_id", "")
            if not job_id:
                return [{"error": "job_id is required"}]
            success = await adapter.cancel_job(job_id)
            return [{"cancelled": success, "job_id": job_id}]

        elif name == "ds_list_jobs":
            jobs = await adapter.list_jobs()
            return [{"jobs": [j.model_dump() for j in jobs], "total": len(jobs)}]

        elif name == "ds_render_structure":
            request = RenderStructureRequest(
                molecule_path=arguments["molecule_path"],
                representation=arguments.get("representation", "ball_and_stick"),
                width=arguments.get("width", 800),
                height=arguments.get("height", 600),
                output_format=arguments.get("output_format", "png"),
            )
            result_path = await adapter.render_structure(request)
            if result_path:
                return [{"image_path": result_path, "format": request.output_format}]
            else:
                return [{
                    "error": "Rendering requires active Discovery Studio GUI session. "
                             "This adapter does not support headless rendering.",
                    "available": False,
                    "recommendation": "Use Discovery Studio client interactively for rendering.",
                }]

        # --- Layer B: API guidance tool handlers ---
        elif name == "ds_search_api":
            query = arguments.get("query", "").lower().strip()
            if not query:
                return [{"error": "query is required"}]
            query_tokens = set(query.split())
            pkg_filter = arguments.get("package_filter")
            limit = arguments.get("limit", 10)

            scored = []
            for entry in _SEARCH_INDEX:
                if pkg_filter and entry.get("package") != pkg_filter:
                    continue
                overlap = len(query_tokens & entry["_tokens"])
                if overlap > 0:
                    scored.append((overlap, entry))
            scored.sort(key=lambda x: -x[0])

            results = []
            for _, entry in scored[:limit]:
                results.append({
                    "name": entry["name"],
                    "package": entry.get("package", ""),
                    "function_path": entry.get("function_path", ""),
                    "description": entry.get("description", ""),
                    "usage_example": entry.get("usage_example", ""),
                    "doc_file": entry.get("doc_file", ""),
                })
            return [{
                "query": arguments["query"],
                "results": results,
                "total_matches": len(scored),
                "returned": len(results),
            }]

        elif name == "ds_function_registry":
            func_name = arguments.get("function_name", "").strip()
            if not func_name:
                return [{"error": "function_name is required"}]
            # Exact match first, then partial
            exact = [e for e in _API_REGISTRY if e["name"].lower() == func_name.lower()]
            partial = [e for e in _API_REGISTRY if func_name.lower() in e["name"].lower() and e not in exact]
            matches = exact + partial[:5]
            if not matches:
                return [{
                    "function_name": func_name,
                    "found": False,
                    "hint": f"No function matching '{func_name}' in registry. "
                            f"Try ds_search_api with broader keywords.",
                }]
            return [{
                "function_name": func_name,
                "found": True,
                "matches": matches,
            }]

        elif name == "ds_list_api_categories":
            cats = []
            for pkg, info in sorted(_API_CATEGORIES.items()):
                cats.append({
                    "package": pkg,
                    "description": info.get("description", ""),
                    "function_count": info.get("count", len(info.get("tools", []))),
                })
            return [{
                "categories": cats,
                "total_packages": len(cats),
                "total_registry_entries": len(_API_REGISTRY),
            }]

        else:
            return [{"error": f"Unknown tool: {name}"}]

    except (SecurityViolationError, ValidationError) as e:
        logger.warning(f"Security violation: {e}")
        return [{"error": str(e), "type": "security_violation",
                 "suggested_actions": [
                     "Check file path is within allowed directories",
                     "Verify file extension is supported (PDB, MOL, MOL2, SDF, XYZ)",
                     "Use validate_path() before accessing files",
                 ]}]
    except ProtocolNotFoundError as e:
        logger.warning(f"Protocol not found: {e}")
        return [{"error": str(e), "type": "protocol_not_found",
                 "suggested_actions": [
                     "Call ds_list_protocols to see available protocols",
                     "Check protocol name spelling (case-sensitive)",
                     "Ensure Pipeline Pilot Server is running if protocol requires it",
                 ]}]
    except LicenseRequiredError as e:
        logger.warning(f"License required: {e}")
        return [{"error": str(e), "type": "license_required",
                 "suggested_actions": [
                     "Check Discovery Studio license status via ds_get_capabilities",
                     "Some protocols require specific license tiers (Enterprise features)",
                     "Try running with mock mode to test workflow without license",
                 ]}]
    except AdapterNotAvailableError as e:
        logger.warning(f"Adapter not available: {e}")
        return [{"error": str(e), "type": "adapter_unavailable",
                 "suggested_actions": [
                     "Check DS_MOCK_MODE environment variable",
                     "Verify Discovery Studio installation path in DS_ROOT",
                     "Ensure Perl is available on PATH for DiscoveryScript adapter",
                 ]}]
    except UnsupportedFormatError as e:
        logger.warning(f"Unsupported format: {e}")
        return [{"error": str(e), "type": "unsupported_format",
                 "suggested_actions": [
                     "Supported formats: PDB, MOL, MOL2, SDF, XYZ, CIF, PDBQT",
                     "Convert to a supported format first using ds_convert_structure",
                 ]}]
    except DiscoveryStudioError as e:
        logger.error(f"DS error: {e}")
        return [{"error": str(e), "type": "discovery_studio_error",
                 "suggested_actions": [
                     "Check Discovery Studio logs for detailed error",
                     "Try ds_health_check to verify component status",
                     "Retry after ensuring DS is not in a busy state",
                 ]}]
    except Exception as e:
        logger.exception(f"Unexpected error")
        return [{"error": str(e), "type": "unexpected"}]


async def main():
    logger.info(f"Starting Discovery Studio MCP Server v{__version__}")
    logger.info(f"Adapter: {type(adapter).__name__}")
    logger.info(f"Mock mode: {settings.ds_mock_mode}")
    logger.info(f"API registry: {len(_API_REGISTRY)} entries loaded")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="discovery-studio-mcp",
                server_version=__version__,
                capabilities=ServerCapabilities(),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
