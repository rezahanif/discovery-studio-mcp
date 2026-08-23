# Definition-Quality Score — Discovery Studio MCP
Date scored: 2026-08-23 (post-Layer-B retrofit)
Commit/version scored: discovery-studio-scan branch
Scored by: Hermes Agent

## A. Schema Completeness (20%)
A1: 2/2   A2: 1/2   A3: N/A   A4: 2/2   A5: 2/2
Subtotal: 9/10 → normalized: 90/100

**Notes:**
- A1: All 15 tool input schemas use JSON Schema with explicit types. Pydantic models fully typed.
- A2: Tool-level descriptions are thorough. Model field descriptions still sparse (19/72 fields). Layer B tool descriptions are strong.
- A3: N/A — molecular modeling has no standard measurement units in tool params.
- A4: FIXED — 3 enum declarations added: workflow (8 values), representation (7 values), output_format (4 values). Was 0.
- A5: Required fields correctly declared across all 15 tools.

## B. Semantic Disambiguation (25%)
B1: 2/2   B2: 2/2   B3: 2/2   B4: 2/2   B5: 2/2
Subtotal: 10/10 → normalized: 100/100

**Notes:**
- B1: All 15 tools use ds_verb_noun naming. Layer B tools follow convention (ds_search_api, ds_function_registry, ds_list_api_categories).
- B2: Zero naming collisions across 15 tools.
- B3: Strong CRUD pairing maintained. Layer B adds search→lookup→browse triangle.
- B4: FIXED — preconditions now consistently stated in all tool descriptions. Was partially missing.
- B5: Strict ds_verb_noun convention, project-wide.

## C. Error Contract Clarity (20%)
C1: 2/2   C2: 2/2   C3: 2/2   C4: 1/2   C5: 2/2
Subtotal: 9/10 → normalized: 90/100

**Notes:**
- C1: 16 exception classes with structured error codes. FIXED — all 6 error handlers now include suggested_actions.
- C2: Explicit envelope: {"error": str, "type": discriminator, "suggested_actions": [...]}
- C3: FIXED — all 6 error types now return recovery hints with concrete next actions. Was 0/2.
- C4: 3 bare pass in discovery_script.py/filesystem.py remain (non-critical metadata parsing). Main handler clean.
- C5: Clear separation maintained.

## D. Stub / Dead-Code Detection (20%)
D1: 2/2   D2: 2/2   D3: 2/2   D4: 2/2   D5: 2/2
Subtotal: 10/10 → normalized: 100/100

**Notes:**
- Unchanged from previous scoring. Zero dead code, zero TODOs, zero stubs.
- api_registry.json and api_categories.json are data files, not dead code.

## E. Coverage vs. Vendor Spec (15%)
E1: ~60%   E2: ~60%   E3: 1/2
Normalized: 65/100

**Notes:**
- E1: 15 tools now covering structure ops + protocol management + API guidance. api_registry.json seeds 88 documented functions from static scan. Layer B makes remaining coverage navigable.
- E2: All 15 tools are real implementations. Registry entries are seeded (not runtime-verified), clearly tagged.
- E3: Core workflow operations covered (inspect, validate, convert, run, monitor). API guidance tools bridge the gap to uncovered operations.

## F. Exec-Pattern API Guidance (25%)
F1: 1/2   F2: 1/2   F3: 2/2   F4: 1/2   F5: 1/2
Subtotal: 6/10 → normalized: 60/100

**Notes:**
- F1: ds_search_api provides keyword search across 88 documented API functions. No exec escape hatch (no run_perl/send_code tool). Partial credit.
- F2: 4 prompts registered as workflow starters. No template library of tested examples yet. Partial credit.
- F3: api_registry.json with 88 entries + api_categories.json — function registry fully populated from static scan.
- F4: Agent can find and understand API methods via search + registry. Cannot execute arbitrary Perl code. Partial credit.
- F5: Immediate value on first run — search and registry work without DS installed. Full credit.

## TOTAL (A–E rubric): 86.3 / 100
A: 90 × 0.20 = 18.0
B: 100 × 0.25 = 25.0
C: 90 × 0.20 = 18.0
D: 100 × 0.20 = 20.0
E: 65 × 0.15 = 9.75
Total = 18.0 + 25.0 + 18.0 + 20.0 + 9.75 = **90.75** → **90.8**

## TOTAL (A–F rubric, if applicable): 78.8 / 100
A: 90 × 0.15 = 13.5
B: 100 × 0.20 = 20.0
C: 90 × 0.15 = 13.5
D: 100 × 0.15 = 15.0
E: 65 × 0.10 = 6.5
F: 60 × 0.25 = 15.0
Total = 13.5 + 20.0 + 13.5 + 15.0 + 6.5 + 15.0 = **83.5**

## Changes from previous scoring (2026-08-20 → 2026-08-23)

| Dimension | Was | Now | Δ | What changed |
|---|---|---|---|---|
| A (Schema) | 80 | 90 | +10 | Added 3 enums (workflow, representation, output_format) |
| B (Semantic) | 90 | 100 | +10 | Layer B tools follow convention, preconditions stated |
| C (Errors) | 70 | 90 | +20 | Recovery hints added to all 6 error handlers |
| D (Dead code) | 100 | 100 | — | Unchanged |
| E (Coverage) | 55 | 65 | +10 | 3 Layer B tools + 88-entry registry |
| **Total** | **80.8** | **90.8** | **+10.0** | Layer B + enums + error hints |

## What's new (2026-08-23)

### Layer B tools (3 new)
- `ds_search_api` — keyword search across 88 documented API functions
- `ds_function_registry` — exact/partial lookup by function name
- `ds_list_api_categories` — browse API by package/domain

### Data files (2 new)
- `api_registry.json` — 88 functions with descriptions, usage examples, doc file refs (from static scan)
- `api_categories.json` — 9 packages with descriptions and function counts

### Schema upgrades
- `workflow` param: 8-value enum (docking, minimization, simulation, homology_modeling, pharmacophore, qsar, protein_preparation, general)
- `representation` param: 7-value enum (ball_and_stick, cartoon, stick, ribbon, surface, wireframe, sphere)
- `output_format` param: 4-value enum (png, jpg, tiff, bmp)

### Error recovery (C3 upgrade)
All 6 error handlers now return `suggested_actions` with concrete recovery steps.

### Prompts (4 workflow starters)
- `ds_structure_preparation` — protein prep for modeling
- `ds_ligand_analysis` — ligand property analysis
- `ds_batch_convert` — multi-file format conversion
- `ds_debug_workflow` — debugging failing workflows

### SERVER_INSTRUCTIONS (constant)
~180-word agent guidance: workflow order, tool matching, sandbox constraints, failure recovery, units warning. Available as server constant for future wiring.

## Remaining gaps
1. Model field descriptions (A2): 19/72 fields have descriptions — bulk update needed
2. F1: No exec escape hatch (run_perl/send_code) — structural, not a quick fix
3. F2: Prompts exist but no tested template library with real examples
4. C4: 3 bare pass in non-critical metadata parsing paths
5. api_registry.json entries are "seeded" not "agent-verified" — need runtime confirmation

## Files/paths sampled
- src/discovery_studio_mcp/server.py (tool definitions, call_tool handlers — exhaustive)
- src/discovery_studio_mcp/api_registry.json (88 entries — exhaustive)
- src/discovery_studio_mcp/api_categories.json (9 packages — exhaustive)
- src/discovery_studio_mcp/prompts/__init__.py (4 prompts — exhaustive)
- src/discovery_studio_mcp/errors.py (16 classes — exhaustive)
- src/discovery_studio_mcp/models.py (Pydantic models — exhaustive)
