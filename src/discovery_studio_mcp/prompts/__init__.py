"""MCP prompts for Discovery Studio workflows."""


def register_prompts(server):
    """Register workflow starter prompts with the MCP server."""

    @server.list_prompts()
    async def list_prompts():
        return [
            {
                "name": "ds_structure_preparation",
                "description": "Prepare a protein structure for molecular modeling "
                               "(docking, simulation, minimization).",
                "arguments": [
                    {
                        "name": "protein_file",
                        "description": "Path to the protein structure file (PDB, MOL2)",
                        "required": True,
                    },
                    {
                        "name": "target_workflow",
                        "description": "Target workflow: docking, minimization, simulation",
                        "required": True,
                    },
                ],
            },
            {
                "name": "ds_ligand_analysis",
                "description": "Analyze a ligand molecule: properties, conformations, "
                               "pharmacophore features.",
                "arguments": [
                    {
                        "name": "ligand_file",
                        "description": "Path to the ligand file (SDF, MOL, MOL2)",
                        "required": True,
                    },
                ],
            },
            {
                "name": "ds_batch_convert",
                "description": "Convert multiple structure files between formats.",
                "arguments": [
                    {
                        "name": "input_files",
                        "description": "Comma-separated list of input file paths",
                        "required": True,
                    },
                    {
                        "name": "output_format",
                        "description": "Target format (pdb, mol2, sdf)",
                        "required": True,
                    },
                ],
            },
            {
                "name": "ds_debug_workflow",
                "description": "Debug a failing Discovery Studio workflow by checking "
                               "component status and suggesting fixes.",
                "arguments": [
                    {
                        "name": "error_description",
                        "description": "Description of the error or unexpected behavior",
                        "required": True,
                    },
                ],
            },
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict):
        if name == "ds_structure_preparation":
            protein_file = arguments.get("protein_file", "")
            workflow = arguments.get("target_workflow", "docking")
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Prepare {protein_file} for {workflow}. "
                        f"Steps: 1) Inspect structure with ds_inspect_structure. "
                        f"2) Validate with ds_validate_structure(workflow='{workflow}'). "
                        f"3) If issues found, describe the problem and suggest fixes. "
                        f"4) List relevant protocols with ds_list_protocols. "
                        f"5) Describe the best protocol with ds_describe_protocol.",
                    }
                ]
            }
        elif name == "ds_ligand_analysis":
            ligand_file = arguments.get("ligand_file", "")
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Analyze {ligand_file}. "
                        f"Steps: 1) Inspect with ds_inspect_structure. "
                        f"2) Validate for pharmacophore workflow. "
                        f"3) Search API for relevant analysis methods "
                        f"(ds_search_api('pharmacophore features')). "
                        f"4) List available protocols for ligand analysis.",
                    }
                ]
            }
        elif name == "ds_batch_convert":
            input_files = arguments.get("input_files", "")
            output_format = arguments.get("output_format", "pdb")
            files = [f.strip() for f in input_files.split(",")]
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Convert {len(files)} files to {output_format}. "
                        f"Steps: 1) For each file, call ds_convert_structure. "
                        f"2) Report success/failure per file. "
                        f"3) List any unsupported formats.",
                    }
                ]
            }
        elif name == "ds_debug_workflow":
            error_desc = arguments.get("error_description", "")
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Debug issue: {error_desc}. "
                        f"Steps: 1) Run ds_health_check. "
                        f"2) Check capabilities with ds_get_capabilities. "
                        f"3) Search API for related functions. "
                        f"4) Suggest specific fixes based on error type.",
                    }
                ]
            }
        else:
            return {"messages": [{"role": "user", "content": "Unknown prompt"}]}
