#!/usr/bin/env python3
"""
BIOVIA Discovery Studio Environment Auditor

Scans the Windows system for Discovery Studio installations,
Perl, Pipeline Pilot, DiscoveryScript modules, documentation,
and available automation capabilities.

Outputs:
  reports/environment-report.json  - machine-readable
  reports/environment-report.md    - human-readable
"""

import json
import os
import sys
import hashlib
import datetime
import subprocess
import re
from pathlib import Path
from typing import Any


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return -1, "", str(e)


def get_registry(path: str) -> dict[str, Any] | None:
    """Read a registry key using PowerShell."""
    ret, out, err = run_cmd(
        ["powershell", "-Command", f"Get-ItemProperty -Path '{path}' -ErrorAction SilentlyContinue | ConvertTo-Json"],
        timeout=15,
    )
    if ret == 0 and out.strip():
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
    return None


def get_registry_children(path: str) -> list[str]:
    ret, out, err = run_cmd(
        ["powershell", "-Command", f"Get-ChildItem -Path '{path}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"],
        timeout=15,
    )
    if ret == 0 and out.strip():
        return [line.strip() for line in out.strip().split("\n") if line.strip()]
    return []


def glob_files(pattern: str) -> list[str]:
    """Glob files in a directory."""
    ret, out, err = run_cmd(
        ["powershell", "-Command", f"Get-ChildItem -Path '{pattern}' -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName"],
        timeout=30,
    )
    if ret == 0 and out.strip():
        return [line.strip() for line in out.strip().split("\n") if line.strip()]
    return []


def file_exists(path: str) -> bool:
    return os.path.exists(path)


def dir_exists(path: str) -> bool:
    return os.path.isdir(path)


def file_hash(path: str, algo: str = "sha256") -> str | None:
    try:
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def list_dir(path: str, depth: int = 1) -> list[str]:
    """List directory contents."""
    ret, out, err = run_cmd(
        ["powershell", "-Command", f"Get-ChildItem -Path '{path}' -Depth {depth} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName | Select-Object -First 500"],
        timeout=30,
    )
    if ret == 0 and out.strip():
        return [line.strip() for line in out.strip().split("\n") if line.strip()]
    return []


def find_build_info(root: str) -> dict[str, str]:
    bi_path = os.path.join(root, "buildinfo.txt")
    if os.path.isfile(bi_path):
        with open(bi_path) as f:
            content = f.read().strip()
        return {"file": bi_path, "content": content}
    return {}


def find_application_xml(root: str) -> dict[str, Any]:
    xml_path = os.path.join(root, "etc", "Application.xml")
    result = {"file": xml_path}
    if os.path.isfile(xml_path):
        with open(xml_path, encoding="utf-8") as f:
            content = f.read()
        result["size"] = len(content)
        # Extract key attributes
        for attr in ["version", "publicVersion", "build", "vendor", "name", "licensedSuffix", "unLicensedSuffix"]:
            m = re.search(rf'{attr}\s*=\s*"([^"]*)"', content)
            if m:
                result[attr] = m.group(1)
    return result


def find_perl(root: str) -> dict[str, Any]:
    perl_exe = os.path.join(root, "bin", "perl.exe")
    result = {"exe": perl_exe, "exists": os.path.isfile(perl_exe)}
    if result["exists"]:
        ret, out, err = run_cmd(
            ["powershell", "-Command", f"& '{perl_exe}' --version 2>&1"],
            timeout=10,
        )
        result["version_output"] = out.strip() if ret == 0 else err.strip()
    # Find version from lib dir
    lib_dir = os.path.join(root, "lib")
    versions = []
    if os.path.isdir(lib_dir):
        for entry in os.listdir(lib_dir):
            full = os.path.join(lib_dir, entry)
            if os.path.isdir(full):
                try:
                    parts = entry.split(".")
                    if all(p.isdigit() for p in parts):
                        versions.append(entry)
                except Exception:
                    pass
    result["perl_versions"] = versions
    return result


def find_perl_modules(root: str) -> list[str]:
    vendor_perl = os.path.join(root, "lib", "vendor_perl")
    result = []
    if os.path.isdir(vendor_perl):
        for dirpath, dirs, files in os.walk(vendor_perl):
            for f in files:
                if f.endswith(".pm"):
                    result.append(os.path.join(dirpath, f))
    return result


def find_documentation(root: str) -> dict[str, Any]:
    doc_dir = os.path.join(root, "share", "doc")
    result = {"paths": []}
    if os.path.isdir(doc_dir):
        for entry in os.listdir(doc_dir):
            full = os.path.join(doc_dir, entry)
            if os.path.isdir(full):
                result["paths"].append(full)
        # Count HTML files
        html_files = []
        for dirpath, dirs, files in os.walk(doc_dir):
            for f in files:
                if f.endswith(".htm") or f.endswith(".html"):
                    html_files.append(os.path.join(dirpath, f))
        result["html_file_count"] = len(html_files)
    return result


def find_scripts(root: str) -> dict[str, Any]:
    scripts_dir = os.path.join(root, "share", "Scripts")
    samples_scripts = os.path.join(root, "share", "Samples", "Scripts")
    result = {}
    if os.path.isdir(scripts_dir):
        result["scripts_dir"] = scripts_dir
        result["scripts_files"] = [
            f for f in os.listdir(scripts_dir)
            if os.path.isfile(os.path.join(scripts_dir, f)) and f.endswith(".pl")
        ]
    if os.path.isdir(samples_scripts):
        result["samples_scripts_dir"] = samples_scripts
        result["samples_files"] = [
            f for f in os.listdir(samples_scripts)
            if os.path.isfile(os.path.join(samples_scripts, f)) and f.endswith(".pl")
        ]
    return result


def read_text_files(root: str, files: list[str]) -> dict[str, str]:
    result = {}
    for rel_path in files:
        full = os.path.join(root, rel_path)
        if os.path.isfile(full):
            with open(full, errors="replace") as f:
                result[rel_path] = f.read()[:2000]
    return result


def find_pipeline_pilot() -> dict[str, Any]:
    result = {"client_found": False, "server_found": False}
    # Check for Pipeline Pilot client DLL
    ds_root = r"C:\Program Files\BIOVIA\Discovery Studio 2020"
    pilot_dll = os.path.join(ds_root, "bin", "pilot.dll")
    if os.path.isfile(pilot_dll):
        result["client_found"] = True
        result["client_dll"] = pilot_dll
    # Check typical Pipeline Pilot server paths
    pp_paths = [
        r"C:\Program Files\BIOVIA\PipelinePilot",
        r"C:\Program Files (x86)\BIOVIA\PipelinePilot",
        r"C:\Program Files\Accelrys\PipelinePilot",
    ]
    for pp in pp_paths:
        if os.path.isdir(pp):
            result["server_found"] = True
            result["server_path"] = pp
    # Check for environment variables
    for key, val in os.environ.items():
        if "PIPELINE" in key.upper() or "SCITEGIC" in key.upper():
            result.setdefault("env_vars", {})[key] = val
    return result


def find_dsscript_functions(ds_root: str) -> list[str]:
    """Extract exported function names from DSScript.pm."""
    dsscript_path = os.path.join(ds_root, "lib", "vendor_perl", "5.26.1", "DSScript.pm")
    functions = []
    if os.path.isfile(dsscript_path):
        with open(dsscript_path, errors="replace") as f:
            for line in f:
                m = re.match(r"\s*\*(\w+)\s*=\s*\*DSScriptc::(\w+);", line)
                if m:
                    functions.append(m.group(1))
    return functions


def find_registry_info() -> dict[str, Any]:
    result = {}
    paths = [
        r"HKLM:\SOFTWARE\BIOVIA\Discovery Studio\20.1",
        r"HKLM:\SOFTWARE\Accelrys\Discovery Studio\20.1",
        r"HKLM:\SOFTWARE\BIOVIA\License Pack",
        r"HKLM:\SOFTWARE\Accelrys\License Pack",
    ]
    for path in paths:
        data = get_registry(path)
        if data:
            result[path] = {
                k: v for k, v in data.items()
                if not k.startswith("PS") and k != "Cim"
            }
    return result


def file_header(path: str, lines: int = 10) -> str:
    try:
        with open(path, errors="replace") as f:
            return "".join(f.readline() for _ in range(lines))
    except Exception:
        return ""


def get_python_info() -> dict[str, Any]:
    return {
        "version": sys.version,
        "executable": sys.executable,
        "platform": sys.platform,
    }


def main():
    discovery_roots = [
        r"C:\Program Files\BIOVIA\Discovery Studio 2020",
        r"C:\Program Files\Dassault Systemes\Discovery Studio",
        r"C:\Program Files (x86)\BIOVIA\Discovery Studio",
    ]

    report: dict[str, Any] = {
        "scan_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "machine": os.environ.get("COMPUTERNAME", "unknown"),
        "user": os.environ.get("USERNAME", "unknown"),
        "python": get_python_info(),
        "discovery_studio": {},
        "perl": {},
        "perl_modules": [],
        "documentation": {},
        "scripts": {},
        "pipeline_pilot": {},
        "registry": {},
        "environment_variables": {},
        "supported_formats": {},
    }

    # Find Discovery Studio
    for root in discovery_roots:
        if not os.path.isdir(root):
            continue

        ds_exe = os.path.join(root, "bin", "DiscoveryStudio2020.exe")
        report["discovery_studio"] = {
            "root": root,
            "executable": ds_exe,
            "executable_exists": os.path.isfile(ds_exe),
            "build_info": find_build_info(root),
            "application_xml": find_application_xml(root),
            "total_files_in_bin": len(glob_files(os.path.join(root, "bin", "*"))),
        }

        report["perl"] = find_perl(root)
        report["perl_modules"] = find_perl_modules(root)
        report["dsscript_functions"] = find_dsscript_functions(root)
        report["documentation"] = find_documentation(root)
        report["scripts"] = find_scripts(root)
        break

    report["pipeline_pilot"] = find_pipeline_pilot()
    report["registry"] = find_registry_info()

    # Environment variables
    for key, val in sorted(os.environ.items()):
        if any(kw in key.upper() for kw in ["BIOVIA", "DISCOVERY", "PIPELINE", "ACCELRYS", "SCITEGIC", "CHEMAXON", "PERL", "DS_"]):
            if "PASSWORD" not in key.upper() and "TOKEN" not in key.upper() and "SECRET" not in key.upper():
                report["environment_variables"][key] = val

    # Format detection
    for import_config in ["MDMImportExport.xml", "SDMImportExport.xml", "ForceFieldImportExportDS.xml", "FileIO.xml"]:
        full = os.path.join(report["discovery_studio"].get("root", ""), "etc", import_config)
        if os.path.isfile(full):
            with open(full, errors="replace") as f:
                report["supported_formats"][import_config] = f.read()[:5000]

    # Write JSON report
    base_dir = Path(__file__).resolve().parents[1]
    reports_dir = base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "environment-report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    # Write Markdown report
    md_path = reports_dir / "environment-report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# BIOVIA Discovery Studio Environment Report\n\n")
        f.write(f"**Scan time**: {report['scan_time']}\n\n")
        f.write(f"**Machine**: {report['machine']}\n\n")

        ds = report["discovery_studio"]
        f.write("## Discovery Studio\n\n")
        f.write(f"- **Root**: `{ds.get('root', 'NOT FOUND')}`\n")
        f.write(f"- **Executable**: `{ds.get('executable', 'N/A')}` (exists: {ds.get('executable_exists', False)})\n")
        axml = ds.get("application_xml", {})
        if axml:
            f.write(f"- **Vendor**: {axml.get('vendor', 'N/A')}\n")
            f.write(f"- **Version**: {axml.get('version', 'N/A')}\n")
            f.write(f"- **Public Version**: {axml.get('publicVersion', 'N/A')}\n")
            f.write(f"- **Build**: {axml.get('build', 'N/A')}\n")
            f.write(f"- **Licensed Suffix**: {axml.get('licensedSuffix', 'N/A')}\n")
        bi = ds.get("build_info", {})
        if bi:
            f.write(f"- **Build Info**: {bi.get('content', 'N/A')}\n")
        f.write(f"- **Files in bin**: {ds.get('total_files_in_bin', 0)}\n\n")

        perl = report["perl"]
        f.write("## Perl\n\n")
        f.write(f"- **Executable**: `{perl.get('exe', 'N/A')}` (exists: {perl.get('exists', False)})\n")
        f.write(f"- **Perl versions in lib**: {perl.get('perl_versions', [])}\n")
        f.write(f"- **Version output**:\n```\n{perl.get('version_output', 'N/A')}\n```\n\n")

        f.write(f"- **Perl modules count**: {len(report['perl_modules'])}\n")
        f.write(f"- **DSScript exported functions count**: {len(report.get('dsscript_functions', []))}\n\n")
        if report.get("dsscript_functions"):
            f.write(f"- **DSScript functions**: {', '.join(report['dsscript_functions'])}\n\n")

        doc = report["documentation"]
        f.write("## Documentation\n\n")
        f.write(f"- **Doc paths**: {doc.get('paths', [])}\n")
        f.write(f"- **HTML files**: {doc.get('html_file_count', 0)}\n\n")

        scripts = report["scripts"]
        f.write("## Scripts\n\n")
        if scripts.get("scripts_dir"):
            f.write(f"- **Scripts directory**: `{scripts['scripts_dir']}` ({len(scripts.get('scripts_files', []))} scripts)\n")
            for s in scripts.get("scripts_files", []):
                f.write(f"  - {s}\n")
        if scripts.get("samples_scripts_dir"):
            f.write(f"- **Samples directory**: `{scripts['samples_scripts_dir']}` ({len(scripts.get('samples_files', []))} samples)\n")
            for s in scripts.get("samples_files", []):
                f.write(f"  - {s}\n")
        f.write("\n")

        pp = report["pipeline_pilot"]
        f.write("## Pipeline Pilot\n\n")
        f.write(f"- **Client found**: {pp.get('client_found', False)}\n")
        if pp.get("client_dll"):
            f.write(f"- **Client DLL**: `{pp['client_dll']}`\n")
        f.write(f"- **Server found**: {pp.get('server_found', False)}\n")
        if pp.get("server_path"):
            f.write(f"- **Server path**: `{pp['server_path']}`\n")
        if pp.get("env_vars"):
            for k, v in pp["env_vars"].items():
                f.write(f"- **{k}** = {v}\n")
        f.write("\n")

        registry = report["registry"]
        f.write("## Registry\n\n")
        for path, data in registry.items():
            f.write(f"### `{path}`\n\n")
            for k, v in data.items():
                f.write(f"- **{k}**: `{v}`\n")
            f.write("\n")

        env_vars = report["environment_variables"]
        if env_vars:
            f.write("## Environment Variables (BIOVIA-related)\n\n")
            for k, v in env_vars.items():
                f.write(f"- **{k}** = `{v}`\n")
            f.write("\n")

        f.write("## Summary\n\n")
        f.write(f"- Discovery Studio installed: {bool(ds.get('root'))}\n")
        f.write(f"- Perl available: {perl.get('exists', False)}\n")
        f.write(f"- Pipeline Pilot Client: {pp.get('client_found', False)}\n")
        f.write(f"- Pipeline Pilot Server: {pp.get('server_found', False)}\n")
        f.write(f"- Documentation found: {bool(doc.get('paths'))}\n")
        f.write(f"- Scripts found: {bool(scripts)}\n")

    print(f"Environment report saved to {json_path}")
    print(f"Environment report saved to {md_path}")
    return report


if __name__ == "__main__":
    main()
