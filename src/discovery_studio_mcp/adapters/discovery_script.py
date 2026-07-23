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
)
from discovery_studio_mcp.security import is_safe_extension, validate_path


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
        self._perl_lib = [
            str(self._ds_root / "bin"),
            str(self._ds_root / "lib" / "5.26.1"),
            str(self._ds_root / "lib" / "vendor_perl" / "5.26.1"),
            str(self._ds_root / "lib" / "site_perl" / "5.26.1"),
        ]
        self._jobs: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        return self._perl_exe.is_file() and self._ds_root.is_dir()

    async def get_capabilities(self) -> DsCapabilities:
        capabilities = DsCapabilities(
            mock=False,
            discovery_studio_version="2020",
            discovery_studio_build="2332 20191022 1434",
            discovery_studio_root=str(self._ds_root),
            perl_version="5.26.1",
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
        dsscript_pm = self._ds_root / "lib" / "vendor_perl" / "5.26.1" / "DiscoveryScript.pm"
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
        return ""  # Requires active GUI session

    async def _run_perl_script(self, script: str, script_name: str) -> dict[str, Any]:
        """Run a Perl script using the bundled interpreter with Discovery Studio libraries."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pl", prefix=f"{script_name}_", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name

        env = os.environ.copy()
        perl_args = [
            str(self._perl_exe),
        ]
        for lib in self._perl_lib:
            if os.path.isdir(lib):
                perl_args.extend(["-I", lib])
        perl_args.extend(["-I", str(self._ds_root / "bin")])
        perl_args.append(script_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *perl_args,
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

my $infile = "{file_path.replace(chr(92), "/")}";
my $document = DiscoveryScript::Open($infile);

if (!$document) {{
    print "Error: Could not open file:\\n$infile\\n";
    exit(1);
}}

my $result = {{}};
$result->{{"format"}} = "{Path(file_path).suffix.lower().lstrip('.')}";

my @molecules;
for (my $i = 0; $i < $document->Molecules->Count; $i++) {{
    push @molecules, $document->Molecules->Item($i);
}}
$result->{{"model_count"}} = scalar(@molecules);
$result->{{"atoms"}} = $document->Atoms->Count;

my @chains;
my @ligands;
my @metals;
my $waters = 0;
my @heteros;
my $residue_count = 0;

for my $mol (@molecules) {{
    if ($mol->IsProtein) {{
        my $chains_iter = $mol->AminoAcidChains;
        while (my $chain = $chains_iter->Next) {{
            push @chains, $chain->Name;
            $residue_count += $chain->Residues->Count;
        }}
    }}
    elsif ($mol->IsLigand) {{
        push @ligands, $mol->Name;
    }}
}}

$result->{{"chains"}} = \\@chains;
$result->{{"ligands"}} = \\@ligands;
$result->{{"residues"}} = $residue_count;
$result->{{"waters"}} = $waters;
$result->{{"metals"}} = \\@metals;
$result->{{"heteroatoms"}} = \\@heteros;

use JSON;
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

my $protocolName = "{protocol_name}";
my $server = "{server_url}";

my $parameterMap = Protocol::ParameterMap::Create();
# Parameters would be set here based on protocol requirements
# This is a template - actual parameter mapping depends on the protocol

my $success = LaunchProtocol($protocolName, $parameterMap, $server);

use JSON;
my $result = {{}};
$result->{{"success"}} = $success ? JSON::true : JSON::false;
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

my $infile = "{input_path.replace(chr(92), "/")}";
my $outfile = "{output_path.replace(chr(92), "/")}";

my $document = DiscoveryScript::Open($infile);
if (!$document) {{
    print "Error: Could not open file: $infile\\n";
    exit(1);
}}

# Save in requested format
$document->Save($outfile);

use JSON;
my $result = {{}};
$result->{{"success"}} = JSON::true;
$result->{{"output"}} = $outfile;
print "__DS_JSON__:" . encode_json($result) . "\\n";
'''
