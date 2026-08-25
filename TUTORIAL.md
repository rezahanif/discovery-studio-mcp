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

The connector provides 15 tools covering molecular modeling workflows:

**Structure Operations:**
- `ds_inspect_structure` — analyze a molecular structure file
- `ds_validate_structure` — check fitness for a workflow
- `ds_convert_structure` — convert between formats (PDB, MOL, MOL2, SDF, XYZ)

**Protocol Management:**
- `ds_list_protocols` — list available Discovery Studio protocols
- `ds_describe_protocol` — get protocol parameters and requirements
- `ds_run_protocol` — execute a protocol with parameters

**Job Monitoring:**
- `ds_list_jobs` — list recent and active jobs
- `ds_get_job_status` — check job progress
- `ds_cancel_job` — cancel a running job

**Rendering:**
- `ds_render_structure` — capture a viewport screenshot

**API Guidance (Layer B):**
- `ds_search_api` — search the Discovery Studio scripting API
- `ds_function_registry` — look up specific API functions

### Example Agent Prompts

```
Inspect the protein structure at D:/data/protein.pdb and tell me 
how many chains, residues, and ligands it contains.
```

```
Convert the SDF file at D:/ligands/molecule.sdf to PDB format.
```

```
List all available protocols and tell me which ones can do 
molecular dynamics simulation.
```

```
Search the API for functions related to pharmacophore modeling.
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DS_MOCK_MODE` | `false` | Enable mock adapter for testing |
| `DS_FILE_WHITELIST` | (all paths) | Restrict file access to specific directories |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Adapter not available` | Discovery Studio not installed or not found. Check `DS_ROOT`. |
| `Pipeline Pilot not connected` | Some protocols require Pipeline Pilot Server. Check `ds_get_capabilities`. |
| `Mock mode` | Set `DS_MOCK_MODE=true` for testing without Discovery Studio. |
