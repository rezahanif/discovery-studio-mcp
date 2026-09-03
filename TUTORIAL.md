# Discovery Studio Connection Setup Guide

## 1. Prerequisites
- BIOVIA Discovery Studio 2020 or later installed on Windows.
- AiConnect Desktop running.

## ⚠️ Host Prerequisite

**The Process Manager does not install or provide BIOVIA Discovery Studio.** Discovery Studio is commercial software from Dassault Systèmes/BIOVIA. You must have a valid installation (free tier, trial, or licensed).

## 2. No Plugin Installation Required

The connector communicates with Discovery Studio via the bundled Perl scripting API — no add-in or plugin to install. The connector reads files directly from the install directory.

## 3. Connect in AiConnect Desktop

1. Open **AiConnect Desktop** → **MCP Collection**.
2. Find **Discovery Studio Connector** and click **Enable**.

## 4. Verify Connection

Check the adapter status:
```
Get Discovery Studio capabilities and check what's available.
```

## 5. Start Working

The connector provides **26 tools** covering the complete computational structural biology lifecycle:

### Structural Biology & Protein Engineering Primitives (Local / Offline)
- `ds_evaluate_mutant` — all-in-one in-silico point mutation, sequence alignment, 3D superposition, and Ramachandran validation macro (~500 tokens).
- `ds_extract_sequence` — extract FASTA sequence from 3D PDB/MOL structures (supports `compact` mode to save tokens).
- `ds_mutate_residue` — perform in-silico single amino-acid point mutations with side-chain repacking and protonation at pH 7.4.
- `ds_align_sequences` — pairwise Needleman-Wunsch global protein sequence alignment with identity % and similarity %.
- `ds_superimpose_structures` — superimpose 3D protein coordinates and calculate C-alpha, mainchain, and all-atom RMSD (Å).
- `ds_calculate_ramachandran` — calculate backbone Phi/Psi dihedral angles and classify residues into Favored, Allowed, and Outlier regions (supports `compact` mode).
- `ds_analyze_interface` — detect inter-chain contact residues, calculate hydrogen bonds, and flag steric clashes (supports `compact` mode).

### Receptor Preparation & Binding Pocket Pipeline
1. **Triage**: `ds_inspect_structure` — analyze file format, chains, residues, ligands, waters, and atom counts.
2. **Preparation**: `ds_prepare_structure` — clean protein, add missing hydrogens at physiological pH (7.4), and strip crystallographic waters.
3. **Cavity Detection**: `ds_analyze_binding_site` — detect binding pockets, calculate cavity volume in $\text{Å}^3$, and find active site coordinates.
4. **Visual Verification**: `ds_view_in_gui` — dispatch structure directly to active Discovery Studio desktop window, set 3D styles (ribbon, ball & stick, CPK), and capture a rendered PNG snapshot.

### Workspace & Interactive Observability
- `ds_get_active_workspace` — inspect currently open Discovery Studio session, active molecule name, and atom counts.
- `ds_render_structure` — render molecular structure to a high-resolution PNG image.
- `ds_validate_structure` — check fitness for specific workflows (docking, simulation, etc.).
- `ds_convert_structure` — convert between formats (PDB, MOL, MOL2, SDF, XYZ).

### Protocol Management (Enterprise Pipeline Pilot Server)
> [!NOTE]
> These protocol tools require an enterprise Pipeline Pilot Server cluster. All 7 structural biology & protein engineering tools above run completely offline on your local machine.
- `ds_list_protocols` — list available Discovery Studio protocols
- `ds_describe_protocol` — get protocol parameters and requirements
- `ds_run_protocol` — execute a protocol with parameters
- `ds_list_jobs` — list recent and active jobs
- `ds_get_job_status` — check job progress
- `ds_cancel_job` — cancel a running job

### API Guidance (Layer B)
- `ds_search_api` — search the Discovery Studio scripting API by keyword
- `ds_function_registry` — look up specific API functions and signatures
- `ds_list_api_categories` — browse API packages by domain

### Example Agent Prompts

```
1. Inspect 1TPO.pdb, clean it at pH 7.4, and strip water molecules.
```

```
2. Detect binding cavities in the prepared receptor and calculate their volume in A^3.
```

```
3. Show the protein in Discovery Studio with flat ribbons colored by secondary structure, and capture a preview image.
```

```
4. Check what document is currently active in the running Discovery Studio window.
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DS_MOCK_MODE` | `false` | Enable mock adapter for testing |
| `DS_ALLOWED_INPUT_DIRS` | `Documents, Workspace, DS_ROOT` | Whitelisted directories for structure loading |
| `DS_PIPELINE_PILOT_URL` | (unconfigured) | Enterprise Pipeline Pilot Server URL for protocols |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Adapter not available` | Discovery Studio not installed or not found. Check `DS_ROOT`. |
| `Pipeline Pilot unconfigured` | Protocol tools (`ds_run_protocol`) require Pipeline Pilot Server. Local 4-stage pipeline works standalone. |
| `Active GUI not responding` | Ensure `DiscoveryStudio2025.exe` is running on your desktop before calling `ds_view_in_gui`. |

