"""Mock adapter for development and testing without Discovery Studio."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

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
    PrepareStructureRequest,
    PrepareStructureResult,
    BindingSiteAnalysisResult,
    BindingSiteInfo,
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

    async def prepare_structure(self, request: PrepareStructureRequest) -> PrepareStructureResult:
        out = request.output_path or f"prepared_{Path(request.input_path).name}"
        return PrepareStructureResult(
            mock=True,
            input_path=request.input_path,
            output_path=out,
            ph=request.ph,
            initial_atoms=1500,
            final_atoms=1650,
            hydrogens_added=150,
            waters_removed=0 if request.keep_waters else 45,
            formal_charge=-2.0,
            status="prepared",
            warnings=["Mock mode: structure was not actually modified"],
        )

    async def analyze_binding_site(
        self, file_path: str, grid_resolution: float = 0.5, site_opening: float = 4.0
    ) -> BindingSiteAnalysisResult:
        return BindingSiteAnalysisResult(
            mock=True,
            file_path=file_path,
            site_count=2,
            sites=[
                BindingSiteInfo(
                    site_id=1,
                    name="Site_1",
                    center=[12.5, 34.2, -5.8],
                    volume_angstrom3=485.6,
                    point_count=388,
                    lining_residues=["HIS57", "ASP102", "SER195"],
                ),
                BindingSiteInfo(
                    site_id=2,
                    name="Site_2",
                    center=[20.1, 15.4, 2.1],
                    volume_angstrom3=210.4,
                    point_count=168,
                    lining_residues=["TYR20", "PHE35", "TRP40"],
                ),
            ],
            grid_resolution_angstrom=grid_resolution,
            method="cavity_detection",
            warnings=["Mock mode: synthetic cavity data"],
        )

    async def view_in_gui(self, request: ViewInGuiRequest) -> ViewInGuiResult:
        return ViewInGuiResult(
            mock=True,
            success=True,
            document_name="Mock Molecule Window",
            file_path=request.file_path or "mock_active.pdb",
            display_style=request.display_style,
            color_scheme=request.color_scheme,
            snapshot_image_path=request.snapshot_path or "mock_preview.png",
            message="Mock GUI view updated successfully",
        )

    async def get_active_workspace(self) -> ActiveWorkspaceResult:
        return ActiveWorkspaceResult(
            mock=True,
            is_gui_running=True,
            process_id=12345,
            has_active_document=True,
            document_name="1TPO.pdb",
            document_path="C:/Mock/1TPO.pdb",
            model_count=1,
            atom_count=1714,
            selected_count=0,
            message="Mock active workspace",
        )

    async def extract_sequence(self, request: ExtractSequenceRequest) -> ExtractSequenceResult:
        mock_seq = "IVGGYTCGANTVPYQVSLNSGYHFCGGSLINSQWVVSAAHCYKSGIQVRLGEDNINVVEGNEQFISASKSIVHPSYNSNTLNNDIMLIKLKSAASLNSRVASISLPTSCASAGTQCLISGWGNTKSSGTSYPDVLKCLKAPILSDSSCKSAYPGQITSNMFCAGYLEGGKDSCQGDSGGPVVCSGKLQGIVSWGSGCAQKNKPGVYTKVCNYVSWIKQTIASN"
        chain_a = ChainSequence(
            chain_id=request.chain_id or "A",
            length=len(mock_seq),
            fasta_sequence=mock_seq,
            residues=[] if request.compact else [ResidueInfo(id=str(i + 16), name=f"{mock_seq[i]}{i+16}", symbol=mock_seq[i]) for i in range(len(mock_seq))],
        )
        return ExtractSequenceResult(
            mock=True,
            file_path=request.file_path,
            total_residues=len(mock_seq),
            chains=[chain_a],
            fasta_formatted=f">Chain_{chain_a.chain_id}\n{mock_seq}\n",
        )

    async def mutate_residue(self, request: MutateResidueRequest) -> MutateResidueResult:
        out = request.output_path or f"mutant_{request.residue_id}_{request.target_amino_acid}.pdb"
        return MutateResidueResult(
            mock=True,
            success=True,
            input_path=request.file_path,
            output_path=out,
            chain_id=request.chain_id or "A",
            residue_id=request.residue_id,
            original_residue=f"ILE{request.residue_id}",
            mutated_residue=f"{request.target_amino_acid.upper()}{request.residue_id}",
            repacked=request.repack_and_clean,
            atom_count=3280,
            message=f"Mutated residue {request.residue_id} to {request.target_amino_acid} successfully",
        )

    async def analyze_interface(self, request: AnalyzeInterfaceRequest) -> AnalyzeInterfaceResult:
        return AnalyzeInterfaceResult(
            mock=True,
            file_path=request.file_path,
            chain_1=request.chain_1,
            chain_2=request.chain_2,
            contact_residues_chain_1=["HIS57", "ASP102", "SER195", "TRP215"],
            contact_residues_chain_2=["LYS15", "ARG17", "ILE19"],
            total_contacts=14,
            hydrogen_bonds=[] if request.compact else [
                InterfaceHBond(donor=f"{request.chain_1}:SER195:OG", acceptor=f"{request.chain_2}:LYS15:NZ", distance_angstrom=2.85),
                InterfaceHBond(donor=f"{request.chain_1}:HIS57:NE2", acceptor=f"{request.chain_2}:ARG17:NH1", distance_angstrom=3.10),
            ],
            clashes=[],
            interface_summary=f"Found 14 contacts, 2 hydrogen bonds, and 0 clashes between Chain {request.chain_1} and Chain {request.chain_2}.",
        )

    async def superimpose_structures(self, request: SuperimposeStructuresRequest) -> SuperimposeStructuresResult:
        out = request.output_path or f"superimposed_{Path(request.target_path).name}"
        return SuperimposeStructuresResult(
            mock=True,
            reference_path=request.reference_path,
            target_path=request.target_path,
            rmsd_all_atom=1.12,
            rmsd_calpha=0.42,
            rmsd_mainchain=0.58,
            aligned_atoms=1640,
            superimposed_output_path=out,
            summary="Mock superposition: C-alpha RMSD = 0.42 Å, Mainchain RMSD = 0.58 Å, All-atom RMSD = 1.12 Å across 1640 atoms.",
        )

    async def align_sequences(self, request: AlignSequencesRequest) -> AlignSequencesResult:
        s1 = request.sequence_1.strip().upper()
        s2 = request.sequence_2.strip().upper()
        min_l = min(len(s1), len(s2))
        matches = sum(1 for i in range(min_l) if s1[i] == s2[i])
        ident = (matches / max(len(s1), len(s2))) * 100 if max(len(s1), len(s2)) > 0 else 100.0
        return AlignSequencesResult(
            mock=True,
            name_1=request.name_1,
            name_2=request.name_2,
            identity_percentage=round(ident, 2),
            similarity_percentage=round(min(ident + 1.5, 100.0), 2),
            alignment_score=float(matches * 2 - (max(len(s1), len(s2)) - matches)),
            aligned_length=max(len(s1), len(s2)),
            matches=matches,
            mismatches=max(len(s1), len(s2)) - matches,
            gaps=abs(len(s1) - len(s2)),
            alignment_view=f">{request.name_1}\n{s1[:60]}...\n>{request.name_2}\n{s2[:60]}...",
            summary=f"Pairwise alignment ({request.algorithm}): {round(ident, 2)}% identity across {max(len(s1), len(s2))} residues.",
        )

    async def calculate_ramachandran(self, request: CalculateRamachandranRequest) -> CalculateRamachandranResult:
        return CalculateRamachandranResult(
            mock=True,
            file_path=request.file_path,
            total_evaluated=223,
            favored_count=214,
            favored_percentage=95.96,
            allowed_count=8,
            allowed_percentage=3.59,
            outlier_count=1,
            outlier_percentage=0.45,
            outlier_residues=["GLY142"],
            plot_image_path=request.plot_output_path or "ramachandran_plot.png" if request.generate_plot_image else None,
            residues=[] if request.compact else [
                RamachandranResidue(id="16", name="ILE16", phi=-65.4, psi=-42.1, region="favored"),
                RamachandranResidue(id="17", name="VAL17", phi=-118.2, psi=135.6, region="favored"),
                RamachandranResidue(id="142", name="GLY142", phi=82.0, psi=-15.0, region="outlier"),
            ],
            summary="Ramachandran stereochemical assessment: 95.96% favored (214), 3.59% allowed (8), 0.45% outliers (1: GLY142).",
        )

    async def evaluate_mutant(self, request: EvaluateMutantRequest) -> EvaluateMutantResult:
        out = request.output_path or f"mutant_{request.residue_id}_{request.target_amino_acid}.pdb"
        return EvaluateMutantResult(
            mock=True,
            input_file=request.file_path,
            output_file=out,
            mutation=f"ILE{request.residue_id} -> {request.target_amino_acid.upper()}{request.residue_id}",
            sequence_identity=99.55,
            sequence_similarity=100.0,
            rmsd_calpha=0.04,
            rmsd_mainchain=0.06,
            rmsd_all_atom=0.12,
            ramachandran_favored_percentage=92.76,
            ramachandran_allowed_percentage=6.79,
            ramachandran_outlier_count=1,
            outlier_residues=["ASN115"],
            verdict="WELL-TOLERATED",
            summary=f"Mutation ILE{request.residue_id} -> {request.target_amino_acid.upper()}{request.residue_id} is WELL-TOLERATED: C-alpha RMSD = 0.04 Å, 99.55% allowed Ramachandran geometry, 0 new steric clashes.",
        )

