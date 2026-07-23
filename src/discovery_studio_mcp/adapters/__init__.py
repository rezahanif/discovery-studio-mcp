"""Adapter initialization and selection."""

from discovery_studio_mcp.adapters.base import DiscoveryStudioAdapter
from discovery_studio_mcp.adapters.discovery_script import DiscoveryScriptAdapter
from discovery_studio_mcp.adapters.filesystem import FilesystemAdapter
from discovery_studio_mcp.adapters.mock import MockAdapter
from discovery_studio_mcp.config import settings


def get_adapter() -> DiscoveryStudioAdapter:
    """Select the appropriate adapter based on configuration."""
    if settings.ds_mock_mode:
        return MockAdapter()
    elif DiscoveryScriptAdapter().is_available():
        return DiscoveryScriptAdapter()
    else:
        return FilesystemAdapter()
