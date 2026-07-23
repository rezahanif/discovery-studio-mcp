"""Filesystem adapter for structure file operations."""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from discovery_studio_mcp.adapters.base import DiscoveryStudioAdapter
from discovery_studio_mcp.errors import AdapterNotAvailableError, UnsupportedFormatError
from discovery_studio_mcp.models import (
    AdapterInfo,
    AdapterStatus,
    ConvertStructureRequest,
    DsCapabilities,
    HealthCheckResult,
    JobResult,
    JobStatus,
    ProtocolDescription,
    ProtocolInfo,
    RenderStructureRequest,
    RunProtocolRequest,
    StructureInspection,
)
from discovery_studio_mcp.security import (
    is_safe_extension,
    sanitize_filename,
    validate_file_size,
    validate_path,
)


class FilesystemAdapter(DiscoveryStudioAdapter):
    """Adapter for filesystem-level operations on structure files.

    Can copy, validate extensions, inspect basic PDB/XYZ/SDF properties
    without requiring Discovery Studio or Perl.
    """

    adapter_name = "filesystem"

    def is_available(self) -> bool:
        return True

    async def get_capabilities(self) -> DsCapabilities:
        return DsCapabilities(
            mock=False,
            discovery_studio_version="detect_only",
            discovery_studio_build="detect_only",
            discovery_studio_root="detect_only",
            available_adapters=[
                AdapterInfo(
                    name="filesystem",
                    status=AdapterStatus.CONFIRMED,
                    description="Filesystem-level structure file operations",
                    version="0.1.0",
                    limitations=[
                        "Cannot run Discovery Studio protocols",
                        "Cannot compute molecular properties",
                        "Basic structure inspection only (PDB/XYZ counts)",
                    ],
                )
            ],
            supported_formats=["pdb", "mol", "mol2", "sdf", "sd", "xyz", "smi", "cif"],
            max_concurrent_jobs=10,
            job_timeout_seconds=60,
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            mock=False,
            status="ok",
            checks=[{"component": "filesystem_access", "status": "available"}],
        )

    async def inspect_structure(self, file_path: str) -> StructureInspection:
        validated = validate_path(file_path, must_exist=True)
        validate_file_size(validated)

        ext = validated.suffix.lower()
        if not is_safe_extension(file_path):
            raise UnsupportedFormatError(f"Unsupported format: {ext}")

        result = StructureInspection(
            mock=False,
            file_path=str(validated),
            format=ext.lstrip("."),
        )

        if ext in (".pdb", ".pdb1", ".ent"):
            result = self._inspect_pdb(validated, result)
        elif ext in (".xyz",):
            result = self._inspect_xyz(validated, result)

        return result

    def _inspect_pdb(self, path: Path, result: StructureInspection) -> StructureInspection:
        try:
            with open(path, errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return result

        models = 0
        chains_set: set[str] = set()
        residues_set: set[str] = set()
        waters = 0
        metals_set: set[str] = set()
        ligand_names: list[str] = []
        hetatoms_set: set[str] = set()
        atom_count = 0
        current_chain = "?"

        for line in lines:
            if line.startswith("MODEL"):
                models += 1
            elif line.startswith("ATOM") or line.startswith("HETATM"):
                atom_count += 1
                if len(line) >= 22:
                    current_chain = line[21:22].strip() or " "
                    chains_set.add(current_chain)
                if len(line) >= 27:
                    res_name = line[17:20].strip()
                    res_seq = line[22:27].strip()
                    res_id = f"{res_name}_{res_seq}_{current_chain}"
                    residues_set.add(res_id)
                    if res_name == "HOH":
                        waters += 1
                    elif res_name in ("ZN", "MG", "CA", "FE", "MN", "CU", "CO", "NI", "NA", "K", "CD", "HG"):
                        metals_set.add(res_name)
                    elif line.startswith("HETATM"):
                        hetatoms_set.add(res_name)
                        if res_name not in ("HOH",) and res_name not in metals_set:
                            ligand_names.append(res_name)

        if models == 0:
            models = 1

        result.atoms = atom_count
        result.model_count = models
        result.chains = sorted(chains_set)
        result.residues = len(residues_set)
        result.waters = waters
        result.metals = sorted(metals_set)
        result.heteroatoms = sorted(hetatoms_set)
        result.ligands = list(dict.fromkeys(ligand_names))[:50]  # unique, limited

        return result

    def _inspect_xyz(self, path: Path, result: StructureInspection) -> StructureInspection:
        try:
            with open(path, errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return result

        if len(lines) >= 1:
            try:
                result.atoms = int(lines[0].strip())
            except ValueError:
                pass
        return result

    async def list_protocols(self) -> list[ProtocolInfo]:
        return []

    async def describe_protocol(self, protocol_name: str) -> ProtocolDescription:
        raise AdapterNotAvailableError("Filesystem adapter does not support protocol execution")

    async def run_protocol(self, request: RunProtocolRequest) -> JobResult:
        raise AdapterNotAvailableError("Filesystem adapter does not support protocol execution")

    async def get_job_status(self, job_id: str) -> JobResult:
        raise AdapterNotAvailableError("Filesystem adapter does not support jobs")

    async def cancel_job(self, job_id: str) -> bool:
        return False

    async def list_jobs(self) -> list[JobResult]:
        return []

    async def convert_structure(self, request: ConvertStructureRequest) -> str:
        validated_input = validate_path(request.input_path, must_exist=True)
        output_path = request.output_path or str(validated_input.with_suffix(f".{request.output_format}"))
        shutil.copy2(validated_input, output_path)
        return output_path

    async def render_structure(self, request: RenderStructureRequest) -> str:
        raise AdapterNotAvailableError("Filesystem adapter does not support rendering")
