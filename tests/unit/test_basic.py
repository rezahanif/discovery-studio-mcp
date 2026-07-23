"""Tests for the Discovery Studio MCP server."""

import pytest

from discovery_studio_mcp.config import Settings
from discovery_studio_mcp.models import (
    DsCapabilities,
    HealthCheckResult,
    StructureInspection,
    ProtocolInfo,
    ProtocolDescription,
    ProtocolParameter,
    RunProtocolRequest,
    JobResult,
    JobStatus,
    AdapterInfo,
    AdapterStatus,
    ConvertStructureRequest,
)
from discovery_studio_mcp.security import (
    sanitize_filename,
    is_safe_extension,
    validate_file_size,
)
from discovery_studio_mcp.errors import (
    SecurityViolationError,
    PathTraversalError,
    UnauthorizedDirectoryError,
    FileSizeLimitError,
    UnsupportedFormatError,
    ProtocolNotFoundError,
)


class TestConfig:
    def test_settings_defaults(self):
        s = Settings()
        assert isinstance(s.ds_mock_mode, bool)

    def test_settings_mock_mode(self):
        s = Settings(ds_mock_mode=True)
        assert s.ds_mock_mode is True

    def test_output_path_creation(self, tmp_path):
        s = Settings(ds_output_dir=str(tmp_path / "workspace"))
        assert s.output_path.exists()


class TestModels:
    def test_capabilities(self):
        caps = DsCapabilities(
            mock=True,
            discovery_studio_version="2020",
            discovery_studio_build="2332",
            discovery_studio_root="/mock",
            available_adapters=[
                AdapterInfo(
                    name="mock",
                    status=AdapterStatus.CONFIRMED,
                    description="Mock adapter",
                )
            ],
        )
        assert caps.mock is True
        assert caps.discovery_studio_version == "2020"

    def test_health_check_result(self):
        hc = HealthCheckResult(
            mock=True,
            status="ok",
            checks=[{"component": "test", "status": "available"}],
        )
        assert hc.mock is True
        assert hc.status == "ok"

    def test_structure_inspection(self):
        si = StructureInspection(
            mock=True,
            file_path="/test/1abc.pdb",
            format="pdb",
            model_count=1,
            chains=["A"],
            residues=246,
            atoms=1964,
            ligands=["LIG"],
            waters=42,
            metals=["ZN"],
        )
        assert si.model_count == 1
        assert len(si.chains) == 1

    def test_protocol_info(self):
        pi = ProtocolInfo(
            name="Prepare Protein",
            description="Prepare protein for docking",
            category="Protein Preparation",
            required_parameters=["Input Protein"],
            requires_server=True,
        )
        assert pi.name == "Prepare Protein"
        assert pi.requires_server is True

    def test_protocol_description(self):
        pd = ProtocolDescription(
            name="Prepare Protein",
            description="Test",
            parameters=[
                ProtocolParameter(name="Input Protein", type="Molecule", required=True),
                ProtocolParameter(name="pH", type="Real", required=False, default_value="7.4"),
            ],
            requires_server=True,
        )
        assert len(pd.parameters) == 2
        assert pd.parameters[0].required is True

    def test_run_protocol_request(self):
        r = RunProtocolRequest(
            protocol_name="test",
            parameters={"key": "value"},
            input_files=["test.pdb"],
        )
        assert r.protocol_name == "test"

    def test_job_result(self):
        jr = JobResult(
            job_id="abc123",
            status=JobStatus.COMPLETED,
            progress=100.0,
        )
        assert jr.job_id == "abc123"
        assert jr.status == JobStatus.COMPLETED

    def test_convert_structure_request(self):
        r = ConvertStructureRequest(
            input_path="/test/input.pdb",
            output_format="mol",
        )
        assert r.output_format == "mol"


class TestSecurity:
    def test_sanitize_filename(self):
        assert sanitize_filename("test.pdb") == "test.pdb"
        assert sanitize_filename("../etc/passwd") == "passwd"
        assert sanitize_filename("C:\\Windows\\system32\\test.pdb") == "test.pdb"

    def test_is_safe_extension(self):
        assert is_safe_extension("test.pdb") is True
        assert is_safe_extension("test.mol") is True
        assert is_safe_extension("test.mol2") is True
        assert is_safe_extension("test.exe") is False
        assert is_safe_extension("test.bat") is False
        assert is_safe_extension("test.sh") is False

    def test_unsafe_extension_detected(self):
        assert is_safe_extension("script.py") is False
        assert is_safe_extension("data.dll") is False


class TestErrors:
    def test_security_violation(self):
        e = SecurityViolationError("test")
        assert str(e) == "test"

    def test_path_traversal(self):
        e = PathTraversalError("traversal detected")
        assert isinstance(e, SecurityViolationError)

    def test_unauthorized_directory(self):
        e = UnauthorizedDirectoryError("not allowed")
        assert isinstance(e, SecurityViolationError)

    def test_file_size_limit(self):
        e = FileSizeLimitError("too large")
        assert isinstance(e, SecurityViolationError)

    def test_unsupported_format(self):
        e = UnsupportedFormatError(".exe")
        assert str(e) == ".exe"

    def test_protocol_not_found(self):
        e = ProtocolNotFoundError("UnknownProtocol")
        assert "UnknownProtocol" in str(e)
