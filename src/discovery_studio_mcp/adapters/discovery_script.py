"""DiscoveryScript adapter using the bundled Perl interpreter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discovery_studio_mcp.adapters.base import DiscoveryStudioAdapter
from discovery_studio_mcp.config import settings
from discovery_studio_mcp.errors import (
    AdapterNotAvailableError,
    DiscoveryStudioError,
    ProtocolExecutionError,
    ProtocolNotFoundError,
)
from discovery_studio_mcp.models import (
    AdapterInfo,
    AdapterStatus,
    CapabilityStatus,
    ConvertStructureRequest,
    DsCapabilities,
    HealthCheckResult,
    JobResult,
    JobStatus,
    ProtocolDescription,
    ProtocolInfo,
    ProtocolParameter,
    RenderStructureRequest,
    RunProtocolRequest,
    StructureInspection,
    PrepareStructureRequest,
    PrepareStructureResult,
    BindingSiteInfo,
    BindingSiteAnalysisResult,
    ViewInGuiRequest,
    ViewInGuiResult,
    ActiveWorkspaceResult,
    ExtractSequenceRequest,
    ExtractSequenceResult,
    ChainSequence,
    ResidueInfo,
    MutateResidueRequest,
    MutateResidueResult,
    AnalyzeInterfaceRequest,
    AnalyzeInterfaceResult,
    InterfaceHBond,
    InterfaceClash,
    SuperimposeStructuresRequest,
    SuperimposeStructuresResult,
    AlignSequencesRequest,
    AlignSequencesResult,
    CalculateRamachandranRequest,
    CalculateRamachandranResult,
    RamachandranResidue,
    EvaluateMutantRequest,
    EvaluateMutantResult,
)
import math
from discovery_studio_mcp.security import is_safe_extension, validate_path


async def _delayed_unlink(path: str, delay: float = 30.0) -> None:
    """Delay file deletion so asynchronous external GUI processes have time to read it."""
    try:
        await asyncio.sleep(delay)
        if os.path.isfile(path):
            os.unlink(path)
    except Exception:
        pass


class DiscoveryScriptAdapter(DiscoveryStudioAdapter):
    """Adapter that uses the bundled Perl interpreter and DiscoveryScript API.

    This adapter can run Perl scripts that use the DiscoveryScript modules
    (MdmDiscoveryScript, ForceFieldDiscoveryScript, ProtocolDiscoveryScript, etc.)
    to interact with molecular data and Discovery Studio protocols.

    Modes of operation:
    1. CLI mode: Run Perl scripts from command line (limited - no GUI features)
    2. Client mode: Launch Discovery Studio executable with a script parameter
    3. Protocol mode: Connect to Pipeline Pilot Server for protocol execution
    """

    adapter_name = "discovery_script"

    def __init__(self):
        self._ds_root = Path(settings.ds_home)
        self._perl_exe = Path(settings.ds_perl_executable)
        self._ds_exe = Path(settings.ds_executable)
        # Detect perl version from lib directory
        lib_dir = self._ds_root / "lib"
        perl_ver = "5.26.1"
        if lib_dir.is_dir():
            vers = [p.name for p in lib_dir.iterdir() if p.is_dir() and p.name.replace(".", "").isdigit()]
            if vers:
                perl_ver = sorted(vers, reverse=True)[0]
        self._perl_ver = perl_ver
        self._perl_lib = [
            str(self._ds_root / "bin"),
            str(self._ds_root / "lib" / perl_ver),
            str(self._ds_root / "lib" / "vendor_perl" / perl_ver),
            str(self._ds_root / "lib" / "site_perl" / perl_ver),
        ]
        self._jobs: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        return self._perl_exe.is_file() and self._ds_root.is_dir()

    async def get_capabilities(self) -> DsCapabilities:
        ds_ver = "2020"
        for part in self._ds_root.name.split():
            if part.isdigit():
                ds_ver = part
                break
        capabilities = DsCapabilities(
            mock=False,
            discovery_studio_version=ds_ver,
            discovery_studio_build="2025 Release",
            discovery_studio_root=str(self._ds_root),
            perl_version=self._perl_ver,
            available_adapters=[
                AdapterInfo(
                    name="discovery_script",
                    status=AdapterStatus.CONFIRMED,
                    description="DiscoveryScript API via bundled Perl 5.26.1",
                    version="2.10",
                    limitations=[
                        "Protocol execution requires Pipeline Pilot Server",
                        "Image rendering requires active GUI session",
                        "Some operations require Discovery Studio Client",
                    ],
                ),
                AdapterInfo(
                    name="filesystem",
                    status=AdapterStatus.CONFIRMED,
                    description="Filesystem operations for structure file handling",
                    version="0.1.0",
                ),
                AdapterInfo(
                    name="pipeline_pilot",
                    status=AdapterStatus.REQUIRES_LICENSE if not settings.has_pipeline_pilot
                    else AdapterStatus.PARTIALLY_CONFIRMED,
                    description="Pipeline Pilot protocol execution",
                    limitations=["Requires Pipeline Pilot Server license and connection"],
                ),
            ],
            pipeline_pilot_available=settings.has_pipeline_pilot,
            pipeline_pilot_server=settings.ds_pipeline_pilot_url or None,
            discovery_script_available=True,
            supported_formats=["pdb", "mol", "mol2", "sdf", "sd", "msv", "dsv",
                               "cif", "xyz", "smi", "car", "msi", "cpd", "chm", "ds_chm",
                               "csv", "helm", "map", "grd", "msf", "skc", "pov", "wrl"],
            license_mode="client",
            max_concurrent_jobs=settings.ds_max_concurrent_jobs,
            job_timeout_seconds=settings.ds_job_timeout_seconds,
            ui_fallback_enabled=settings.ds_enable_ui_fallback,
        )
        return capabilities

    async def health_check(self) -> HealthCheckResult:
        checks: list[dict[str, str]] = []
        issues: list[str] = []
        recommendations: list[str] = []

        checks.append({"component": "perl_executable", "status": "available" if self._perl_exe.is_file() else "missing"})
        if not self._perl_exe.is_file():
            issues.append(f"Perl executable not found at {self._perl_exe}")

        checks.append({"component": "ds_root", "status": "available" if self._ds_root.is_dir() else "missing"})
        if not self._ds_root.is_dir():
            issues.append(f"Discovery Studio root not found at {self._ds_root}")

        # Check DiscoveryScript module availability
        dsscript_pm = self._ds_root / "lib" / "vendor_perl" / self._perl_ver / "DiscoveryScript.pm"
        checks.append({"component": "discovery_script_module", "status": "available" if dsscript_pm.is_file() else "missing"})
        if not dsscript_pm.is_file():
            issues.append("DiscoveryScript Perl module not found")

        # Check client executable
        checks.append({"component": "ds_client", "status": "available" if self._ds_exe.is_file() else "missing"})
        if not self._ds_exe.is_file():
            issues.append(f"Discovery Studio client not found at {self._ds_exe}")

        # Check Pipeline Pilot
        pp_status = "available" if settings.has_pipeline_pilot else "unconfigured"
        checks.append({"component": "pipeline_pilot", "status": pp_status})
        if not settings.has_pipeline_pilot:
            recommendations.append("Set DS_PIPELINE_PILOT_URL to enable protocol execution")

        status = "ok" if not issues else "degraded"

        return HealthCheckResult(
            mock=False,
            status=status,
            checks=checks,
            issues=issues,
            recommendations=recommendations,
        )

    async def inspect_structure(self, file_path: str) -> StructureInspection:
        validated = validate_path(file_path, must_exist=True)
        if not is_safe_extension(file_path):
            raise ValueError(f"Unsupported file extension: {file_path}")

        script = self._build_inspect_script(str(validated))
        result = await self._run_perl_script(script, f"inspect_{uuid.uuid4().hex[:8]}")

        if result.get("error"):
            return StructureInspection(
                mock=False,
                file_path=file_path,
                format=validated.suffix.lower().lstrip("."),
                warnings=[result["error"]],
            )

        return StructureInspection(
            mock=False,
            file_path=file_path,
            format=result.get("format", validated.suffix.lower().lstrip(".")),
            model_count=result.get("model_count", 0),
            chains=result.get("chains", []),
            residues=result.get("residues", 0),
            atoms=result.get("atoms", 0),
            ligands=result.get("ligands", []),
            waters=result.get("waters", 0),
            metals=result.get("metals", []),
            heteroatoms=result.get("heteroatoms", []),
            warnings=result.get("warnings", []),
        )

    async def list_protocols(self) -> list[ProtocolInfo]:
        return [
            ProtocolInfo(
                name="Prepare Protein",
                description="Prepare protein structure for docking (clean, protonate, type)",
                category="Protein Preparation",
                required_parameters=["Input Protein", "pH"],
                requires_server=True,
            ),
            ProtocolInfo(
                name="Minimize",
                description="Energy minimization of typed molecules",
                category="Energy",
                required_parameters=["Input Typed Molecule"],
                requires_server=True,
            ),
            ProtocolInfo(
                name="Calculate Energy",
                description="Calculate single-point energy using a force field",
                category="Energy",
                required_parameters=["Input Typed Molecule"],
                requires_server=True,
            ),
            ProtocolInfo(
                name="Dock Ligands (CDOCKER)",
                description="Dock flexible ligands into a binding site using CDOCKER",
                category="Docking",
                required_parameters=["Input Receptor", "Input Ligands", "Input Site Sphere"],
                requires_server=True,
                requires_license=True,
            ),
            ProtocolInfo(
                name="Dock Ligands (LigandFit)",
                description="Dock ligands with shape-based initial placement",
                category="Docking",
                required_parameters=["Input Receptor", "Input Ligands"],
                requires_server=True,
                requires_license=True,
            ),
            ProtocolInfo(
                name="Define and Edit Binding Site",
                description="Define a binding site from a receptor and reference ligand",
                category="Structure-Based Design",
                required_parameters=["Input Receptor", "Input Reference Ligand"],
                requires_server=True,
            ),
        ]

    async def describe_protocol(self, protocol_name: str) -> ProtocolDescription:
        protocols: dict[str, ProtocolDescription] = {
            "Prepare Protein": ProtocolDescription(
                name="Prepare Protein",
                description="Prepare protein structure for downstream analysis. "
                            "Steps include cleaning, adding hydrogens, setting protonation states, "
                            "and forcefield typing.",
                category="Protein Preparation",
                parameters=[
                    ProtocolParameter(name="Input Protein", type="Molecule", required=True,
                                      description="Protein 3D structure"),
                    ProtocolParameter(name="pH", type="Real", required=False, default_value="7.4",
                                      description="Target pH for protonation"),
                    ProtocolParameter(name="Insert Missing Atoms", type="Boolean", required=False,
                                      default_value="True"),
                    ProtocolParameter(name="Delete Water", type="Boolean", required=False,
                                      default_value="False"),
                ],
                requires_server=True,
            ),
            "Dock Ligands (CDOCKER)": ProtocolDescription(
                name="Dock Ligands (CDOCKER)",
                description="Dock ligands into a protein binding site using the CDOCKER algorithm. "
                            "CDOCKER uses a CHARMm-based molecular dynamics simulated annealing approach.",
                category="Docking",
                parameters=[
                    ProtocolParameter(name="Input Receptor", type="Molecule", required=True,
                                      description="Prepared receptor protein"),
                    ProtocolParameter(name="Input Ligands", type="Molecule", required=True,
                                      description="Ligands to dock"),
                    ProtocolParameter(name="Input Site Sphere", type="Sphere", required=True,
                                      description="Binding site sphere (x, y, z, radius)"),
                    ProtocolParameter(name="Top Hits", type="Integer", required=False, default_value="10"),
                    ProtocolParameter(name="Random Conformations", type="Integer", required=False, default_value="10"),
                    ProtocolParameter(name="Pose Cluster Radius", type="Real", required=False, default_value="0.5"),
                ],
                requires_server=True,
                requires_license=True,
            ),
            "Dock Ligands (LigandFit)": ProtocolDescription(
                name="Dock Ligands (LigandFit)",
                description="Dock ligands using shape-based initial placement followed by energy optimization. "
                            "LigandFit uses a Monte Carlo conformational search.",
                category="Docking",
                parameters=[
                    ProtocolParameter(name="Input Receptor", type="Molecule", required=True),
                    ProtocolParameter(name="Input Ligands", type="Molecule", required=True),
                    ProtocolParameter(name="Number of Monte Carlo Trials", type="Integer", required=False,
                                      default_value="10"),
                ],
                requires_server=True,
                requires_license=True,
            ),
            "Minimize": ProtocolDescription(
                name="Minimize",
                description="Perform energy minimization on a typed molecule using a force field.",
                category="Energy",
                parameters=[
                    ProtocolParameter(name="Input Typed Molecule", type="Molecule", required=True),
                    ProtocolParameter(name="Minimization Steps", type="Integer", required=False, default_value="200"),
                ],
                requires_server=True,
            ),
            "Calculate Energy": ProtocolDescription(
                name="Calculate Energy",
                description="Calculate single-point energy of a typed molecule.",
                category="Energy",
                parameters=[
                    ProtocolParameter(name="Input Typed Molecule", type="Molecule", required=True),
                ],
                requires_server=True,
            ),
        }

        if protocol_name in protocols:
            return protocols[protocol_name]
        raise ProtocolNotFoundError(f"Protocol not found: {protocol_name}")

    async def run_protocol(self, request: RunProtocolRequest) -> JobResult:
        job_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        output_dir = settings.output_path / "jobs" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        job = {
            "job_id": job_id,
            "protocol": request.protocol_name,
            "parameters": request.parameters,
            "status": JobStatus.PENDING,
            "submitted_at": now,
            "output_dir": str(output_dir),
        }
        self._jobs[job_id] = job

        if not settings.has_pipeline_pilot:
            job["status"] = JobStatus.FAILED
            job["errors"] = ["Pipeline Pilot Server not configured. Set DS_PIPELINE_PILOT_URL."]
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                submitted_at=now,
                errors=job.get("errors", []),
            )

        try:
            script = self._build_protocol_script(request)
            result = await self._run_perl_script(script, f"protocol_{job_id}")

            job["status"] = JobStatus.COMPLETED if result.get("success") else JobStatus.FAILED
            job["completed_at"] = datetime.now(timezone.utc)
            job["warnings"] = result.get("warnings", [])
            job["errors"] = result.get("errors", [])
            job["result_files"] = result.get("files", [])

            return JobResult(
                job_id=job_id,
                status=JobStatus(job["status"]),
                submitted_at=now,
                completed_at=job.get("completed_at"),
                warnings=job.get("warnings", []),
                errors=job.get("errors", []),
                result_files=job.get("result_files", []),
            )
        except subprocess.TimeoutExpired:
            job["status"] = JobStatus.FAILED
            job["errors"] = [f"Protocol execution timed out after {settings.ds_job_timeout_seconds}s"]
            return JobResult(job_id=job_id, status=JobStatus.FAILED, errors=job["errors"])
        except Exception as e:
            job["status"] = JobStatus.FAILED
            job["errors"] = [str(e)]
            return JobResult(job_id=job_id, status=JobStatus.FAILED, errors=job["errors"])

    async def get_job_status(self, job_id: str) -> JobResult:
        job = self._jobs.get(job_id)
        if not job:
            return JobResult(job_id=job_id, status=JobStatus.FAILED, errors=["Job not found"])
        return JobResult(
            job_id=job_id,
            status=JobStatus(job["status"]),
            submitted_at=job.get("submitted_at"),
            completed_at=job.get("completed_at"),
            warnings=job.get("warnings", []),
            errors=job.get("errors", []),
            result_files=job.get("result_files", []),
        )

    async def cancel_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = JobStatus.CANCELLED
            return True
        return False

    async def list_jobs(self) -> list[JobResult]:
        return [
            JobResult(
                job_id=j["job_id"],
                status=JobStatus(j["status"]),
                submitted_at=j.get("submitted_at"),
                completed_at=j.get("completed_at"),
            )
            for j in self._jobs.values()
        ]

    async def convert_structure(self, request: ConvertStructureRequest) -> str:
        validated_input = validate_path(request.input_path, must_exist=True)
        if not is_safe_extension(request.input_path):
            raise ValueError(f"Unsupported input format: {request.input_path}")

        output_path = request.output_path or str(validated_input.with_suffix(f".{request.output_format}"))
        script = self._build_convert_script(str(validated_input), output_path, request.output_format)
        result = await self._run_perl_script(script, f"convert_{uuid.uuid4().hex[:8]}")
        return output_path if result.get("success") else str(validated_input)

    async def render_structure(self, request: RenderStructureRequest) -> str:
        """Render a structure to an image file via Discovery Studio client."""
        validated = validate_path(request.molecule_path, must_exist=True)
        output_image = request.output_path or str(validated.with_suffix(f".{request.output_format}"))
        view_res = await self.view_in_gui(
            ViewInGuiRequest(
                file_path=str(validated),
                display_style=request.representation,
                capture_snapshot=True,
                snapshot_path=output_image,
            )
        )
        return view_res.snapshot_image_path or output_image

    async def prepare_structure(self, request: PrepareStructureRequest) -> PrepareStructureResult:
        """Clean protein, add hydrogens at specified pH, and optionally strip waters."""
        validated_input = validate_path(request.input_path, must_exist=True)
        out_path = request.output_path or str(validated_input.with_name(f"prepared_{validated_input.name}"))
        script = self._build_prepare_script(
            str(validated_input), out_path, request.ph, request.keep_waters, request.standardize_names
        )
        result = await self._run_perl_script(script, f"prepare_{uuid.uuid4().hex[:8]}")
        return PrepareStructureResult(
            mock=False,
            input_path=str(validated_input),
            output_path=out_path if result.get("success") else str(validated_input),
            ph=request.ph,
            initial_atoms=result.get("initial_atoms", 0),
            final_atoms=result.get("final_atoms", 0),
            hydrogens_added=result.get("hydrogens_added", 0),
            waters_removed=result.get("waters_removed", 0),
            formal_charge=result.get("formal_charge", 0.0),
            status="prepared" if result.get("success") else "failed",
            warnings=result.get("warnings", []),
        )

    async def analyze_binding_site(
        self, file_path: str, grid_resolution: float = 0.5, site_opening: float = 4.0
    ) -> BindingSiteAnalysisResult:
        """Detect binding pockets / cavities and compute volumes in Angstroms^3."""
        validated_input = validate_path(file_path, must_exist=True)
        script = self._build_cavity_script(str(validated_input), grid_resolution, site_opening)
        result = await self._run_perl_script(script, f"cavity_{uuid.uuid4().hex[:8]}")
        raw_sites = result.get("sites", [])
        sites = [
            BindingSiteInfo(
                site_id=s.get("id", i + 1),
                name=s.get("name", f"Site_{i + 1}"),
                center=s.get("center", [0.0, 0.0, 0.0]),
                volume_angstrom3=s.get("volume", 0.0),
                point_count=s.get("points", 0),
                lining_residues=s.get("residues", []),
            )
            for i, s in enumerate(raw_sites)
        ]
        return BindingSiteAnalysisResult(
            mock=False,
            file_path=str(validated_input),
            site_count=len(sites),
            sites=sites,
            grid_resolution_angstrom=grid_resolution,
            method="cavity_detection",
            warnings=result.get("warnings", []),
        )

    async def view_in_gui(self, request: ViewInGuiRequest) -> ViewInGuiResult:
        """Dispatch structure and visual display styles directly to the active Discovery Studio window."""
        snap_file = request.snapshot_path
        if request.capture_snapshot and not snap_file:
            snap_file = str(Path(tempfile.gettempdir()) / f"ds_view_{uuid.uuid4().hex[:8]}.png")

        target_file = ""
        if request.file_path:
            target_file = str(validate_path(request.file_path, must_exist=True))

        script = self._build_gui_view_script(
            target_file=target_file,
            display_style=request.display_style,
            color_scheme=request.color_scheme,
            rotate_x=request.rotate_x,
            rotate_y=request.rotate_y,
            snapshot_path=snap_file if request.capture_snapshot else "",
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pl", prefix="ds_gui_", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_file = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                str(self._ds_exe),
                script_file,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            snap_ok = None
            if snap_file:
                for _ in range(30):
                    if os.path.isfile(snap_file) and os.path.getsize(snap_file) > 0:
                        snap_ok = snap_file
                        break
                    await asyncio.sleep(0.1)

            return ViewInGuiResult(
                mock=False,
                success=True,
                document_name=Path(target_file).name if target_file else "Active Window",
                file_path=target_file,
                display_style=request.display_style,
                color_scheme=request.color_scheme,
                snapshot_image_path=snap_ok,
                message="Dispatched visual update to active Discovery Studio Molecule Window.",
            )
        finally:
            try:
                asyncio.create_task(_delayed_unlink(script_file, 30.0))
            except Exception:
                pass

    async def get_active_workspace(self) -> ActiveWorkspaceResult:
        """Query state and active documents of the running Discovery Studio GUI."""
        gui_running = False
        pid = None
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "Get-Process DiscoveryStudio* -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
                text=True,
            ).strip()
            if out:
                pids = [int(p.strip()) for p in out.split() if p.strip().isdigit()]
                if pids:
                    gui_running = True
                    pid = pids[0]
        except Exception:
            pass

        if not gui_running:
            return ActiveWorkspaceResult(
                mock=False,
                is_gui_running=False,
                message="Discovery Studio GUI is not currently running.",
            )

        status_json_path = str(Path(tempfile.gettempdir()) / f"ds_ws_{uuid.uuid4().hex[:8]}.json")
        script = f'''use strict;
use MdmDiscoveryScript;
use JSON::PP qw(encode_json);

my $doc = eval {{ DiscoveryScript::LastActiveDocument(MdmModelType) }};
my $info = {{}};
if ($doc) {{
    $info->{{"has_doc"}} = JSON::PP::true;
    $info->{{"name"}} = eval {{ $doc->Name }} || "";
    $info->{{"atoms"}} = eval {{ $doc->Atoms->Count }} || 0;
    $info->{{"models"}} = eval {{ $doc->Molecules->Count }} || 0;
    $info->{{"selected"}} = eval {{ $doc->SelectedObjects->Count }} || 0;
}} else {{
    $info->{{"has_doc"}} = JSON::PP::false;
}}

open(my $fh, ">", "{status_json_path.replace(chr(92), "/")}");
print $fh encode_json($info);
close($fh);
'''
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pl", prefix="ds_ws_check_", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_file = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                str(self._ds_exe),
                script_file,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            info = {}
            if os.path.isfile(status_json_path):
                try:
                    with open(status_json_path, "r", encoding="utf-8") as jf:
                        info = json.load(jf)
                except Exception:
                    pass
                try:
                    os.unlink(status_json_path)
                except OSError:
                    pass

            has_doc = info.get("has_doc", False)
            return ActiveWorkspaceResult(
                mock=False,
                is_gui_running=True,
                process_id=pid,
                has_active_document=has_doc,
                document_name=info.get("name"),
                document_path=None,
                model_count=info.get("models", 0),
                atom_count=info.get("atoms", 0),
                selected_count=info.get("selected", 0),
                message="Connected to active Discovery Studio session.",
            )
        finally:
            try:
                asyncio.create_task(_delayed_unlink(script_file, 30.0))
            except Exception:
                pass

    async def extract_sequence(self, request: ExtractSequenceRequest) -> ExtractSequenceResult:
        """Extract protein sequence (FASTA format and per-residue breakdown) from a structure."""
        valid_path = validate_path(request.file_path, must_exist=True)
        script = self._build_extract_sequence_script(str(valid_path), request.chain_id)
        result = await self._run_perl_script(script, "extract_seq")

        if not result.get("success", False):
            raise DiscoveryStudioError(f"Sequence extraction failed: {result.get('error', 'unknown error')}")

        chains: list[ChainSequence] = []
        for c in result.get("chains", []):
            residues = [
                ResidueInfo(id=str(r.get("id", "")), name=str(r.get("name", "")), symbol=str(r.get("symbol", "")))
                for r in c.get("residues", [])
            ]
            chains.append(
                ChainSequence(
                    chain_id=str(c.get("chain_id", "A")),
                    length=int(c.get("length", len(residues))),
                    fasta_sequence=str(c.get("fasta", "")),
                    residues=[] if request.compact else residues,
                )
            )

        fasta_lines = []
        for c in chains:
            fasta_lines.append(f">Chain_{c.chain_id} | {valid_path.name} | length={c.length}")
            seq = c.fasta_sequence
            for i in range(0, len(seq), 80):
                fasta_lines.append(seq[i : i + 80])

        return ExtractSequenceResult(
            mock=False,
            file_path=str(valid_path),
            total_residues=sum(c.length for c in chains),
            chains=chains,
            fasta_formatted="\n".join(fasta_lines),
        )

    async def mutate_residue(self, request: MutateResidueRequest) -> MutateResidueResult:
        """Introduce an in-silico single amino-acid point mutation and repack sidechains."""
        valid_in = validate_path(request.file_path, must_exist=True)
        if request.output_path:
            valid_out = Path(request.output_path)
        else:
            stem = valid_in.stem
            aa_code = request.target_amino_acid.upper()
            valid_out = valid_in.parent / f"{stem}_mut_{request.residue_id}_{aa_code}.pdb"

        script = self._build_mutate_residue_script(
            input_path=str(valid_in),
            output_path=str(valid_out),
            chain_id=request.chain_id,
            residue_id=request.residue_id,
            target_aa=request.target_amino_acid,
            repack=request.repack_and_clean,
        )
        result = await self._run_perl_script(script, "mutate_res")

        if not result.get("success", False):
            raise DiscoveryStudioError(f"Mutagenesis failed: {result.get('error', 'unknown error')}")

        return MutateResidueResult(
            mock=False,
            success=True,
            input_path=str(valid_in),
            output_path=str(valid_out),
            chain_id=str(result.get("chain_id", request.chain_id or "A")),
            residue_id=str(request.residue_id),
            original_residue=str(result.get("original_residue", "")),
            mutated_residue=str(result.get("mutated_residue", f"{request.target_amino_acid.upper()}{request.residue_id}")),
            repacked=request.repack_and_clean,
            atom_count=int(result.get("final_atoms", 0)),
            message=f"Successfully mutated {result.get('original_residue', request.residue_id)} to {result.get('mutated_residue', request.target_amino_acid)} and saved to {valid_out.name}.",
        )

    async def analyze_interface(self, request: AnalyzeInterfaceRequest) -> AnalyzeInterfaceResult:
        """Analyze contacts, hydrogen bonds, and steric clashes between two protein chains."""
        valid_path = validate_path(request.file_path, must_exist=True)
        script = self._build_analyze_interface_script(
            file_path=str(valid_path),
            chain_1=request.chain_1,
            chain_2=request.chain_2,
            cutoff=request.contact_cutoff_angstrom,
        )
        result = await self._run_perl_script(script, "analyze_interface")

        if not result.get("success", False):
            raise DiscoveryStudioError(f"Interface analysis failed: {result.get('error', 'unknown error')}")

        hbonds = [
            InterfaceHBond(
                donor=str(hb.get("donor", "")),
                acceptor=str(hb.get("acceptor", "")),
                distance_angstrom=float(hb.get("distance", 0.0)),
            )
            for hb in result.get("hydrogen_bonds", [])
        ]
        clashes = [
            InterfaceClash(
                atom_1=str(c.get("atom_1", "")),
                atom_2=str(c.get("atom_2", "")),
                overlap_angstrom=float(c.get("overlap", 0.0)),
            )
            for c in result.get("clashes", [])
        ]

        c1_res = [str(r) for r in result.get("contact_residues_chain_1", [])]
        c2_res = [str(r) for r in result.get("contact_residues_chain_2", [])]
        total_contacts = len(c1_res) + len(c2_res)

        summary = (
            f"Interface between Chain {request.chain_1} ({len(c1_res)} residues) and "
            f"Chain {request.chain_2} ({len(c2_res)} residues): {len(hbonds)} hydrogen bond(s), "
            f"{len(clashes)} steric clash(es) at {request.contact_cutoff_angstrom} Å cutoff."
        )

        return AnalyzeInterfaceResult(
            mock=False,
            file_path=str(valid_path),
            chain_1=request.chain_1,
            chain_2=request.chain_2,
            contact_residues_chain_1=c1_res,
            contact_residues_chain_2=c2_res,
            total_contacts=total_contacts,
            hydrogen_bonds=hbonds[:10] if request.compact else hbonds,
            clashes=clashes,
            interface_summary=summary,
        )

    async def superimpose_structures(self, request: SuperimposeStructuresRequest) -> SuperimposeStructuresResult:
        """Superimpose two protein 3D structures and calculate RMSD (All-Atom, Backbone, C-Alpha)."""
        valid_ref = validate_path(request.reference_path, must_exist=True)
        valid_tgt = validate_path(request.target_path, must_exist=True)
        valid_out = None
        if request.output_path:
            valid_out = validate_path(request.output_path, must_exist=False)

        script = self._build_superimpose_script(
            ref_path=str(valid_ref),
            tgt_path=str(valid_tgt),
            align_by=request.align_by,
            output_path=str(valid_out) if valid_out else "",
        )
        result = await self._run_perl_script(script, "superimpose")
        if not result.get("success", False):
            raise DiscoveryStudioError(f"Superposition failed: {result.get('error', 'unknown error')}")

        ca_rmsd = float(result.get("rmsd_calpha", 0.0))
        mc_rmsd = float(result.get("rmsd_mainchain", 0.0))
        all_rmsd = float(result.get("rmsd_all_atom", 0.0))
        aligned_atoms = int(result.get("aligned_atoms", 0))

        summary = (
            f"Superimposed {valid_tgt.name} onto {valid_ref.name} ({request.align_by}): "
            f"C-alpha RMSD = {ca_rmsd:.3f} A, Mainchain RMSD = {mc_rmsd:.3f} A, "
            f"All-atom RMSD = {all_rmsd:.3f} A."
        )

        return SuperimposeStructuresResult(
            mock=False,
            reference_path=str(valid_ref),
            target_path=str(valid_tgt),
            rmsd_all_atom=all_rmsd,
            rmsd_calpha=ca_rmsd,
            rmsd_mainchain=mc_rmsd,
            aligned_atoms=aligned_atoms,
            superimposed_output_path=str(valid_out) if valid_out else None,
            summary=summary,
        )

    async def align_sequences(self, request: AlignSequencesRequest) -> AlignSequencesResult:
        """Perform pairwise protein sequence alignment and compute identity/similarity percentages."""
        def clean_seq(raw: str) -> str:
            lines = raw.strip().splitlines()
            seq_lines = [l.strip() for l in lines if not l.startswith(">")]
            return "".join(seq_lines).upper()

        s1 = clean_seq(request.sequence_1)
        s2 = clean_seq(request.sequence_2)

        aln = self._needleman_wunsch(s1, s2)

        view_lines = []
        a1 = aln["aligned_seq1"]
        a2 = aln["aligned_seq2"]
        mk = aln["markup"]
        for idx in range(0, len(a1), 60):
            view_lines.append(f"{request.name_1:<10} {a1[idx:idx+60]}")
            view_lines.append(f"{'':<10} {mk[idx:idx+60]}")
            view_lines.append(f"{request.name_2:<10} {a2[idx:idx+60]}")
            view_lines.append("")

        ident = aln["identity_percentage"]
        sim = aln["similarity_percentage"]
        summary = (
            f"Pairwise global alignment ({request.name_1} vs {request.name_2}): "
            f"{ident:.2f}% identity, {sim:.2f}% similarity across {aln['aligned_length']} positions "
            f"({aln['matches']} matches, {aln['mismatches']} substitutions, {aln['gaps']} gaps)."
        )

        return AlignSequencesResult(
            mock=False,
            name_1=request.name_1,
            name_2=request.name_2,
            identity_percentage=ident,
            similarity_percentage=sim,
            alignment_score=float(aln["score"]),
            aligned_length=aln["aligned_length"],
            matches=aln["matches"],
            mismatches=aln["mismatches"],
            gaps=aln["gaps"],
            alignment_view="\n".join(view_lines),
            summary=summary,
        )

    async def calculate_ramachandran(self, request: CalculateRamachandranRequest) -> CalculateRamachandranResult:
        """Calculate per-residue Phi/Psi backbone dihedral angles and classify Ramachandran regions."""
        valid_path = validate_path(request.file_path, must_exist=True)
        res = self._compute_ramachandran(str(valid_path), request.chain_id)

        evaluated = len(res)
        favored = [r for r in res if r.region == "favored"]
        allowed = [r for r in res if r.region == "allowed"]
        outliers = [r for r in res if r.region == "outlier"]

        fav_pct = round((len(favored) / evaluated * 100) if evaluated > 0 else 0.0, 2)
        all_pct = round((len(allowed) / evaluated * 100) if evaluated > 0 else 0.0, 2)
        out_pct = round((len(outliers) / evaluated * 100) if evaluated > 0 else 0.0, 2)

        outlier_strs = [f"{r.name} (phi={r.phi:.1f} deg, psi={r.psi:.1f} deg)" for r in outliers]
        summary = (
            f"Ramachandran validation for {valid_path.name}: {len(favored)}/{evaluated} ({fav_pct}%) in favored regions, "
            f"{len(allowed)}/{evaluated} ({all_pct}%) in allowed regions, "
            f"{len(outliers)}/{evaluated} ({out_pct}%) outliers."
        )

        return CalculateRamachandranResult(
            mock=False,
            file_path=str(valid_path),
            total_evaluated=evaluated,
            favored_count=len(favored),
            favored_percentage=fav_pct,
            allowed_count=len(allowed),
            allowed_percentage=all_pct,
            outlier_count=len(outliers),
            outlier_percentage=out_pct,
            outlier_residues=outlier_strs,
            plot_image_path=None,
            residues=[] if request.compact else res,
            summary=summary,
        )

    async def evaluate_mutant(self, request: EvaluateMutantRequest) -> EvaluateMutantResult:
        """All-in-one general-purpose in-silico mutation, alignment, superposition, and stereochemical evaluation."""
        valid_in = validate_path(request.file_path, must_exist=True)
        if request.output_path:
            valid_out = Path(request.output_path)
        else:
            stem = valid_in.stem
            aa_code = request.target_amino_acid.upper()
            valid_out = valid_in.parent / f"{stem}_mut_{request.residue_id}_{aa_code}.pdb"

        # 1. Mutate residue
        mut_req = MutateResidueRequest(
            file_path=str(valid_in),
            chain_id=request.chain_id,
            residue_id=request.residue_id,
            target_amino_acid=request.target_amino_acid,
            repack_and_clean=request.repack_and_clean,
            output_path=str(valid_out),
        )
        mut_res = await self.mutate_residue(mut_req)

        # 2. Extract sequences for WT and mutant
        seq_wt = await self.extract_sequence(ExtractSequenceRequest(file_path=str(valid_in), chain_id=request.chain_id, compact=True))
        seq_mut = await self.extract_sequence(ExtractSequenceRequest(file_path=str(valid_out), chain_id=request.chain_id, compact=True))

        wt_fasta = seq_wt.chains[0].fasta_sequence if seq_wt.chains else ""
        mut_fasta = seq_mut.chains[0].fasta_sequence if seq_mut.chains else ""

        # 3. Pairwise sequence alignment
        aln_res = await self.align_sequences(AlignSequencesRequest(
            sequence_1=wt_fasta,
            sequence_2=mut_fasta,
            name_1="WildType",
            name_2=f"Mut_{request.target_amino_acid}{request.residue_id}",
        ))

        # 4. 3D Coordinate Superposition
        super_res = await self.superimpose_structures(SuperimposeStructuresRequest(
            reference_path=str(valid_in),
            target_path=str(valid_out),
            align_by="calpha",
        ))

        # 5. Ramachandran stereochemical assessment
        rama_res = await self.calculate_ramachandran(CalculateRamachandranRequest(
            file_path=str(valid_out),
            chain_id=request.chain_id,
            compact=True,
        ))

        verdict = "WELL-TOLERATED"
        if super_res.rmsd_calpha > 1.5 or rama_res.outlier_count > 3:
            verdict = "HIGH-RISK"
        elif super_res.rmsd_calpha > 0.8 or rama_res.outlier_count > 1:
            verdict = "POTENTIAL-STRAIN"

        summary = (
            f"Evaluation of mutation {mut_res.original_residue} -> {mut_res.mutated_residue} on {valid_in.name}: "
            f"Verdict is {verdict}. Sequence identity {aln_res.identity_percentage:.2f}%. "
            f"C-alpha RMSD = {super_res.rmsd_calpha:.3f} A, Mainchain RMSD = {super_res.rmsd_mainchain:.3f} A. "
            f"Ramachandran stereochemistry: {rama_res.favored_percentage:.1f}% favored, {rama_res.allowed_percentage:.1f}% allowed, "
            f"{rama_res.outlier_count} outlier(s)."
        )

        return EvaluateMutantResult(
            mock=False,
            input_file=str(valid_in),
            output_file=str(valid_out),
            mutation=f"{mut_res.original_residue} -> {mut_res.mutated_residue}",
            sequence_identity=aln_res.identity_percentage,
            sequence_similarity=aln_res.similarity_percentage,
            rmsd_calpha=super_res.rmsd_calpha,
            rmsd_mainchain=super_res.rmsd_mainchain,
            rmsd_all_atom=super_res.rmsd_all_atom,
            ramachandran_favored_percentage=rama_res.favored_percentage,
            ramachandran_allowed_percentage=rama_res.allowed_percentage,
            ramachandran_outlier_count=rama_res.outlier_count,
            outlier_residues=rama_res.outlier_residues,
            verdict=verdict,
            summary=summary,
        )


    async def _run_perl_script(self, script: str, script_name: str) -> dict[str, Any]:
        """Run a Perl script using the bundled interpreter with Discovery Studio libraries."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pl", prefix=f"{script_name}_", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name

        env = os.environ.copy()
        env["AccelrysRoot"] = str(self._ds_root)
        env["ACCELRYS_ROOT"] = str(self._ds_root)
        ds_bin = str(self._ds_root / "bin")
        env["PATH"] = ds_bin + os.pathsep + env.get("PATH", "")

        perl_args = [
            str(self._perl_exe),
        ]
        for lib in self._perl_lib:
            if os.path.isdir(lib):
                perl_args.extend(["-I", lib])
        perl_args.extend(["-I", ds_bin])
        perl_args.append(script_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *perl_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=settings.ds_job_timeout_seconds,
            )
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                return {"error": stderr_text or f"Perl exited with code {proc.returncode}"}

            # Try to extract JSON output between marker lines
            json_output = {}
            for line in stdout_text.split("\n"):
                if line.startswith("__DS_JSON__:"):
                    try:
                        json_output = json.loads(line[len("__DS_JSON__:"):])
                    except json.JSONDecodeError:
                        pass

            json_output.setdefault("stdout", stdout_text)
            json_output.setdefault("success", proc.returncode == 0)
            return json_output

        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _build_inspect_script(self, file_path: str) -> str:
        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use JSON::PP qw(encode_json);

my $infile = "{file_path.replace(chr(92), "/")}";
my $document = eval {{ DiscoveryScript::Open($infile) }};

if (!$document) {{
    print "__DS_JSON__:" . encode_json({{ error => "Could not open structure: $@" }}) . "\\n";
    exit(0);
}}

my $result = {{ format => "{Path(file_path).suffix.lower().lstrip('.')}" }};

my @molecules;
eval {{
    for (my $i = 0; $i < $document->Molecules->Count; $i++) {{
        push @molecules, $document->Molecules->Item($i);
    }}
}};
$result->{{"model_count"}} = scalar(@molecules);
$result->{{"atoms"}} = eval {{ $document->Atoms->Count }} || 0;

my @chains;
my @ligands;
my @metals;
my $waters = 0;
my @heteros;
my $residue_count = 0;

for my $mol (@molecules) {{
    eval {{
        my $aa_chains = $mol->AminoAcidChains;
        for (my $c = 0; $c < $aa_chains->Count; $c++) {{
            my $chain = $aa_chains->Item($c);
            push @chains, $chain->Name if $chain && $chain->Name;
            eval {{ $residue_count += $chain->Residues->Count; }};
        }}
    }};
    eval {{
        my $all_chains = $mol->Chains;
        if (!@chains && $all_chains) {{
            for (my $c = 0; $c < $all_chains->Count; $c++) {{
                my $chain = $all_chains->Item($c);
                push @chains, $chain->Name if $chain && $chain->Name;
            }}
        }}
    }};
}}

$result->{{"chains"}} = \\@chains;
$result->{{"ligands"}} = \\@ligands;
$result->{{"residues"}} = $residue_count;
$result->{{"waters"}} = $waters;
$result->{{"metals"}} = \\@metals;
$result->{{"heteroatoms"}} = \\@heteros;

print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_protocol_script(self, request: RunProtocolRequest) -> str:
        params_json = json.dumps(request.parameters)
        protocol_name = request.protocol_name
        server_url = settings.ds_pipeline_pilot_url

        return f'''#!/usr/bin/perl
use strict;
use warnings;
use ProtocolCommands;
use ProtocolDiscoveryScript;
use JSON::PP qw(encode_json);

my $protocolName = "{protocol_name}";
my $server = "{server_url}";

my $parameterMap = Protocol::ParameterMap::Create();
# Parameters would be set here based on protocol requirements
# This is a template - actual parameter mapping depends on the protocol

my $success = LaunchProtocol($protocolName, $parameterMap, $server);

my $result = {{}};
$result->{{"success"}} = $success ? JSON::PP::true : JSON::PP::false;
if ($success) {{
    $result->{{"status"}} = "completed";
}} else {{
    $result->{{"status"}} = "failed";
    $result->{{"errors"}} = ["Protocol execution returned failure"];
}}
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_convert_script(self, input_path: str, output_path: str, output_format: str) -> str:
        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use JSON::PP qw(encode_json);

my $infile = "{input_path.replace(chr(92), "/")}";
my $outfile = "{output_path.replace(chr(92), "/")}";

my $document = DiscoveryScript::Open($infile);
if (!$document) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Could not open file: $infile" }}) . "\\n";
    exit(0);
}}

# Save in requested format
$document->Save($outfile);

my $result = {{ success => JSON::PP::true, output => $outfile }};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_prepare_script(
        self, input_path: str, output_path: str, ph: float, keep_waters: bool, standardize: bool
    ) -> str:
        safe_in = input_path.replace(chr(92), "/")
        safe_out = output_path.replace(chr(92), "/")
        kw_val = 1 if keep_waters else 0
        std_val = 1 if standardize else 0

        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use ProteinDiscoveryScript;
use DSCommands;
use JSON::PP qw(encode_json);

my $infile = "{safe_in}";
my $outfile = "{safe_out}";

my $doc = eval {{ DiscoveryScript::Open($infile) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open structure" }}) . "\\n";
    exit(0);
}}

my $initial_atoms = eval {{ $doc->Atoms->Count }} || 0;
my $waters_removed = 0;

if (!{kw_val}) {{
    eval {{
        my $waters = $doc->Filter({{ Type => "Residue", Name => "HOH" }});
        if ($waters && $waters->Count > 0) {{
            $waters_removed = $waters->Count;
            $doc->DeleteObjects($waters);
        }}
    }};
}}

eval {{
    $doc->CleanProtein({{
        pH => {ph},
        HydrogenRepresentation => 'allHydrogenRepresentation',
        AdjustHydrogens => 1,
        DeleteDisorder => 1,
        StandardizeNames => {std_val},
    }});
}};

my $final_atoms = eval {{ $doc->Atoms->Count }} || 0;
my $charge = 0.0;
eval {{
    my $mols = $doc->Molecules;
    for (my $i = 0; $i < $mols->Count; $i++) {{
        $charge += $mols->Item($i)->FormalChargeSum;
    }}
}};

my $fmt = "pdb";
if ($outfile =~ /\\.([A-Za-z0-9]+)$/) {{
    $fmt = lc($1);
}}
$doc->Save($outfile, $fmt);

my $result = {{
    success => JSON::PP::true,
    initial_atoms => $initial_atoms,
    final_atoms => $final_atoms,
    hydrogens_added => $final_atoms - $initial_atoms + ($waters_removed * 3),
    waters_removed => $waters_removed,
    formal_charge => $charge,
    output_path => $outfile,
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_cavity_script(self, input_path: str, grid_res: float, site_opening: float) -> str:
        safe_in = input_path.replace(chr(92), "/")
        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use SbdDiscoveryScript;
use DSCommands;
use JSON::PP qw(encode_json);

my $infile = "{safe_in}";
my $doc = eval {{ DiscoveryScript::Open($infile) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open structure" }}) . "\\n";
    exit(0);
}}

my @site_list;
eval {{
    eval {{ Delete($doc, GetWaters($doc)); }};
    my $mols = $doc->Molecules;
    if ($mols && $mols->Count > 0) {{
        my $receptor = $mols->Item(0);
        my $sites = $doc->CreateBindingSitesFromCavities($receptor);
        if ($sites) {{
            for (my $i = 0; $i < $sites->Count; $i++) {{
                my $s = $sites->Item($i);
                my $center = eval {{ $s->Center }} || eval {{ $s->CenterOfMass }};
                my @coords = $center ? ($center->X, $center->Y, $center->Z) : (0.0, 0.0, 0.0);
                my $vol = eval {{ $s->GetProperty("Volume") }} || 0.0;
                my $pts = eval {{ $s->BindingSitePoints->Count }} || 0;
                push @site_list, {{
                    id => $i + 1,
                    name => eval {{ $s->Name }} || ("Site_" . ($i + 1)),
                    center => \\@coords,
                    volume => $vol,
                    points => $pts,
                    residues => []
                }};
            }}
        }}
    }}
}};

my $result = {{
    success => JSON::PP::true,
    sites => \\@site_list,
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_gui_view_script(
        self, target_file: str, display_style: str, color_scheme: str, rotate_x: float, rotate_y: float, snapshot_path: str
    ) -> str:
        style_map = {
            "ribbon_flat": "Mdm::styleProteinRibbonFlat",
            "ribbon_tube": "Mdm::styleProteinRibbonTube",
            "ball_and_stick": "Mdm::styleAtomBallAndStick",
            "cpk": "Mdm::styleAtomCPK",
            "schematic": "Mdm::styleProteinSchematic",
            "stick": "Mdm::styleAtomStick",
            "wire": "Mdm::styleProteinCAlphaWire",
        }
        color_map = {
            "secondary": "Mdm::proteinColorBySecondaryType",
            "rainbow": "Mdm::proteinColorByRainbow",
            "chain": "Mdm::proteinColorByAminoAcidChain",
            "molecule": "Mdm::proteinColorByMolecule",
            "charge": "Mdm::proteinColorByResidue",
            "hydrophobicity": "Mdm::proteinColorByHydrophobicity",
        }
        ds_style = style_map.get(display_style, "Mdm::styleProteinRibbonFlat")
        ds_color = color_map.get(color_scheme, "Mdm::proteinColorBySecondaryType")

        open_block = ""
        if target_file:
            safe_target = target_file.replace(chr(92), "/")
            open_block = f'''
my $doc = eval {{ DiscoveryScript::Open("{safe_target}") }};
'''
        else:
            open_block = '''
my $doc = eval {{ DiscoveryScript::LastActiveDocument(MdmModelType) }};
'''

        snap_block = ""
        if snapshot_path:
            safe_snap = snapshot_path.replace(chr(92), "/")
            snap_block = f'''
eval {{ $doc->SaveImage("{safe_snap}", "png"); }};
'''

        return f'''use strict;
use warnings;
use MdmDiscoveryScript;
use DSCommands;

{open_block}

if ($doc) {{
    $doc->EnableUpdateViews(0);

    # 1. Apply Protein Display Style
    eval {{
        $doc->SetProteinDisplayStyle({ds_style});
    }};

    # 2. Apply Protein Color Scheme
    eval {{
        $doc->SetProteinColorScheme({ds_color});
    }};

    # 3. Rotate View if specified
    if ({rotate_x} != 0 || {rotate_y} != 0) {{
        eval {{
            $doc->RotateView({rotate_x}, {rotate_y}, 0);
        }};
    }}

    # 4. Frame view
    eval {{ $doc->FitView(); }};

    $doc->EnableUpdateViews(1);
    $doc->UpdateViews();

    {snap_block}
}}
'''

    def _build_extract_sequence_script(self, file_path: str, filter_chain: str | None) -> str:
        safe_in = file_path.replace(chr(92), "/")
        safe_chain = (filter_chain or "").strip()
        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use JSON::PP qw(encode_json);

my $infile = "{safe_in}";
my $doc = eval {{ DiscoveryScript::Open($infile) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open structure" }}) . "\\n";
    exit(0);
}}

my @chains_out;
my $chains = eval {{ $doc->AminoAcidChains }};
if ($chains && $chains->Count > 0) {{
    for (my $c = 0; $c < $chains->Count; $c++) {{
        my $chain = $chains->Item($c);
        my $cname = eval {{ $chain->Name }} || eval {{ $chain->Id }} || ("Chain_" . ($c + 1));
        if ("{safe_chain}" ne "" && $cname ne "{safe_chain}" && (eval {{ $chain->Id }} // "") ne "{safe_chain}") {{
            next;
        }}
        my $seq = "";
        my @res_list;
        my $aas = eval {{ $chain->AminoAcids }};
        if ($aas) {{
            for (my $i = 0; $i < $aas->Count; $i++) {{
                my $aa = $aas->Item($i);
                my $sym = eval {{ $aa->Symbol }} || eval {{ $aa->Abbreviation }} || substr(eval {{ $aa->Name }} || "X", 0, 1);
                $seq .= $sym;
                push @res_list, {{
                    id => eval {{ $aa->Id }} || ($i + 1),
                    name => eval {{ $aa->Name }} || ("Res_" . ($i + 1)),
                    symbol => $sym
                }};
            }}
        }}
        push @chains_out, {{
            chain_id => $cname,
            length => length($seq),
            fasta => $seq,
            residues => \\@res_list
        }};
    }}
}}

if (scalar(@chains_out) == 0 && $doc->Molecules->Count > 0) {{
    my $mol = $doc->Molecules->Item(0);
    my $mseq = eval {{ $mol->AminoAcidSequence }} || "";
    if ($mseq) {{
        push @chains_out, {{
            chain_id => "A",
            length => length($mseq),
            fasta => $mseq,
            residues => []
        }};
    }}
}}

my $result = {{
    success => JSON::PP::true,
    chains => \\@chains_out
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_mutate_residue_script(
        self,
        input_path: str,
        output_path: str,
        chain_id: str | None,
        residue_id: str,
        target_aa: str,
        repack: bool,
    ) -> str:
        safe_in = input_path.replace(chr(92), "/")
        safe_out = output_path.replace(chr(92), "/")
        safe_chain = (chain_id or "").strip()
        safe_res = str(residue_id).strip()

        aa_clean = target_aa.strip().upper()
        aa_map = {
            "A": "ala", "ALA": "ala", "ALANINE": "ala",
            "R": "arg", "ARG": "arg", "ARGININE": "arg",
            "N": "asn", "ASN": "asn", "ASPARAGINE": "asn",
            "D": "asp", "ASP": "asp", "ASPARTIC ACID": "asp", "ASPARTATE": "asp",
            "C": "cys", "CYS": "cys", "CYSTEINE": "cys",
            "Q": "gln", "GLN": "gln", "GLUTAMINE": "gln",
            "E": "glu", "GLU": "glu", "GLUTAMIC ACID": "glu", "GLUTAMATE": "glu",
            "G": "gly", "GLY": "gly", "GLYCINE": "gly",
            "H": "his", "HIS": "his", "HISTIDINE": "his",
            "I": "ile", "ILE": "ile", "ISOLEUCINE": "ile",
            "L": "leu", "LEU": "leu", "LEUCINE": "leu",
            "K": "lys", "LYS": "lys", "LYSINE": "lys",
            "M": "met", "MET": "met", "METHIONINE": "met",
            "F": "phe", "PHE": "phe", "PHENYLALANINE": "phe",
            "P": "pro", "PRO": "pro", "PROLINE": "pro",
            "S": "ser", "SER": "ser", "SERINE": "ser",
            "T": "thr", "THR": "thr", "THREONINE": "thr",
            "W": "trp", "TRP": "trp", "TRYPTOPHAN": "trp",
            "Y": "tyr", "TYR": "tyr", "TYROSINE": "tyr",
            "V": "val", "VAL": "val", "VALINE": "val",
        }
        mapped_type = aa_map.get(aa_clean, "ala")
        repack_flag = 1 if repack else 0

        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use ProteinDiscoveryScript;
use DSCommands;
use JSON::PP qw(encode_json);

my $infile = "{safe_in}";
my $outfile = "{safe_out}";
my $target_chain = "{safe_chain}";
my $res_target_id = "{safe_res}";

my $doc = eval {{ DiscoveryScript::Open($infile) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open structure" }}) . "\\n";
    exit(0);
}}

my $target_res;
my $orig_res_name = "";
my $chain_name = "";

my $aas = eval {{ $doc->AminoAcids }};
if ($aas) {{
    for (my $i = 0; $i < $aas->Count; $i++) {{
        my $item = $aas->Item($i);
        my $id = eval {{ $item->Id }} // "";
        my $name = eval {{ $item->Name }} // "";
        if ($id eq $res_target_id || $name =~ /^[A-Za-z]+$res_target_id$/) {{
            my $p = eval {{ $item->Parent }};
            my $pname = eval {{ $p->Name }} // "";
            my $pid = eval {{ $p->Id }} // "";
            if ($target_chain eq "" || $pname eq $target_chain || $pid eq $target_chain) {{
                $target_res = $item;
                $orig_res_name = $name;
                $chain_name = $pname || $pid || "A";
                last;
            }}
        }}
    }}
}}

if (!$target_res) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Residue $res_target_id not found in target structure/chain" }}) . "\\n";
    exit(0);
}}

eval {{
    $doc->MutateAminoAcid($target_res, Mdm::{mapped_type});
}};
if ($@) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "MutateAminoAcid failed: $@" }}) . "\\n";
    exit(0);
}}

my $mut_res_name = eval {{ $target_res->Name }} || "";

if ({repack_flag}) {{
    eval {{
        $doc->CleanProtein({{
            pH => 7.4,
            HydrogenRepresentation => 'allHydrogenRepresentation',
            AdjustHydrogens => 1,
            DeleteDisorder => 1,
            StandardizeNames => 1
        }});
    }};
}}

my $fmt = "pdb";
if ($outfile =~ /\\.([A-Za-z0-9]+)$/) {{
    $fmt = lc($1);
}}
$doc->Save($outfile, $fmt);
my $final_atoms = eval {{ $doc->Atoms->Count }} || 0;

my $result = {{
    success => JSON::PP::true,
    chain_id => $chain_name,
    original_residue => $orig_res_name,
    mutated_residue => $mut_res_name,
    final_atoms => $final_atoms
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_analyze_interface_script(
        self,
        file_path: str,
        chain_1: str,
        chain_2: str,
        cutoff: float,
    ) -> str:
        safe_in = file_path.replace(chr(92), "/")
        c1 = chain_1.strip()
        c2 = chain_2.strip()

        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use DSCommands;
use JSON::PP qw(encode_json);

my $infile = "{safe_in}";
my $c1_id = "{c1}";
my $c2_id = "{c2}";
my $cutoff = {cutoff};

my $doc = eval {{ DiscoveryScript::Open($infile) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open structure" }}) . "\\n";
    exit(0);
}}

my $chain1;
my $chain2;
my $chains = eval {{ $doc->Chains }};
if ($chains) {{
    for (my $c = 0; $c < $chains->Count; $c++) {{
        my $ch = $chains->Item($c);
        my $name = eval {{ $ch->Name }} || eval {{ $ch->Id }} || "";
        if ($name eq $c1_id) {{ $chain1 = $ch; }}
        if ($name eq $c2_id) {{ $chain2 = $ch; }}
    }}
}}

if (!$chain1 || !$chain2) {{
    my $aachains = eval {{ $doc->AminoAcidChains }};
    if ($aachains) {{
        for (my $c = 0; $c < $aachains->Count; $c++) {{
            my $ch = $aachains->Item($c);
            my $name = eval {{ $ch->Name }} || eval {{ $ch->Id }} || "";
            if ($name eq $c1_id) {{ $chain1 = $ch; }}
            if ($name eq $c2_id) {{ $chain2 = $ch; }}
        }}
    }}
}}

# Fallback: if only 2 chains exist and names differ
if ((!$chain1 || !$chain2) && $doc->Chains && $doc->Chains->Count >= 2) {{
    $chain1 = $doc->Chains->Item(0);
    $chain2 = $doc->Chains->Item(1);
}}

my %c1_residues;
my %c2_residues;
my @hbonds;
my @clashes;

if ($chain1 && $chain2) {{
    my $atoms1 = eval {{ $chain1->Atoms }};
    my $cutoff_sq = $cutoff * $cutoff;
    my $ca_thresh_sq = 12.0 * 12.0;

    my @r1_cache;
    my @r2_cache;

    my $aas1 = eval {{ $chain1->AminoAcids }};
    if ($aas1) {{
        for (my $i = 0; $i < $aas1->Count; $i++) {{
            my $res = $aas1->Item($i);
            my $ca = eval {{ $res->CAlpha }};
            my $cap = $ca ? eval {{ $ca->XYZ }} : undef;
            my $name = eval {{ $res->Name }} || ("Res_" . ($i + 1));
            my @coords;
            my $ats = eval {{ $res->Atoms }};
            if ($ats) {{
                for (my $a = 0; $a < $ats->Count; $a++) {{
                    my $at = $ats->Item($a);
                    my $p = eval {{ $at->XYZ }};
                    if ($p) {{
                        push @coords, [$p->X, $p->Y, $p->Z];
                    }}
                }}
            }}
            push @r1_cache, {{
                name => $name,
                cax => $cap ? $cap->X : undef,
                cay => $cap ? $cap->Y : undef,
                caz => $cap ? $cap->Z : undef,
                atoms => \\@coords
            }};
        }}
    }}

    if ($c1_id eq $c2_id) {{
        @r2_cache = @r1_cache;
    }} else {{
        my $aas2 = eval {{ $chain2->AminoAcids }};
        if ($aas2) {{
            for (my $i = 0; $i < $aas2->Count; $i++) {{
                my $res = $aas2->Item($i);
                my $ca = eval {{ $res->CAlpha }};
                my $cap = $ca ? eval {{ $ca->XYZ }} : undef;
                my $name = eval {{ $res->Name }} || ("Res_" . ($i + 1));
                my @coords;
                my $ats = eval {{ $res->Atoms }};
                if ($ats) {{
                    for (my $a = 0; $a < $ats->Count; $a++) {{
                        my $at = $ats->Item($a);
                        my $p = eval {{ $at->XYZ }};
                        if ($p) {{
                            push @coords, [$p->X, $p->Y, $p->Z];
                        }}
                    }}
                }}
                push @r2_cache, {{
                    name => $name,
                    cax => $cap ? $cap->X : undef,
                    cay => $cap ? $cap->Y : undef,
                    caz => $cap ? $cap->Z : undef,
                    atoms => \\@coords
                }};
            }}
        }}
    }}

    for (my $i = 0; $i < scalar(@r1_cache); $i++) {{
        my $r1 = $r1_cache[$i];
        next unless defined($r1->{{cax}});
        my $x1 = $r1->{{cax}}; my $y1 = $r1->{{cay}}; my $z1 = $r1->{{caz}};

        for (my $j = 0; $j < scalar(@r2_cache); $j++) {{
            next if ($c1_id eq $c2_id && $i == $j);
            my $r2 = $r2_cache[$j];
            next unless defined($r2->{{cax}});

            my $dx = $x1 - $r2->{{cax}};
            my $dy = $y1 - $r2->{{cay}};
            my $dz = $z1 - $r2->{{caz}};
            if (($dx*$dx + $dy*$dy + $dz*$dz) <= $ca_thresh_sq) {{
                my $ats1 = $r1->{{atoms}};
                my $ats2 = $r2->{{atoms}};
                my $contact = 0;
                for my $a (@$ats1) {{
                    for my $b (@$ats2) {{
                        my $adx = $a->[0] - $b->[0];
                        my $ady = $a->[1] - $b->[1];
                        my $adz = $a->[2] - $b->[2];
                        if (($adx*$adx + $ady*$ady + $adz*$adz) <= $cutoff_sq) {{
                            $c1_residues{{$r1->{{name}}}} = 1;
                            $c2_residues{{$r2->{{name}}}} = 1;
                            $contact = 1;
                            last;
                        }}
                    }}
                    last if $contact;
                }}
            }}
        }}
    }}

        eval {{
            my $hb_mon = $doc->CreateHydrogenBondMonitor($atoms1, Mdm::allAtomHydrogenBonds, Mdm::allMolecularHydrogenBonds);
            if ($hb_mon) {{
                my $hbs = $doc->HydrogenBonds;
                if ($hbs) {{
                    for (my $h = 0; $h < $hbs->Count; $h++) {{
                        my $hb = $hbs->Item($h);
                        my $don = eval {{ $hb->Atom1->Name }} || "Donor";
                        my $acc = eval {{ $hb->Atom2->Name }} || "Acceptor";
                        my $d = eval {{ $hb->Distance }} || 0.0;
                        push @hbonds, {{ donor => $don, acceptor => $acc, distance => $d }};
                    }}
                }}
            }}
        }};

        eval {{
            my $bump_mon = $doc->CreateBumpMonitor($atoms1);
            if ($bump_mon) {{
                my $bumps = $doc->Bumps;
                if ($bumps) {{
                    for (my $b = 0; $b < $bumps->Count; $b++) {{
                        my $bump = $bumps->Item($b);
                        my $at1 = eval {{ $bump->Atom1->Name }} || "Atom1";
                        my $at2 = eval {{ $bump->Atom2->Name }} || "Atom2";
                        my $ov = eval {{ $bump->Overlap }} || 0.0;
                        push @clashes, {{ atom_1 => $at1, atom_2 => $at2, overlap => $ov }};
                    }}
                }}
            }}
        }};
    }}

my @c1_list = sort keys %c1_residues;
my @c2_list = sort keys %c2_residues;

my $result = {{
    success => JSON::PP::true,
    contact_residues_chain_1 => \\@c1_list,
    contact_residues_chain_2 => \\@c2_list,
    hydrogen_bonds => \\@hbonds,
    clashes => \\@clashes
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _build_superimpose_script(
        self, ref_path: str, tgt_path: str, align_by: str, output_path: str
    ) -> str:
        safe_ref = ref_path.replace(chr(92), "/")
        safe_tgt = tgt_path.replace(chr(92), "/")
        safe_out = output_path.replace(chr(92), "/") if output_path else ""

        return f'''#!/usr/bin/perl
use strict;
use warnings;
use MdmDiscoveryScript;
use ProteinDiscoveryScript;
use DSCommands;
use JSON::PP qw(encode_json);

my $ref_file = "{safe_ref}";
my $tgt_file = "{safe_tgt}";
my $out_file = "{safe_out}";

my $doc = eval {{ DiscoveryScript::Open($ref_file) }};
if (!$doc) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to open reference structure" }}) . "\\n";
    exit(0);
}}

eval {{ $doc->Insert($tgt_file); }};
if ($@) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Failed to insert target structure: $@" }}) . "\\n";
    exit(0);
}}

if ($doc->Molecules->Count < 2) {{
    print "__DS_JSON__:" . encode_json({{ success => JSON::PP::false, error => "Target structure contains no valid molecule" }}) . "\\n";
    exit(0);
}}

my $mol_ref = $doc->Molecules->Item(0);
my $mol_tgt = $doc->Molecules->Item(1);

my $aas_ref = eval {{ $mol_ref->AminoAcids }};
my $aas_tgt = eval {{ $mol_tgt->AminoAcids }};

my $align_mode = Mdm::superimposeProteinUsingCAlphaAtoms;
if ("{align_by}" eq "mainchain") {{
    $align_mode = Mdm::superimposeProteinUsingMainChainAtoms;
}} elsif ("{align_by}" eq "all_atom") {{
    $align_mode = Mdm::superimposeProteinUsingAllAtoms;
}}

my $align_rmsd = eval {{
    $doc->SuperimposeProtein($aas_ref, $aas_tgt, $align_mode);
}} // 0.0;

my $ca_obj = eval {{ $doc->CalculateCAlphaRmsd($mol_ref, $mol_tgt, 0, 0) }};
my $mc_obj = eval {{ $doc->CalculateMainChainRmsd($mol_ref, $mol_tgt, 0, 0) }};
my $all_obj = eval {{ $doc->CalculateAllProteinRmsd($mol_ref, $mol_tgt, 0, 0) }};

my $val_ca = ref($ca_obj) ? $ca_obj->Item($ca_obj->Count - 1) : ($ca_obj // 0.0);
my $val_mc = ref($mc_obj) ? $mc_obj->Item($mc_obj->Count - 1) : ($mc_obj // 0.0);
my $val_all = ref($all_obj) ? $all_obj->Item($all_obj->Count - 1) : ($all_obj // 0.0);

if ($out_file ne "") {{
    eval {{
        $mol_ref->Select();
        $doc->DeleteSelection();
        my $fmt = "pdb";
        if ($out_file =~ /\\.([A-Za-z0-9]+)$/) {{ $fmt = lc($1); }}
        $doc->Save($out_file, $fmt);
    }};
}}

my $result = {{
    success => JSON::PP::true,
    rmsd_calpha => $val_ca,
    rmsd_mainchain => $val_mc,
    rmsd_all_atom => $val_all,
    rmsd_superimpose => $align_rmsd,
    aligned_atoms => eval {{ $mol_ref->Atoms->Count }} || 0,
}};
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''

    def _needleman_wunsch(
        self, seq1: str, seq2: str, match_score: int = 2, mismatch_penalty: int = -1, gap_penalty: int = -2
    ) -> dict[str, Any]:
        n, m = len(seq1), len(seq2)
        score_matrix = [[0] * (m + 1) for _ in range(n + 1)]

        for i in range(n + 1):
            score_matrix[i][0] = i * gap_penalty
        for j in range(m + 1):
            score_matrix[0][j] = j * gap_penalty

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                char1 = seq1[i - 1]
                char2 = seq2[j - 1]
                diag = score_matrix[i - 1][j - 1] + (match_score if char1 == char2 else mismatch_penalty)
                up = score_matrix[i - 1][j] + gap_penalty
                left = score_matrix[i][j - 1] + gap_penalty
                score_matrix[i][j] = max(diag, up, left)

        align1, align2, markup = [], [], []
        i, j = n, m
        matches, mismatches, gaps = 0, 0, 0

        # Conservative amino acid substitution groups
        sim_groups = [
            {"A", "V", "L", "I", "M"},
            {"F", "Y", "W"},
            {"K", "R", "H"},
            {"D", "E"},
            {"S", "T", "N", "Q"},
        ]

        def are_similar(c1: str, c2: str) -> bool:
            return any(c1 in g and c2 in g for g in sim_groups)

        similar_count = 0
        while i > 0 and j > 0:
            curr = score_matrix[i][j]
            char1 = seq1[i - 1]
            char2 = seq2[j - 1]
            diag = score_matrix[i - 1][j - 1] + (match_score if char1 == char2 else mismatch_penalty)
            up = score_matrix[i - 1][j] + gap_penalty

            if curr == diag:
                align1.append(char1)
                align2.append(char2)
                if char1 == char2:
                    markup.append("|")
                    matches += 1
                    similar_count += 1
                elif are_similar(char1, char2):
                    markup.append(":")
                    mismatches += 1
                    similar_count += 1
                else:
                    markup.append(".")
                    mismatches += 1
                i -= 1
                j -= 1
            elif curr == up:
                align1.append(char1)
                align2.append("-")
                markup.append(" ")
                gaps += 1
                i -= 1
            else:
                align1.append("-")
                align2.append(char2)
                markup.append(" ")
                gaps += 1
                j -= 1

        while i > 0:
            align1.append(seq1[i - 1])
            align2.append("-")
            markup.append(" ")
            gaps += 1
            i -= 1
        while j > 0:
            align1.append("-")
            align2.append(seq2[j - 1])
            markup.append(" ")
            gaps += 1
            j -= 1

        a1 = "".join(reversed(align1))
        a2 = "".join(reversed(align2))
        mark = "".join(reversed(markup))
        aligned_len = len(a1)
        ident = (matches / aligned_len * 100) if aligned_len > 0 else 0.0
        sim = (similar_count / aligned_len * 100) if aligned_len > 0 else 0.0

        return {
            "aligned_seq1": a1,
            "aligned_seq2": a2,
            "markup": mark,
            "aligned_length": aligned_len,
            "matches": matches,
            "mismatches": mismatches,
            "gaps": gaps,
            "identity_percentage": round(ident, 2),
            "similarity_percentage": round(sim, 2),
            "score": score_matrix[n][m],
        }

    def _calc_dihedral(
        self,
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        p3: tuple[float, float, float],
        p4: tuple[float, float, float],
    ) -> float:
        b1 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        b2 = (p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2])
        b3 = (p4[0] - p3[0], p4[1] - p3[1], p4[2] - p3[2])

        n1 = (b1[1] * b2[2] - b1[2] * b2[1], b1[2] * b2[0] - b1[0] * b2[2], b1[0] * b2[1] - b1[1] * b2[0])
        n2 = (b2[1] * b3[2] - b2[2] * b3[1], b2[2] * b3[0] - b2[0] * b3[2], b2[0] * b3[1] - b2[1] * b3[0])

        b2_len = math.sqrt(b2[0] ** 2 + b2[1] ** 2 + b2[2] ** 2)
        if b2_len == 0:
            return 0.0
        u2 = (b2[0] / b2_len, b2[1] / b2_len, b2[2] / b2_len)

        m1 = (u2[1] * n1[2] - u2[2] * n1[1], u2[2] * n1[0] - u2[0] * n1[2], u2[0] * n1[1] - u2[1] * n1[0])

        x = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
        y = m1[0] * n2[0] + m1[1] * n2[1] + m1[2] * n2[2]

        return math.degrees(math.atan2(y, x))

    def _classify_ramachandran_region(self, res_name: str, phi: float, psi: float) -> str:
        res = res_name.upper()
        if res == "GLY":
            if (-180 <= phi <= 0 and -100 <= psi <= 60) or (0 <= phi <= 180 and -60 <= psi <= 100):
                return "favored"
            if -180 <= phi <= 180 and -180 <= psi <= 180:
                return "allowed"
            return "outlier"
        elif res == "PRO":
            if -90 <= phi <= -40 and -60 <= psi <= 180:
                return "favored"
            if -110 <= phi <= -30 and -80 <= psi <= 180:
                return "allowed"
            return "outlier"
        else:
            if (-160 <= phi <= -20 and -100 <= psi <= 50) or \
               (-180 <= phi <= -45 and (45 <= psi <= 180 or -180 <= psi <= -160)) or \
               (30 <= phi <= 90 and 0 <= psi <= 90):
                return "favored"
            elif (-180 <= phi <= 0 and -120 <= psi <= 180) or (20 <= phi <= 110 and -20 <= psi <= 110):
                return "allowed"
            return "outlier"

    def _compute_ramachandran(self, pdb_path: str, target_chain: str | None) -> list[RamachandranResidue]:
        residues: dict[tuple[str, str, str], dict[str, tuple[float, float, float]]] = {}
        with open(pdb_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("ATOM  "):
                    atom_name = line[12:16].strip()
                    res_name = line[17:20].strip()
                    chain_id = line[21].strip() or "A"
                    res_seq = line[22:26].strip()
                    if target_chain and chain_id != target_chain:
                        continue
                    try:
                        x = float(line[30:38])
                        y = float(line[38:46])
                        z = float(line[46:54])
                    except ValueError:
                        continue
                    key = (chain_id, res_seq, res_name)
                    if key not in residues:
                        residues[key] = {}
                    if atom_name in ("N", "CA", "C"):
                        residues[key][atom_name] = (x, y, z)

        res_keys = list(residues.keys())
        results: list[RamachandranResidue] = []

        for i in range(len(res_keys)):
            chain, seq_id, name = res_keys[i]
            curr = residues[res_keys[i]]
            if "N" not in curr or "CA" not in curr or "C" not in curr:
                continue

            phi = None
            psi = None

            if i > 0:
                prev = residues[res_keys[i - 1]]
                if "C" in prev and res_keys[i - 1][0] == chain:
                    phi = self._calc_dihedral(prev["C"], curr["N"], curr["CA"], curr["C"])

            if i < len(res_keys) - 1:
                nxt = residues[res_keys[i + 1]]
                if "N" in nxt and res_keys[i + 1][0] == chain:
                    psi = self._calc_dihedral(curr["N"], curr["CA"], curr["C"], nxt["N"])

            if phi is not None and psi is not None:
                region = self._classify_ramachandran_region(name, phi, psi)
                results.append(
                    RamachandranResidue(
                        id=seq_id,
                        name=f"{name}{seq_id}",
                        phi=round(phi, 1),
                        psi=round(psi, 1),
                        region=region,
                    )
                )

        return results


