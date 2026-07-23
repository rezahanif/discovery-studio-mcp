# Discovery Studio Agent Skill

## When to Use This Skill

Use this Skill when the user requests:
- Molecular structure analysis or inspection
- Protein-ligand docking
- Protein preparation (protonation, cleaning, forcefield typing)
- Ligand preparation
- Binding site definition
- Structure-based drug design operations
- Structure file format conversion
- Any task requiring BIOVIA Discovery Studio

## Core Workflow Principles

### 1. Always Check Capabilities First

Before any operation, call `ds_get_capabilities`. This tells you:
- Whether Discovery Studio is available
- Which adapters are active (DiscoveryScript, Pipeline Pilot, Filesystem)
- What formats are supported
- Whether protocol execution is possible (requires Pipeline Pilot Server)

### 2. Always Inspect Structures First

Before docking or any computation, call `ds_inspect_structure` on every input file.
Check:
- Is there a protein? (chains present)
- Are there ligands?
- How many waters? (may need removal)
- Are there metals or cofactors? (may need special handling)
- Are there missing atoms or residues?

### 3. Don't Skip Protein Preparation

For docking workflows, protein preparation is ESSENTIAL:
- Missing atoms must be added
- Hydrogen atoms must be added
- Protonation states must be set (pH-dependent)
- Forcefield typing must be applied (usually CHARMm)
- Never dock into an unprepared protein

### 4. Don't Skip Ligand Preparation

Ligands must be:
- Clean (proper bond orders, valences)
- Ionized at appropriate pH
- Energy minimized or at least have reasonable geometry
- Check for duplicate structures

### 5. Handle Water, Metals, Cofactors

Water molecules:
- Usually should be removed for docking (unless crystallographic water is essential)
- Some protocols allow keeping specific waters

Metals:
- Check for Zn, Mg, Ca, Fe, Mn in the active site
- May affect forcefield typing
- May need special parameters

Cofactors and native ligands:
- Should usually be kept if they are part of the biological system
- Remove only if they are artifacts

### 6. Binding Site Definition

The binding site determines where docking happens. Options:
- From co-crystallized ligand position (best)
- From known active site residues
- From cavity detection
- Never use arbitrary coordinates without justification

### 7. Choosing a Docking Protocol

Discovery Studio provides multiple docking methods:
- **CDOCKER**: CHARMm-based MD simulated annealing. Good accuracy, moderate speed.
- **LigandFit**: Shape-based with Monte Carlo search. Faster, good for screening.

Choose based on:
- Number of ligands (screening vs. detailed study)
- Quality requirements
- Available license

### 8. Interpreting Scores

IMPORTANT: Docking scores are COMPUTATIONAL estimates, NOT experimental binding energies.

- **-CDOCKER_ENERGY**: CHARMm interaction energy (lower is better)
- **-CDOCKER_INTERACTION_ENERGY**: Ligand-receptor interaction (lower is better)
- These scores RANK poses, not PREDICT absolute affinity
- Score differences < 1-2 units are usually not significant

Always phrase results as:
- "The top-ranked pose has a CDOCKER energy of X"
- NOT "The binding energy is X"

### 9. Always Check Warnings

After any job:
- Call `ds_get_job_status` to check for warnings
- Look for: "Failed to type", "Missing parameters", "Atom type not found"
- Report warnings to the user even if the job "completed"

### 10. Reproducibility

Every job creates a manifest. Always reference the job_id in your answers.
The manifest at `workspace/jobs/<job_id>/manifest.json` contains everything
needed to reproduce the result.

## Standard Agent Workflow: Docking

```
User: "Dock these 5 ligands into my protein"

1. ds_get_capabilities
   -> Check docking protocols available
   -> Confirm Pipeline Pilot connection

2. ds_inspect_structure(protein.pdb)
   -> Count chains, residues, waters, metals, ligands
   -> Report findings to user

3. ds_validate_structure(protein.pdb, workflow="docking")
   -> Check for issues

4. For each ligand file, ds_inspect_structure(ligand.sdf)

5. Ask user about:
   - pH for protonation (typically 7.4)
   - Whether to keep crystallographic waters
   - Whether to keep cofactors
   - Binding site definition (if not from co-crystal)

6. ds_run_protocol("Prepare Protein", {
     "Input Protein": protein.pdb,
     "pH": "7.4"
   })

7. ds_run_protocol("Dock Ligands (CDOCKER)", {
     "Input Receptor": prepared_protein.dsv,
     "Input Ligands": ligands.sdf,
     "Input Site Sphere": "x,y,z,radius"
   })

8. Poll ds_get_job_status(job_id) until complete

9. Report results:
   - Top N poses with scores
   - Warnings
   - Manifest reference

10. If interaction analysis is available,
    ds_run_protocol("Analyze Ligand Poses", {...})

11. Create final report with:
    - Methodology
    - Parameters used
    - Results table
    - Warnings
    - Manifest reference for reproducibility
    - Limitation statement about computational vs. experimental
```

## When Human Intervention Is Required

- Binding site is unclear or contested
- The protein has cofactors that should or shouldn't be included
- Docking scores are all similar (no clear ranking)
- Warnings indicate forcefield typing failures
- Results conflict with known experimental data
- The user needs to decide which docking protocol to use

## When Results Are Not Reliable Enough

- Fewer than 10 poses generated (sampling may be insufficient)
- All scores are very similar (no differentiation)
- Many typing or parameter warnings
- Protein has incomplete residues near the binding site
- Ligands have unusual chemistry not well parameterized

## Tool Reference

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| ds_get_capabilities | Check what's available | None |
| ds_health_check | Verify environment | None |
| ds_inspect_structure | Analyze structure file | file_path |
| ds_validate_structure | Check suitability for workflow | file_path, workflow |
| ds_convert_structure | Convert between formats | input_path, output_format |
| ds_list_protocols | List available protocols | None |
| ds_describe_protocol | Get protocol details | protocol_name |
| ds_run_protocol | Execute a protocol | protocol_name, parameters |
| ds_get_job_status | Poll job status | job_id |
| ds_cancel_job | Cancel running job | job_id |
| ds_list_jobs | List recent jobs | None |
| ds_render_structure | Create image (requires GUI) | molecule_path, representation |
