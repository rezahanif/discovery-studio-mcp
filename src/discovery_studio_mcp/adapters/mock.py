"""Mock adapter for development and testing without Discovery Studio."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from discovery_studio_mcp.adapters.base import DiscoveryStudioAdapter
from discovery_studio_mcp.models import (
    AdapterInfo,
    AdapterStatus,
    CapabilityStatus,
    DsCapabilities,
    HealthCheckResult,
    JobResult,
    JobStatus,
    ProtocolInfo,
    ProtocolDescription,
    ProtocolParameter,
    RunProtocolRequest,
    RenderStructureRequest,
    StructureInspection,
    ConvertStructureRequest,
)


class MockAdapter(DiscoveryStudioAdapter):
    """Mock adapter that returns synthetic data for testing. All responses are marked mock=True."""

    adapter_name = "mock"

    async def get_capabilities(self) -> DsCapabilities:
        return DsCapabilities(
            mock=True,
            discovery_studio_version="2020 (mock)",
            discovery_studio_build="mock-2332",
            discovery_studio_root="/mock/ds",
            available_adapters=[
                AdapterInfo(
                    name="mock",
                    status=AdapterStatus.CONFIRMED,
                    description="Mock adapter for development and testing",
                    version="0.1.0",
                    limitations=["All results are synthetic"],
                ),
                AdapterInfo(
                    name="discovery_script",
                    status=AdapterStatus.NOT_FOUND,
                    description="DiscoveryScript adapter via Perl",
                    limitations=["Not available in mock mode"],
                ),
                AdapterInfo(
                    name="filesystem",
                    status=AdapterStatus.CONFIRMED,
                    description="Filesystem operations for structure file handling",
                    version="0.1.0",
                ),
                AdapterInfo(
                    name="pipeline_pilot",
                    status=AdapterStatus.NOT_FOUND,
                    description="Pipeline Pilot protocol execution",
                    limitations=["Requires Pipeline Pilot Server license"],
                ),
                AdapterInfo(
                    name="ui_fallback",
                    status=AdapterStatus.NOT_APPLICABLE,
                    description="UI automation fallback - disabled by default",
                    limitations=["Disabled in mock mode"],
                ),
            ],
            pipeline_pilot_available=False,
            discovery_script_available=False,
            supported_formats=["pdb", "mol", "mol2", "sdf", "sd", "msv", "dsv", "cif", "xyz", "smi"],
            license_mode="mock",
            max_concurrent_jobs=1,
            job_timeout_seconds=3600,
            ui_fallback_enabled=False,
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            mock=True,
            status="ok",
            checks=[
                {"component": "mock_adapter", "status": "available"},
                {"component": "discovery_studio", "status": "mock_mode"},
                {"component": "pipeline_pilot", "status": "unavailable"},
                {"component": "perl_executable", "status": "mock_mode"},
            ],
            issues=["Mock mode is active - no real operations performed"],
            recommendations=[
                "Set DS_MOCK_MODE=false and configure DS_HOME to connect to real Discovery Studio",
                "Configure DS_PIPELINE_PILOT_URL to enable protocol execution",
            ],
        )

    async def inspect_structure(self, file_path: str) -> StructureInspection:
        return StructureInspection(
            mock=True,
            file_path=file_path,
            format=file_path.rsplit(".", 1)[-1] if "." in file_path else "unknown",
            model_count=1,
            chains=["A", "B"],
            residues=246,
            atoms=1964,
            ligands=["LIG1", "SO4"],
            waters=42,
            metals=["ZN"],
            heteroatoms=["PO4"],
            warnings=["Mock mode: file was not actually inspected"],
        )

    async def list_protocols(self) -> list[ProtocolInfo]:
        return [
            ProtocolInfo(
                name="Prepare Protein",
                description="Prepare protein structure for docking",
                category="Protein Preparation",
                required_parameters=["Input Protein", "pH"],
                requires_server=True,
            ),
            ProtocolInfo(
                name="Minimize",
                description="Minimize molecular structure energy",
                category="Energy",
                required_parameters=["Input Typed Molecule"],
                requires_server=True,
            ),
            ProtocolInfo(
                name="Dock Ligands (CDOCKER)",
                description="Dock ligands to a protein binding site",
                category="Docking",
                required_parameters=["Input Receptor", "Input Ligands", "Input Site Sphere"],
                requires_server=True,
                requires_license=True,
            ),
            ProtocolInfo(
                name="Calculate Energy",
                description="Calculate molecular energy using force field",
                category="Energy",
                required_parameters=["Input Typed Molecule"],
                requires_server=True,
            ),
        ]

    async def describe_protocol(self, protocol_name: str) -> ProtocolDescription:
        mock_protocols: dict[str, ProtocolDescription] = {
            "Prepare Protein": ProtocolDescription(
                name="Prepare Protein",
                description="Prepare protein structure for docking",
                category="Protein Preparation",
                parameters=[
                    ProtocolParameter(name="Input Protein", type="Molecule", required=True,
                                      description="Protein structure to prepare"),
                    ProtocolParameter(name="pH", type="Real", required=False, default_value="7.4",
                                      description="pH for protonation"),
                ],
                requires_server=True,
            ),
            "Dock Ligands (CDOCKER)": ProtocolDescription(
                name="Dock Ligands (CDOCKER)",
                description="Dock ligands using CDOCKER algorithm",
                category="Docking",
                parameters=[
                    ProtocolParameter(name="Input Receptor", type="Molecule", required=True),
                    ProtocolParameter(name="Input Ligands", type="Molecule", required=True),
                    ProtocolParameter(name="Input Site Sphere", type="Sphere", required=True),
                    ProtocolParameter(name="Pose Cluster Radius", type="Real", required=False, default_value="0.5"),
                ],
                requires_server=True,
                requires_license=True,
            ),
        }
        if protocol_name in mock_protocols:
            return mock_protocols[protocol_name]
        return ProtocolDescription(
            name=protocol_name,
            description=f"Protocol '{protocol_name}' - mock description",
            parameters=[],
            requires_server=True,
        )

    async def run_protocol(self, request: RunProtocolRequest) -> JobResult:
        job_id = f"mock-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        return JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            submitted_at=now,
            completed_at=now,
            progress=100.0,
            status_message="Mock protocol completed successfully",
            warnings=["Mock mode: protocol was not actually executed"],
        )

    async def get_job_status(self, job_id: str) -> JobResult:
        return JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=100.0,
            status_message="Mock job status",
        )

    async def cancel_job(self, job_id: str) -> bool:
        return True

    async def list_jobs(self) -> list[JobResult]:
        return []

    async def convert_structure(self, request: ConvertStructureRequest) -> str:
        return f"mock-output.{request.output_format}"

    async def render_structure(self, request: RenderStructureRequest) -> str:
        return f"mock-render-{uuid.uuid4().hex[:8]}.{request.output_format}"
