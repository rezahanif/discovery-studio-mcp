"""Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class AdapterStatus(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    NOT_FOUND = "not_found"
    REQUIRES_LICENSE = "requires_license"
    REQUIRES_MANUAL_CHECK = "requires_manual_check"
    NOT_APPLICABLE = "not_applicable"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class AdapterInfo(BaseModel):
    name: str
    status: AdapterStatus
    description: str
    version: str | None = None
    limitations: list[str] = Field(default_factory=list)


class DsCapabilities(BaseModel):
    mock: bool = False
    discovery_studio_version: str
    discovery_studio_build: str
    discovery_studio_root: str
    perl_version: str | None = None
    available_adapters: list[AdapterInfo] = Field(default_factory=list)
    pipeline_pilot_available: bool = False
    pipeline_pilot_server: str | None = None
    discovery_script_available: bool = False
    supported_formats: list[str] = Field(default_factory=list)
    license_mode: str | None = None
    max_concurrent_jobs: int = 1
    job_timeout_seconds: int = 3600
    ui_fallback_enabled: bool = False


class StructureInspection(BaseModel):
    mock: bool = False
    file_path: str
    format: str | None = None
    model_count: int = 0
    chains: list[str] = Field(default_factory=list)
    residues: int = 0
    atoms: int = 0
    ligands: list[str] = Field(default_factory=list)
    waters: int = 0
    metals: list[str] = Field(default_factory=list)
    heteroatoms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProtocolInfo(BaseModel):
    name: str
    description: str
    category: str | None = None
    required_parameters: list[str] = Field(default_factory=list)
    optional_parameters: list[str] = Field(default_factory=list)
    requires_server: bool = True
    requires_license: bool | None = None


class ProtocolParameter(BaseModel):
    name: str
    type: str
    required: bool = False
    default_value: str | None = None
    description: str | None = None


class ProtocolDescription(BaseModel):
    name: str
    description: str
    category: str | None = None
    parameters: list[ProtocolParameter] = Field(default_factory=list)
    requires_server: bool = True
    requires_license: bool | None = None


class RunProtocolRequest(BaseModel):
    protocol_name: str
    parameters: dict[str, str] = Field(default_factory=dict)
    input_files: list[str] = Field(default_factory=list)
    confirm_destructive_action: bool = False


class ConvertStructureRequest(BaseModel):
    input_path: str
    output_format: str
    output_path: str | None = None


class RenderStructureRequest(BaseModel):
    molecule_path: str
    representation: str = "ball_and_stick"
    width: int = 800
    height: int = 600
    output_format: str = "png"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    status_message: str | None = None
    result_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    manifest_path: str | None = None


class HealthCheckResult(BaseModel):
    mock: bool = False
    status: str = "unknown"
    checks: list[dict[str, str]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PrepareStructureRequest(BaseModel):
    input_path: str
    output_path: str | None = None
    ph: float = 7.4
    keep_waters: bool = False
    standardize_names: bool = True


class PrepareStructureResult(BaseModel):
    mock: bool = False
    input_path: str
    output_path: str
    ph: float = 7.4
    initial_atoms: int = 0
    final_atoms: int = 0
    hydrogens_added: int = 0
    waters_removed: int = 0
    formal_charge: float = 0.0
    status: str = "prepared"
    warnings: list[str] = Field(default_factory=list)


class BindingSiteInfo(BaseModel):
    site_id: int
    name: str = ""
    center: list[float] = Field(default_factory=list)
    volume_angstrom3: float = 0.0
    point_count: int = 0
    lining_residues: list[str] = Field(default_factory=list)


class BindingSiteAnalysisResult(BaseModel):
    mock: bool = False
    file_path: str
    site_count: int = 0
    sites: list[BindingSiteInfo] = Field(default_factory=list)
    grid_resolution_angstrom: float = 0.5
    method: str = "cavity_detection"
    warnings: list[str] = Field(default_factory=list)


class ViewInGuiRequest(BaseModel):
    file_path: str | None = None
    display_style: str = "ribbon_flat"
    color_scheme: str = "secondary"
    rotate_x: float = 0.0
    rotate_y: float = 0.0
    capture_snapshot: bool = True
    snapshot_path: str | None = None


class ViewInGuiResult(BaseModel):
    mock: bool = False
    success: bool = True
    document_name: str = ""
    file_path: str = ""
    display_style: str = ""
    color_scheme: str = ""
    snapshot_image_path: str | None = None
    message: str = ""


class ActiveWorkspaceResult(BaseModel):
    mock: bool = False
    is_gui_running: bool = False
    process_id: int | None = None
    has_active_document: bool = False
    document_name: str | None = None
    document_path: str | None = None
    model_count: int = 0
    atom_count: int = 0
    selected_count: int = 0
    message: str = ""


class ResidueInfo(BaseModel):
    id: str
    name: str
    symbol: str


class ChainSequence(BaseModel):
    chain_id: str
    length: int
    fasta_sequence: str
    residues: list[ResidueInfo] = []


class ExtractSequenceRequest(BaseModel):
    file_path: str
    chain_id: str | None = None
    compact: bool = True


class ExtractSequenceResult(BaseModel):
    mock: bool = False
    file_path: str
    total_residues: int = 0
    chains: list[ChainSequence] = []
    fasta_formatted: str = ""


class MutateResidueRequest(BaseModel):
    file_path: str
    chain_id: str | None = None
    residue_id: str
    target_amino_acid: str
    repack_and_clean: bool = True
    output_path: str | None = None


class MutateResidueResult(BaseModel):
    mock: bool = False
    success: bool = True
    input_path: str = ""
    output_path: str = ""
    chain_id: str = ""
    residue_id: str = ""
    original_residue: str = ""
    mutated_residue: str = ""
    repacked: bool = True
    atom_count: int = 0
    message: str = ""


class InterfaceHBond(BaseModel):
    donor: str
    acceptor: str
    distance_angstrom: float = 0.0


class InterfaceClash(BaseModel):
    atom_1: str
    atom_2: str
    overlap_angstrom: float = 0.0


class AnalyzeInterfaceRequest(BaseModel):
    file_path: str
    chain_1: str = "A"
    chain_2: str = "B"
    contact_cutoff_angstrom: float = 4.5
    compact: bool = True


class AnalyzeInterfaceResult(BaseModel):
    mock: bool = False
    file_path: str
    chain_1: str
    chain_2: str
    contact_residues_chain_1: list[str] = []
    contact_residues_chain_2: list[str] = []
    total_contacts: int = 0
    hydrogen_bonds: list[InterfaceHBond] = []
    clashes: list[InterfaceClash] = []
    interface_summary: str = ""


# --- Superposition & RMSD Models ---
class SuperimposeStructuresRequest(BaseModel):
    reference_path: str
    target_path: str
    align_by: str = "calpha"
    output_path: str | None = None


class SuperimposeStructuresResult(BaseModel):
    mock: bool = False
    reference_path: str
    target_path: str
    rmsd_all_atom: float = 0.0
    rmsd_calpha: float = 0.0
    rmsd_mainchain: float = 0.0
    aligned_atoms: int = 0
    superimposed_output_path: str | None = None
    summary: str = ""


# --- Sequence Alignment Models ---
class AlignSequencesRequest(BaseModel):
    sequence_1: str
    sequence_2: str
    name_1: str = "Seq1"
    name_2: str = "Seq2"
    algorithm: str = "needleman_wunsch"


class AlignSequencesResult(BaseModel):
    mock: bool = False
    name_1: str
    name_2: str
    identity_percentage: float
    similarity_percentage: float
    alignment_score: float
    aligned_length: int
    matches: int
    mismatches: int
    gaps: int
    alignment_view: str = ""
    summary: str = ""


# --- Ramachandran Stereochemistry Models ---
class RamachandranResidue(BaseModel):
    id: str
    name: str
    phi: float
    psi: float
    region: str  # "favored", "allowed", "outlier"


class CalculateRamachandranRequest(BaseModel):
    file_path: str
    chain_id: str | None = None
    generate_plot_image: bool = False
    plot_output_path: str | None = None
    compact: bool = True


class CalculateRamachandranResult(BaseModel):
    mock: bool = False
    file_path: str
    total_evaluated: int
    favored_count: int
    favored_percentage: float
    allowed_count: int
    allowed_percentage: float
    outlier_count: int
    outlier_percentage: float
    outlier_residues: list[str] = []
    plot_image_path: str | None = None
    residues: list[RamachandranResidue] = []
    summary: str = ""


# --- Bundled Structural Biology Macro-Workflow ---
class EvaluateMutantRequest(BaseModel):
    file_path: str
    residue_id: str
    target_amino_acid: str
    chain_id: str | None = "A"
    repack_and_clean: bool = True
    output_path: str | None = None
    compact: bool = True


class EvaluateMutantResult(BaseModel):
    mock: bool = False
    input_file: str
    output_file: str
    mutation: str
    sequence_identity: float
    sequence_similarity: float
    rmsd_calpha: float
    rmsd_mainchain: float
    rmsd_all_atom: float
    ramachandran_favored_percentage: float
    ramachandran_allowed_percentage: float
    ramachandran_outlier_count: int
    outlier_residues: list[str] = []
    verdict: str
    summary: str



