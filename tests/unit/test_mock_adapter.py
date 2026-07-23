"""Tests for the MockAdapter."""

import pytest
from discovery_studio_mcp.adapters.mock import MockAdapter
from discovery_studio_mcp.models import (
    RunProtocolRequest,
    JobStatus,
    ConvertStructureRequest,
    RenderStructureRequest,
)


@pytest.fixture
def adapter():
    return MockAdapter()


@pytest.mark.asyncio
async def test_get_capabilities(adapter):
    caps = await adapter.get_capabilities()
    assert caps.mock is True
    assert caps.discovery_studio_version == "2020 (mock)"
    assert len(caps.available_adapters) > 0


@pytest.mark.asyncio
async def test_health_check(adapter):
    result = await adapter.health_check()
    assert result.mock is True
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_inspect_structure(adapter):
    result = await adapter.inspect_structure("/test/1abc.pdb")
    assert result.mock is True
    assert result.file_path == "/test/1abc.pdb"
    assert result.format == "pdb"
    assert result.model_count == 1
    assert len(result.chains) > 0
    assert result.atoms > 0


@pytest.mark.asyncio
async def test_list_protocols(adapter):
    protocols = await adapter.list_protocols()
    assert len(protocols) > 0
    assert all(p.name for p in protocols)


@pytest.mark.asyncio
async def test_describe_protocol(adapter):
    desc = await adapter.describe_protocol("Prepare Protein")
    assert desc.name == "Prepare Protein"
    assert len(desc.parameters) > 0
    assert desc.requires_server is True


@pytest.mark.asyncio
async def test_describe_unknown_protocol(adapter):
    desc = await adapter.describe_protocol("NonexistentProtocol")
    assert desc.name == "NonexistentProtocol"


@pytest.mark.asyncio
async def test_run_protocol(adapter):
    request = RunProtocolRequest(
        protocol_name="Prepare Protein",
        parameters={"pH": "7.4"},
    )
    result = await adapter.run_protocol(request)
    assert result.status == JobStatus.COMPLETED
    assert len(result.warnings) > 0  # mock warning


@pytest.mark.asyncio
async def test_get_job_status(adapter):
    result = await adapter.get_job_status("test-job-id")
    assert result.job_id == "test-job-id"
    assert result.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancel_job(adapter):
    assert await adapter.cancel_job("test-job-id") is True


@pytest.mark.asyncio
async def test_list_jobs(adapter):
    jobs = await adapter.list_jobs()
    assert isinstance(jobs, list)


@pytest.mark.asyncio
async def test_convert_structure(adapter):
    request = ConvertStructureRequest(
        input_path="/test/input.pdb",
        output_format="mol",
    )
    result = await adapter.convert_structure(request)
    assert "output" in result or "." in result


@pytest.mark.asyncio
async def test_render_structure(adapter):
    request = RenderStructureRequest(
        molecule_path="/test/1abc.pdb",
        representation="ball_and_stick",
    )
    result = await adapter.render_structure(request)
    assert "mock" in result.lower() or ".png" in result.lower()
