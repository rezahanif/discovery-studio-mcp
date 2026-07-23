"""Abstract base adapter for Discovery Studio automation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from discovery_studio_mcp.models import (
    DsCapabilities,
    HealthCheckResult,
    StructureInspection,
    ProtocolInfo,
    ProtocolDescription,
    ProtocolParameter,
    RunProtocolRequest,
    JobResult,
    ConvertStructureRequest,
    RenderStructureRequest,
    CapabilityStatus,
)


class DiscoveryStudioAdapter(ABC):
    """Abstract interface for Discovery Studio automation adapters."""

    adapter_name: str = "base"

    @abstractmethod
    async def get_capabilities(self) -> DsCapabilities:
        """Return what capabilities are available through this adapter."""

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        """Perform a safety check of the environment."""

    @abstractmethod
    async def inspect_structure(self, file_path: str) -> StructureInspection:
        """Inspect a molecular structure file and return its properties."""

    @abstractmethod
    async def list_protocols(self) -> list[ProtocolInfo]:
        """List all available protocols."""

    @abstractmethod
    async def describe_protocol(self, protocol_name: str) -> ProtocolDescription:
        """Get detailed information about a protocol."""

    @abstractmethod
    async def run_protocol(self, request: RunProtocolRequest) -> JobResult:
        """Run a protocol and return a job result."""

    @abstractmethod
    async def get_job_status(self, job_id: str) -> JobResult:
        """Get the current status of a job."""

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""

    @abstractmethod
    async def list_jobs(self) -> list[JobResult]:
        """List recent jobs."""

    @abstractmethod
    async def convert_structure(self, request: ConvertStructureRequest) -> str:
        """Convert a structure between formats."""

    @abstractmethod
    async def render_structure(self, request: RenderStructureRequest) -> str:
        """Render a structure to an image."""

    def is_available(self) -> bool:
        """Check if this adapter is available in the current environment."""
        return True
