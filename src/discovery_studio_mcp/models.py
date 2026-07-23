"""Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class AdapterStatus(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    NOT_FOUND = "not_found"
    REQUIRES_LICENSE = "requires_license"
    REQUIRES_MANUAL_CHECK = "requires_manual_check"
    NOT_APPLICABLE = "not_applicable"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class AdapterInfo(BaseModel):
    name: str
    status: AdapterStatus
    description: str
    version: str | None = None
    limitations: list[str] = Field(default_factory=list)


class DsCapabilities(BaseModel):
    mock: bool = False
    discovery_studio_version: str
    discovery_studio_build: str
    discovery_studio_root: str
    perl_version: str | None = None
    available_adapters: list[AdapterInfo] = Field(default_factory=list)
    pipeline_pilot_available: bool = False
    pipeline_pilot_server: str | None = None
    discovery_script_available: bool = False
    supported_formats: list[str] = Field(default_factory=list)
    license_mode: str | None = None
    max_concurrent_jobs: int = 1
    job_timeout_seconds: int = 3600
    ui_fallback_enabled: bool = False


class StructureInspection(BaseModel):
    mock: bool = False
    file_path: str
    format: str | None = None
    model_count: int = 0
    chains: list[str] = Field(default_factory=list)
    residues: int = 0
    atoms: int = 0
    ligands: list[str] = Field(default_factory=list)
    waters: int = 0
    metals: list[str] = Field(default_factory=list)
    heteroatoms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProtocolInfo(BaseModel):
    name: str
    description: str
    category: str | None = None
    required_parameters: list[str] = Field(default_factory=list)
    optional_parameters: list[str] = Field(default_factory=list)
    requires_server: bool = True
    requires_license: bool | None = None


class ProtocolParameter(BaseModel):
    name: str
    type: str
    required: bool = False
    default_value: str | None = None
    description: str | None = None


class ProtocolDescription(BaseModel):
    name: str
    description: str
    category: str | None = None
    parameters: list[ProtocolParameter] = Field(default_factory=list)
    requires_server: bool = True
    requires_license: bool | None = None


class RunProtocolRequest(BaseModel):
    protocol_name: str
    parameters: dict[str, str] = Field(default_factory=dict)
    input_files: list[str] = Field(default_factory=list)
    confirm_destructive_action: bool = False


class ConvertStructureRequest(BaseModel):
    input_path: str
    output_format: str
    output_path: str | None = None


class RenderStructureRequest(BaseModel):
    molecule_path: str
    representation: str = "ball_and_stick"
    width: int = 800
    height: int = 600
    output_format: str = "png"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    status_message: str | None = None
    result_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    manifest_path: str | None = None


class HealthCheckResult(BaseModel):
    mock: bool = False
    status: str = "unknown"
    checks: list[dict[str, str]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
