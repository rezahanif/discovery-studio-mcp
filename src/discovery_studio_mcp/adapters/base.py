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
    PrepareStructureRequest,
    PrepareStructureResult,
    BindingSiteAnalysisResult,
    ViewInGuiRequest,
    ViewInGuiResult,
    ActiveWorkspaceResult,
    ExtractSequenceRequest,
    ExtractSequenceResult,
    MutateResidueRequest,
    MutateResidueResult,
    AnalyzeInterfaceRequest,
    AnalyzeInterfaceResult,
    SuperimposeStructuresRequest,
    SuperimposeStructuresResult,
    AlignSequencesRequest,
    AlignSequencesResult,
    CalculateRamachandranRequest,
    CalculateRamachandranResult,
    EvaluateMutantRequest,
    EvaluateMutantResult,
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

    async def prepare_structure(self, request: PrepareStructureRequest) -> PrepareStructureResult:
        """Clean protein, add hydrogens at specified pH, and optionally strip waters."""
        raise NotImplementedError

    async def analyze_binding_site(
        self, file_path: str, grid_resolution: float = 0.5, site_opening: float = 4.0
    ) -> BindingSiteAnalysisResult:
        """Detect binding pockets / cavities and compute volumes in Angstroms^3."""
        raise NotImplementedError

    async def view_in_gui(self, request: ViewInGuiRequest) -> ViewInGuiResult:
        """Dispatch structure and visual display styles directly to the active Discovery Studio window."""
        raise NotImplementedError

    async def get_active_workspace(self) -> ActiveWorkspaceResult:
        """Query state and active documents of the running Discovery Studio GUI."""
        raise NotImplementedError

    async def extract_sequence(self, request: ExtractSequenceRequest) -> ExtractSequenceResult:
        """Extract protein sequence (FASTA format and per-residue breakdown) from a structure."""
        raise NotImplementedError

    async def mutate_residue(self, request: MutateResidueRequest) -> MutateResidueResult:
        """Introduce an in-silico single amino-acid point mutation and repack sidechains."""
        raise NotImplementedError

    async def analyze_interface(self, request: AnalyzeInterfaceRequest) -> AnalyzeInterfaceResult:
        """Analyze contacts, hydrogen bonds, and steric clashes between two protein chains."""
        raise NotImplementedError

    async def superimpose_structures(self, request: SuperimposeStructuresRequest) -> SuperimposeStructuresResult:
        """Superimpose two protein 3D structures and calculate RMSD (All-Atom, Backbone, C-Alpha)."""
        raise NotImplementedError

    async def align_sequences(self, request: AlignSequencesRequest) -> AlignSequencesResult:
        """Perform pairwise protein sequence alignment and compute identity/similarity percentages."""
        raise NotImplementedError

    async def calculate_ramachandran(self, request: CalculateRamachandranRequest) -> CalculateRamachandranResult:
        """Calculate per-residue Phi/Psi backbone dihedral angles and classify Ramachandran regions."""
        raise NotImplementedError

    async def evaluate_mutant(self, request: EvaluateMutantRequest) -> EvaluateMutantResult:
        """All-in-one general-purpose in-silico mutation, alignment, superposition, and stereochemical evaluation."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this adapter is available in the current environment."""
        return True

