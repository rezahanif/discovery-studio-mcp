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
from mcp.types import ServerCapabilities, Tool

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
    PrepareStructureRequest,
    ViewInGuiRequest,
    ExtractSequenceRequest,
    MutateResidueRequest,
    AnalyzeInterfaceRequest,
    SuperimposeStructuresRequest,
    AlignSequencesRequest,
    CalculateRamachandranRequest,
    EvaluateMutantRequest,
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

BIOLOGICAL 4-STAGE PIPELINE:
1. ds_inspect_structure   → Stage 1: Fast structural triage (format, chains, residues, ligand, waters, atom counts)
2. ds_prepare_structure   → Stage 2: Clean protein, protonate at physiological pH (default 7.4), add hydrogens, strip waters
3. ds_analyze_binding_site → Stage 3: Detect active binding pockets, cavity volume (Angstroms^3), coordinates (X,Y,Z)
4. ds_view_in_gui         → Stage 4: Live visual dispatch to active Discovery Studio desktop window + frame view + capture PNG

EXECUTION CONTEXTS (HEADLESS vs. IN-GUI):
- HEADLESS BATCH: ds_inspect_structure, ds_validate_structure, ds_prepare_structure, ds_analyze_binding_site, ds_convert_structure
  Operate in background RAM using DiscoveryScript Perl. Do not touch or block the user's desktop application.
- IN-GUI INTERACTIVE: ds_view_in_gui, ds_get_active_workspace, ds_render_structure
  Dispatch directly to the running DiscoveryStudio2025.exe session via single-instance Windows IPC. Updates the 3D viewport live and saves preview snapshots.

ENTERPRISE PROTOCOL TOOLS:
- ds_run_protocol, ds_get_job_status, ds_cancel_job, ds_list_jobs, ds_describe_protocol
  Require an active Pipeline Pilot Server URL (DS_PIPELINE_PILOT_URL). If unconfigured, use the local 4-stage pipeline instead.

UNITS & CONVENTIONS:
- Distance & Coordinates: Angstroms (1 A = 0.1 nm = 10^-10 m)
- Pocket Volume: Cubic Angstroms (A^3)
- Physiological pH: 7.4 (controls Histidine HSE/HSD/HSP protonation states)
- Energy: kcal/mol
- Angles: Degrees
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
_TOOL_SPECS: list[dict[str, Any]] = [
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
        "description": "[Requires Pipeline Pilot Enterprise Server] List all available enterprise "
                       "protocols (e.g. dynamics, docking). For standalone local modeling without server, "
                       "use ds_prepare_structure, ds_mutate_residue, ds_analyze_binding_site, and ds_analyze_interface.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ds_describe_protocol",
        "description": "[Requires Pipeline Pilot Enterprise Server] Get detailed parameter metadata "
                       "and inputs for a server protocol.",
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
        "description": "[Requires Pipeline Pilot Enterprise Server] Launch a server protocol job. "
                       "WARNING: Fails if local workstation is not connected to a Pipeline Pilot cluster. "
                       "For local structural biology tasks, use ds_prepare_structure, ds_mutate_residue, "
                       "ds_analyze_binding_site, and ds_analyze_interface.",
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
        "description": "[Requires Pipeline Pilot Enterprise Server] Get the current status of a running or completed server job.",
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
    {
        "name": "ds_prepare_structure",
        "description": "Stage 2: Clean macromolecule and prepare for simulation or docking. "
                       "Standardizes atom nomenclature, fixes connectivity, adds missing hydrogens "
                       "at specified pH (default 7.4), and optionally strips crystallographic waters. "
                       "Operates headlessly and outputs the prepared structure file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to the raw molecular structure file (e.g. .pdb, .mol2)",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional destination path for prepared structure. Defaults to prepared_<filename>",
                },
                "ph": {
                    "type": "number",
                    "description": "Target physiological pH for amino acid protonation states (default: 7.4)",
                    "default": 7.4,
                },
                "keep_waters": {
                    "type": "boolean",
                    "description": "If False (default), removes all crystallographic water molecules (HOH). Set True if water bridges are required for ligand binding.",
                    "default": False,
                },
                "standardize_names": {
                    "type": "boolean",
                    "description": "Standardize IUPAC nomenclature for terminal groups and isoleucine (default: True)",
                    "default": True,
                },
            },
            "required": ["input_path"],
        },
    },
    {
        "name": "ds_analyze_binding_site",
        "description": "Stage 3: Detect active binding pockets and cavities in a receptor protein. "
                       "Calculates geometric cavity points, 3D center coordinates (X, Y, Z in Angstroms), "
                       "and cavity volume in Angstroms^3 (A^3) to verify if drug molecules can fit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the prepared receptor structure file",
                },
                "grid_resolution": {
                    "type": "number",
                    "description": "Grid sampling resolution in Angstroms (default: 0.5 A)",
                    "default": 0.5,
                },
                "site_opening": {
                    "type": "number",
                    "description": "Threshold distance for cavity entrance openings in Angstroms (default: 4.0 A)",
                    "default": 4.0,
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ds_view_in_gui",
        "description": "Stage 4 / Live Visualizer: Dispatch structure and visual representation "
                       "directly into the user's active Discovery Studio 2025 desktop window. "
                       "Applies 3D display styles (ribbon, ball & stick, CPK spheres), colors by "
                       "secondary structure or chain, centers camera (FitView), and captures an "
                       "image snapshot PNG for visual verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to structure file to display. If omitted, applies styles to whatever molecule is currently open in the active window.",
                },
                "display_style": {
                    "type": "string",
                    "description": "3D molecular rendering style",
                    "enum": ["ribbon_flat", "ribbon_tube", "ball_and_stick", "cpk", "schematic", "stick", "wire"],
                    "default": "ribbon_flat",
                },
                "color_scheme": {
                    "type": "string",
                    "description": "Coloring scheme for the protein structure",
                    "enum": ["secondary", "rainbow", "chain", "molecule", "charge", "hydrophobicity"],
                    "default": "secondary",
                },
                "rotate_x": {
                    "type": "number",
                    "description": "Angle in degrees to rotate view around X-axis (pitch)",
                    "default": 0.0,
                },
                "rotate_y": {
                    "type": "number",
                    "description": "Angle in degrees to rotate view around Y-axis (yaw)",
                    "default": 0.0,
                },
                "capture_snapshot": {
                    "type": "boolean",
                    "description": "Whether to capture a rendered PNG snapshot of the 3D viewport (default: True)",
                    "default": True,
                },
                "snapshot_path": {
                    "type": "string",
                    "description": "Optional destination path for the snapshot PNG",
                },
            },
            "required": [],
        },
    },
    {
        "name": "ds_get_active_workspace",
        "description": "Observability: Inspect the currently open Discovery Studio GUI session. "
                       "Returns process ID, active molecule document name, total atom count, "
                       "and count of currently selected objects in the 3D viewport.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ds_extract_sequence",
        "description": "Biological Sequence Primitive: Extract amino acid sequence (FASTA format "
                       "and detailed per-residue breakdown) from a protein structure file. "
                       "Allows specifying chain_id or extracting all chains.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to input protein structure file (PDB, MOL2, etc.)",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Optional chain identifier (e.g. 'A') to restrict extraction",
                },
                "compact": {
                    "type": "boolean",
                    "description": "If true (default), returns clean FASTA sequence and omits lengthy per-residue object arrays to save tokens",
                    "default": True,
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ds_mutate_residue",
        "description": "Computational Mutagenesis Primitive: Introduce an in-silico single amino-acid "
                       "point mutation into a protein structure. Performs native Discovery Studio side-chain "
                       "repacking and clean/hydrogen adjustment at pH 7.4, saving the mutant 3D model to disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to input structure file",
                },
                "residue_id": {
                    "type": "string",
                    "description": "Residue sequence number or identifier to mutate (e.g. '57' or '16')",
                },
                "target_amino_acid": {
                    "type": "string",
                    "description": "Target amino acid 3-letter code or 1-letter symbol (e.g. 'ALA', 'A', 'ARG', 'R')",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Optional chain identifier (e.g. 'A') where target residue resides",
                },
                "repack_and_clean": {
                    "type": "boolean",
                    "description": "Whether to perform protonation and side-chain repacking at pH 7.4 (default: True)",
                    "default": True,
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path for the output mutant structure file",
                },
            },
            "required": ["file_path", "residue_id", "target_amino_acid"],
        },
    },
    {
        "name": "ds_analyze_interface",
        "description": "Protein-Protein Interface Primitive: Analyze contact residues, hydrogen bonds, "
                       "and steric clashes between two interacting protein chains (e.g. Chain A and Chain B). "
                       "Calculates total interface contacts at specified distance threshold in Angstroms.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to protein complex structure file",
                },
                "chain_1": {
                    "type": "string",
                    "description": "First interacting chain identifier (default: 'A')",
                    "default": "A",
                },
                "chain_2": {
                    "type": "string",
                    "description": "Second interacting chain identifier (default: 'B')",
                    "default": "B",
                },
                "contact_cutoff_angstrom": {
                    "type": "number",
                    "description": "Distance threshold in Angstroms for defining interface contact (default: 4.5)",
                    "default": 4.5,
                },
                "compact": {
                    "type": "boolean",
                    "description": "If true (default), returns interface summary, contacts, clashes, and top 10 H-bonds, omitting massive raw arrays",
                    "default": True,
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ds_superimpose_structures",
        "description": "3D Coordinate Superposition & RMSD Primitive: Superimpose a target protein structure "
                       "onto a reference protein structure in 3D coordinate space. Computes Root Mean Square "
                       "Deviation (RMSD) for C-alpha atoms, mainchain backbone atoms, and all atoms in Angstroms. "
                       "Optionally saves the transformed/aligned target coordinates to a new PDB file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reference_path": {
                    "type": "string",
                    "description": "Path to reference structure file (e.g. wild-type PDB)",
                },
                "target_path": {
                    "type": "string",
                    "description": "Path to target structure file to superimpose (e.g. mutant or homolog PDB)",
                },
                "align_by": {
                    "type": "string",
                    "description": "Atom selection used for superposition alignment",
                    "enum": ["calpha", "mainchain", "all_atom"],
                    "default": "calpha",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional destination path to save the superimposed target structure file",
                },
            },
            "required": ["reference_path", "target_path"],
        },
    },
    {
        "name": "ds_align_sequences",
        "description": "Pairwise Sequence Alignment Primitive: Perform global (Needleman-Wunsch) protein "
                       "sequence alignment between two amino acid sequences or structures. Calculates percentage "
                       "sequence identity, percentage sequence similarity, alignment score, matches, mismatches, "
                       "gaps, and returns a formatted visual alignment with match markers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sequence_1": {
                    "type": "string",
                    "description": "First amino acid sequence (raw single-letter string or FASTA text)",
                },
                "sequence_2": {
                    "type": "string",
                    "description": "Second amino acid sequence (raw single-letter string or FASTA text)",
                },
                "name_1": {
                    "type": "string",
                    "description": "Label for sequence 1 (default: 'Seq1')",
                    "default": "Seq1",
                },
                "name_2": {
                    "type": "string",
                    "description": "Label for sequence 2 (default: 'Seq2')",
                    "default": "Seq2",
                },
                "algorithm": {
                    "type": "string",
                    "description": "Alignment algorithm",
                    "enum": ["needleman_wunsch", "smith_waterman"],
                    "default": "needleman_wunsch",
                },
            },
            "required": ["sequence_1", "sequence_2"],
        },
    },
    {
        "name": "ds_calculate_ramachandran",
        "description": "Stereochemical Validation Primitive: Calculate per-residue Phi (φ) and Psi (ψ) "
                       "backbone dihedral torsion angles from 3D protein coordinates. Classifies every residue "
                       "into standard Ramachandran regions (Favored, Allowed, Outlier), computing overall percentages "
                       "and identifying conformational strain outliers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to protein structure file (PDB format)",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Optional chain identifier (e.g. 'A') to restrict evaluation",
                },
                "generate_plot_image": {
                    "type": "boolean",
                    "description": "Whether to generate a 2D scatter plot image of the Ramachandran distribution",
                    "default": False,
                },
                "plot_output_path": {
                    "type": "string",
                    "description": "Optional file path for the plot image",
                },
                "compact": {
                    "type": "boolean",
                    "description": "If true (default), returns stereochemical statistics and outlier list, omitting massive raw 200+ angle tables",
                    "default": True,
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ds_evaluate_mutant",
        "description": "All-in-One Protein Mutagenesis & Evaluation Macro: General-purpose computational pipeline that introduces "
                       "a single amino-acid point mutation, verifies sequence identity via global pairwise alignment, superimposes "
                       "3D coordinates, and validates Ramachandran stereochemistry in a single optimized call. Returns a comprehensive "
                       "evaluation card with RMSD, stereochemical breakdown, and tolerance verdict with ultra-low token overhead (~500 tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to wild-type protein structure file (PDB format)",
                },
                "residue_id": {
                    "type": "string",
                    "description": "Residue sequence number to mutate (e.g. '16' or '57')",
                },
                "target_amino_acid": {
                    "type": "string",
                    "description": "Target amino acid 3-letter code or 1-letter symbol (e.g. 'ALA', 'VAL', 'PHE')",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Optional chain identifier (default: 'A')",
                    "default": "A",
                },
                "repack_and_clean": {
                    "type": "boolean",
                    "description": "Whether to perform protonation and side-chain repacking at pH 7.4 (default: True)",
                    "default": True,
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path for the output mutant structure file",
                },
            },
            "required": ["file_path", "residue_id", "target_amino_acid"],
        },
    },
    {
        "name": "ds_search_api",
        "description": "Search the Discovery Studio scripting API by keyword. "
                       "Returns matching functions with descriptions, usage examples, "
                       "and package context. Use this when you need to find the right "
                       "API method for a task but don't know the exact name. "
                       "Reference documentation only: not executable through this connector.",
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
                       "and package. Use this when you know the function name and need details. "
                       "Reference documentation only: not executable through this connector.",
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
                       "Use this to understand the API surface and browse by domain. "
                       "Reference documentation only: not executable through this connector.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [Tool(**spec) for spec in _TOOL_SPECS]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
    logger.info(f"Tool called: {name} with arguments: {json.dumps(arguments, default=str)[:200]}")

    try:
        if name == "ds_get_capabilities":
            caps = await adapter.get_capabilities()
            return caps.model_dump()

        elif name == "ds_health_check":
            result = await adapter.health_check()
            return result.model_dump()

        elif name == "ds_inspect_structure":
            file_path = arguments.get("file_path", "")
            if not file_path:
                return {"error": "file_path is required"}
            result = await adapter.inspect_structure(file_path)
            return result.model_dump()

        elif name == "ds_validate_structure":
            file_path = arguments.get("file_path", "")
            if not file_path:
                return {"error": "file_path is required"}
            workflow = arguments.get("workflow", "general")
            inspection = await adapter.inspect_structure(file_path)

            issues = []
            if workflow == "docking":
                if inspection.model_count > 1:
                    issues.append("Multiple models found - consider using first model only")
                if not inspection.chains:
                    issues.append("No protein chains found - needed for docking")

            return {
                "valid": len(issues) == 0,
                "workflow": workflow,
                "file_path": file_path,
                "issues": issues,
                "inspection": inspection.model_dump(),
            }

        elif name == "ds_convert_structure":
            request = ConvertStructureRequest(
                input_path=arguments["input_path"],
                output_format=arguments["output_format"],
                output_path=arguments.get("output_path"),
            )
            result_path = await adapter.convert_structure(request)
            return {"output_path": result_path, "format": request.output_format}

        elif name == "ds_list_protocols":
            protocols = await adapter.list_protocols()
            return {
                "protocols": [p.model_dump() for p in protocols],
                "total": len(protocols),
                "note": "Protocol execution requires Pipeline Pilot Server connection. "
                        "These are available protocol names - use ds_describe_protocol for details.",
            }

        elif name == "ds_describe_protocol":
            protocol_name = arguments.get("protocol_name", "")
            if not protocol_name:
                return {"error": "protocol_name is required"}
            description = await adapter.describe_protocol(protocol_name)
            return description.model_dump()

        elif name == "ds_run_protocol":
            request = RunProtocolRequest(
                protocol_name=arguments["protocol_name"],
                parameters=arguments.get("parameters", {}),
                input_files=arguments.get("input_files", []),
                confirm_destructive_action=arguments.get("confirm_destructive_action", False),
            )
            result = await adapter.run_protocol(request)
            return result.model_dump()

        elif name == "ds_get_job_status":
            job_id = arguments.get("job_id", "")
            if not job_id:
                return {"error": "job_id is required"}
            result = await adapter.get_job_status(job_id)
            return result.model_dump()

        elif name == "ds_cancel_job":
            job_id = arguments.get("job_id", "")
            if not job_id:
                return {"error": "job_id is required"}
            success = await adapter.cancel_job(job_id)
            return {"cancelled": success, "job_id": job_id}

        elif name == "ds_list_jobs":
            jobs = await adapter.list_jobs()
            return {"jobs": [j.model_dump() for j in jobs], "total": len(jobs)}

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
                return {"image_path": result_path, "format": request.output_format}
            else:
                return {
                    "error": "Rendering requires active Discovery Studio GUI session. "
                             "This adapter does not support headless rendering.",
                    "available": False,
                    "recommendation": "Use Discovery Studio client interactively for rendering.",
                }

        elif name == "ds_prepare_structure":
            prep_req = PrepareStructureRequest(
                input_path=arguments["input_path"],
                output_path=arguments.get("output_path"),
                ph=arguments.get("ph", 7.4),
                keep_waters=arguments.get("keep_waters", False),
                standardize_names=arguments.get("standardize_names", True),
            )
            prep_res = await adapter.prepare_structure(prep_req)
            return prep_res.model_dump()

        elif name == "ds_analyze_binding_site":
            grid_res = arguments.get("grid_resolution", 0.5)
            site_op = arguments.get("site_opening", 4.0)
            site_res = await adapter.analyze_binding_site(
                arguments["file_path"], grid_resolution=grid_res, site_opening=site_op
            )
            return site_res.model_dump()

        elif name == "ds_view_in_gui":
            view_req = ViewInGuiRequest(
                file_path=arguments.get("file_path"),
                display_style=arguments.get("display_style", "ribbon_flat"),
                color_scheme=arguments.get("color_scheme", "secondary"),
                rotate_x=arguments.get("rotate_x", 0.0),
                rotate_y=arguments.get("rotate_y", 0.0),
                capture_snapshot=arguments.get("capture_snapshot", True),
                snapshot_path=arguments.get("snapshot_path"),
            )
            view_res = await adapter.view_in_gui(view_req)
            return view_res.model_dump()

        elif name == "ds_get_active_workspace":
            ws_res = await adapter.get_active_workspace()
            return ws_res.model_dump()

        elif name == "ds_extract_sequence":
            seq_req = ExtractSequenceRequest(
                file_path=arguments["file_path"],
                chain_id=arguments.get("chain_id"),
                compact=arguments.get("compact", True),
            )
            seq_res = await adapter.extract_sequence(seq_req)
            return seq_res.model_dump()

        elif name == "ds_mutate_residue":
            mut_req = MutateResidueRequest(
                file_path=arguments["file_path"],
                chain_id=arguments.get("chain_id"),
                residue_id=str(arguments["residue_id"]),
                target_amino_acid=arguments["target_amino_acid"],
                repack_and_clean=arguments.get("repack_and_clean", True),
                output_path=arguments.get("output_path"),
            )
            mut_res = await adapter.mutate_residue(mut_req)
            return mut_res.model_dump()

        elif name == "ds_analyze_interface":
            iface_req = AnalyzeInterfaceRequest(
                file_path=arguments["file_path"],
                chain_1=arguments.get("chain_1", "A"),
                chain_2=arguments.get("chain_2", "B"),
                contact_cutoff_angstrom=arguments.get("contact_cutoff_angstrom", 4.5),
                compact=arguments.get("compact", True),
            )
            iface_res = await adapter.analyze_interface(iface_req)
            return iface_res.model_dump()

        elif name == "ds_superimpose_structures":
            super_req = SuperimposeStructuresRequest(
                reference_path=arguments["reference_path"],
                target_path=arguments["target_path"],
                align_by=arguments.get("align_by", "calpha"),
                output_path=arguments.get("output_path"),
            )
            super_res = await adapter.superimpose_structures(super_req)
            return super_res.model_dump()

        elif name == "ds_align_sequences":
            aln_req = AlignSequencesRequest(
                sequence_1=arguments["sequence_1"],
                sequence_2=arguments["sequence_2"],
                name_1=arguments.get("name_1", "Seq1"),
                name_2=arguments.get("name_2", "Seq2"),
                algorithm=arguments.get("algorithm", "needleman_wunsch"),
            )
            aln_res = await adapter.align_sequences(aln_req)
            return aln_res.model_dump()

        elif name == "ds_calculate_ramachandran":
            rama_req = CalculateRamachandranRequest(
                file_path=arguments["file_path"],
                chain_id=arguments.get("chain_id"),
                generate_plot_image=arguments.get("generate_plot_image", False),
                plot_output_path=arguments.get("plot_output_path"),
                compact=arguments.get("compact", True),
            )
            rama_res = await adapter.calculate_ramachandran(rama_req)
            return rama_res.model_dump()

        elif name == "ds_evaluate_mutant":
            eval_req = EvaluateMutantRequest(
                file_path=arguments["file_path"],
                residue_id=str(arguments["residue_id"]),
                target_amino_acid=arguments["target_amino_acid"],
                chain_id=arguments.get("chain_id", "A"),
                repack_and_clean=arguments.get("repack_and_clean", True),
                output_path=arguments.get("output_path"),
                compact=arguments.get("compact", True),
            )
            eval_res = await adapter.evaluate_mutant(eval_req)
            return eval_res.model_dump()

        # --- Layer B: API guidance tool handlers ---
        elif name == "ds_search_api":
            query = arguments.get("query", "").lower().strip()
            if not query:
                return {"error": "query is required"}
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
            return {
                "query": arguments["query"],
                "results": results,
                "total_matches": len(scored),
                "returned": len(results),
            }

        elif name == "ds_function_registry":
            func_name = arguments.get("function_name", "").strip()
            if not func_name:
                return {"error": "function_name is required"}
            # Exact match first, then partial
            exact = [e for e in _API_REGISTRY if e["name"].lower() == func_name.lower()]
            partial = [e for e in _API_REGISTRY if func_name.lower() in e["name"].lower() and e not in exact]
            matches = exact + partial[:5]
            if not matches:
                return {
                    "function_name": func_name,
                    "found": False,
                    "hint": f"No function matching '{func_name}' in registry. "
                            f"Try ds_search_api with broader keywords.",
                }
            return {
                "function_name": func_name,
                "found": True,
                "matches": matches,
            }

        elif name == "ds_list_api_categories":
            cats = []
            for pkg, info in sorted(_API_CATEGORIES.items()):
                cats.append({
                    "package": pkg,
                    "description": info.get("description", ""),
                    "function_count": info.get("count", len(info.get("tools", []))),
                })
            return {
                "categories": cats,
                "total_packages": len(cats),
                "total_registry_entries": len(_API_REGISTRY),
            }

        else:
            return {"error": f"Unknown tool: {name}"}

    except (SecurityViolationError, ValidationError) as e:
        logger.warning(f"Security violation: {e}")
        return {"error": str(e), "type": "security_violation",
                 "suggested_actions": [
                     "Check file path is within allowed directories",
                     "Verify file extension is supported (PDB, MOL, MOL2, SDF, XYZ)",
                     "Use validate_path() before accessing files",
                 ]}
    except ProtocolNotFoundError as e:
        logger.warning(f"Protocol not found: {e}")
        return {"error": str(e), "type": "protocol_not_found",
                 "suggested_actions": [
                     "Call ds_list_protocols to see available protocols",
                     "Check protocol name spelling (case-sensitive)",
                     "Ensure Pipeline Pilot Server is running if protocol requires it",
                 ]}
    except LicenseRequiredError as e:
        logger.warning(f"License required: {e}")
        return {"error": str(e), "type": "license_required",
                 "suggested_actions": [
                     "Check Discovery Studio license status via ds_get_capabilities",
                     "Some protocols require specific license tiers (Enterprise features)",
                     "Try running with mock mode to test workflow without license",
                 ]}
    except AdapterNotAvailableError as e:
        logger.warning(f"Adapter not available: {e}")
        return {"error": str(e), "type": "adapter_unavailable",
                 "suggested_actions": [
                     "Check DS_MOCK_MODE environment variable",
                     "Verify Discovery Studio installation path in DS_ROOT",
                     "Ensure Perl is available on PATH for DiscoveryScript adapter",
                 ]}
    except UnsupportedFormatError as e:
        logger.warning(f"Unsupported format: {e}")
        return {"error": str(e), "type": "unsupported_format",
                 "suggested_actions": [
                     "Supported formats: PDB, MOL, MOL2, SDF, XYZ, CIF, PDBQT",
                     "Convert to a supported format first using ds_convert_structure",
                 ]}
    except DiscoveryStudioError as e:
        logger.error(f"DS error: {e}")
        return {"error": str(e), "type": "discovery_studio_error",
                 "suggested_actions": [
                     "Check Discovery Studio logs for detailed error",
                     "Try ds_health_check to verify component status",
                     "Retry after ensuring DS is not in a busy state",
                 ]}
    except Exception as e:
        logger.exception(f"Unexpected error")
        return {"error": str(e), "type": "unexpected"}


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
