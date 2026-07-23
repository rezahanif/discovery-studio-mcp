# Automation Capabilities Assessment

## Overview

This document catalogs all discovered automation mechanisms for BIOVIA Discovery Studio 2020
and their current status.

## 1. DiscoveryScript (Perl API)

**Source**: Local installation, lib/vendor_perl/5.26.1/, share/doc/DS/content/docds/scripting/

**Version**: Discovery Studio 2020, Perl 5.26.1

**How it works**:
DiscoveryScript is a SWIG-generated Perl API that wraps Discovery Studio's C++ core.
Scripts use Perl modules like MdmDiscoveryScript, ForceFieldDiscoveryScript, 
ProtocolDiscoveryScript, and DSScript.

**Invocation**: 
- `perl.exe -I <lib_paths> script.pl` (CLI mode, limited)
- `DiscoveryStudio2020.exe script.pl` (client mode, full features)
- Drag-and-drop into DS client

**Parameter passing**: Command-line args via @ARGV, default variables in script

**File handling**: `DiscoveryScript::Open()` opens files, `Document::Save()` saves them

**Status retrieval**: Return values from API functions, Perl warn/die for errors

**Results**: Files written to disk, documents displayed in client

**GUI required**: 
- CLI mode: Some operations work (structure processing, typing)
- Client mode: Required for visualization, some protocol interactions
- Protocol execution ALWAYS requires Pipeline Pilot Server

**License**: 
- DSCommands (unlicensed) available in Visualizer mode
- ProtocolCommands (licensed) requires Client license
- Protocol execution requires Pipeline Pilot license

**Limitations**:
- No headless rendering without client
- Protocol execution requires Pipeline Pilot Server
- Cannot run arbitrary protocols without server connection
- Client must be running for ds_* tools

**Test status**: INSTALLATION CONFIRMED - API NOT YET TESTED

## 2. Pipeline Pilot

**Source**: Local DLL (pilot.dll), documentation

**Version**: Pipeline Pilot component bundled with DS 2020 Client

**How it works**:
Pipeline Pilot is a protocol execution platform. Discovery Studio can launch
protocols through Pipeline Pilot Server. The `LaunchProtocol` command in 
ProtocolCommands.pm connects to a Pipeline Pilot Server.

**Invocation**: `LaunchProtocol(protocolName, parameterMap, "server:port")`

**Parameter passing**: `Protocol::ParameterMap` object with typed parameters

**File handling**: Server-side file management

**Status retrieval**: Protocol::Session, Protocol::Task APIs

**GUI required**: No (operates via server connection)

**License**: Requires Pipeline Pilot Server license

**Limitations**:
- Server NOT installed on this machine
- Requires separate license
- Server URL must be configured via DS_PIPELINE_PILOT_URL

**Test status**: CLIENT DLL FOUND - SERVER NOT AVAILABLE

## 3. Command Line Interface

**Source**: perl.bat, DiscoveryStudio2020.exe

**How it works**:
- `perl.bat` sets up the Perl environment and runs scripts
- `DiscoveryStudio2020.exe <script.pl>` starts client and runs script

**Limitations**:
- Perl CLI mode: Can process structures, cannot render or interact with GUI
- Client mode: Requires GUI session, cannot run headless protocols without server

**Test status**: CONFIRMED (perl.bat exists, DiscoveryStudio2020.exe exists)

## 4. Filesystem Integration

**How it works**:
Basic structure file operations: reading PDB files, counting atoms/chains/residues,
format detection, file copying.

**Limitations**: No molecular computation, no protocol execution

**Test status**: CONFIRMED (basic PDB parsing works)

## 5. UI Automation

**How it works**:
Windows automation via pywinauto/pyautogui to control Discovery Studio GUI.

**Limitations**:
- Fragile, version-dependent
- Requires DS client running with visible GUI
- Cannot be headless
- Should be last resort

**Test status**: DISABLED BY DEFAULT (DS_ENABLE_UI_FALLBACK=false)

## Capability Matrix

| Category | Status | Notes |
|----------|--------|-------|
| Pipeline Pilot | Присутствует клиентская DLL, сервер отсутствует | Server not available locally |
| DiscoveryScript | Подтверждено (установка) | API modules found, not yet tested live |
| CLI | Подтверждено | perl.bat, DiscoveryStudio2020.exe found |
| Filesystem | Подтверждено | Basic PDB/XYZ parsing works |
| UI Automation | Отключено по умолчанию | Requires DS_ENABLE_UI_FALLBACK=true |

## Key Findings

1. **DiscoveryScript API is comprehensive** - 300+ scripting API documentation HTML files confirm rich API surface
2. **Protocol execution blocked** - No Pipeline Pilot Server available locally
3. **Rendering requires GUI** - No headless rendering API confirmed in DiscoveryScript
4. **Structure inspection works CLI** - PDB file parsing possible without DS client
5. **CLI Perl scripts can process structures** - Forcefield typing, minimization setup possible
