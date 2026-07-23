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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("discovery-studio-mcp")

adapter: DiscoveryStudioAdapter = get_adapter()
server = Server("discovery-studio-mcp")


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
                        "description": "Target workflow (e.g., 'docking', 'minimization', 'simulation')",
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
                        "description": "Representation style (ball_and_stick, cartoon, stick, ribbon, surface)",
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
                        "description": "Output image format (png, jpg)",
                        "default": "png",
                    },
                },
                "required": ["molecule_path"],
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

        else:
            return [{"error": f"Unknown tool: {name}"}]

    except (SecurityViolationError, ValidationError) as e:
        logger.warning(f"Security violation: {e}")
        return [{"error": str(e), "type": "security_violation"}]
    except ProtocolNotFoundError as e:
        logger.warning(f"Protocol not found: {e}")
        return [{"error": str(e), "type": "protocol_not_found"}]
    except LicenseRequiredError as e:
        logger.warning(f"License required: {e}")
        return [{"error": str(e), "type": "license_required"}]
    except AdapterNotAvailableError as e:
        logger.warning(f"Adapter not available: {e}")
        return [{"error": str(e), "type": "adapter_unavailable"}]
    except UnsupportedFormatError as e:
        logger.warning(f"Unsupported format: {e}")
        return [{"error": str(e), "type": "unsupported_format"}]
    except DiscoveryStudioError as e:
        logger.error(f"DS error: {e}")
        return [{"error": str(e), "type": "discovery_studio_error"}]
    except Exception as e:
        logger.exception(f"Unexpected error")
        return [{"error": str(e), "type": "unexpected"}]


async def main():
    logger.info(f"Starting Discovery Studio MCP Server v{__version__}")
    logger.info(f"Adapter: {type(adapter).__name__}")
    logger.info(f"Mock mode: {settings.ds_mock_mode}")

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
