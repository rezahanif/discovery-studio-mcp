# BIOVIA Discovery Studio MCP Integration

## Environment Audit Summary

### Discovery Studio
- **Product**: BIOVIA Discovery Studio 2020
- **Version**: 20.1 (build 19295, build info: 2332 20191022 1434)
- **Install location**: `C:\Program Files\BIOVIA\Discovery Studio 2020`
- **Executable**: `C:\Program Files\BIOVIA\Discovery Studio 2020\bin\DiscoveryStudio2020.exe`
- **Edition**: Client (licensed), falls back to Visualizer (unlicensed)

### Perl
- **Interpreter**: Perl 5.26.1 (bundled)
- **Path**: `C:\Program Files\BIOVIA\Discovery Studio 2020\bin\perl.exe`
- **Library paths**: lib/5.26.1, lib/site_perl/5.26.1, lib/vendor_perl/5.26.1
- **Key modules**: DiscoveryScript, MdmDiscoveryScript, ForceFieldDiscoveryScript, ProtocolDiscoveryScript, DSScript, DSCommands

### Pipeline Pilot
- **Client DLL**: `pilot.dll` present in bin/
- **Server**: NOT installed locally
- **License Pack**: Client mode (version 20.1.0) at `C:\Program Files (x86)\BIOVIA\LicensePack`

### Documentation
- **Location**: `C:\Program Files\BIOVIA\Discovery Studio 2020\share\doc\DS` (Client docs)
- **Location**: `C:\Program Files\BIOVIA\Discovery Studio 2020\share\doc\DSV` (Visualizer docs)
- **Scripting API docs**: 300+ HTML files covering classes, properties, functions, filters
- **Format**: HTML-based help system

### Scripts
- **Built-in scripts** (34 `.pl` files): `share\Scripts\`
- **Sample scripts** (12 `.pl` files): `share\Samples\Scripts\`

### Registry
- `HKLM\SOFTWARE\BIOVIA\Discovery Studio\20.1` - InstallRoot
- `HKLM\SOFTWARE\Accelrys\Discovery Studio\20.1` - InstallRoot
- `HKLM\SOFTWARE\BIOVIA\License Pack` - CLIENT, version 20.1.0
- `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\DiscoveryStudio2020.exe`

### DSCript API Functions (confirmed)
`run_protocol`, `run_job_protocol`, `get_job_info`, `get_job_server`, `set_job_server`,
`save_active_view_image`, `save_application_image`, `save_desktop_image`,
`open_file`, `open_file_ext`, `insert_file`, `save_current_model`,
`set_batch_mode`, `process_events`, `display_message`,
`set_running`, `done_running`, `invoke_action`, `invoke_plugin_action`

### Supported File Formats (from MDMImportExport.xml)
PDB (.pdb, .ent), CIF (.cif), CSD (.csd, .fdat, .dat), CSV (.csv),
Catalyst (.cpd, .chm, .ds_chm), InsightII (.grd, .car, .psv),
MOL/SDF (.mol, .sdf, .sd, .mdl), Cerius2 (.msi), Quanta (.msf),
SMILES (.smi), Sketch (.skc), MOL2 (.mol2), HELM (.helm),
XYZ (.xyz), Map (.map), POV (.pov), VRML (.wrl),
DSV (.dsv), MSV (.msv), DSX (.dsx)
