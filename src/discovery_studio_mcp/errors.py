"""Custom exceptions for the Discovery Studio MCP server."""


class DiscoveryStudioError(Exception):
    """Base exception for all Discovery Studio MCP errors."""


class ConfigurationError(DiscoveryStudioError):
    """Configuration is invalid or missing."""


class DiscoveryStudioNotFoundError(DiscoveryStudioError):
    """Discovery Studio installation not found."""


class ProtocolNotFoundError(DiscoveryStudioError):
    """The requested protocol was not found."""


class ProtocolExecutionError(DiscoveryStudioError):
    """A protocol failed during execution."""


class JobNotFoundError(DiscoveryStudioError):
    """The requested job was not found."""


class JobTimeoutError(DiscoveryStudioError):
    """A job exceeded its maximum allowed runtime."""


class SecurityViolationError(DiscoveryStudioError):
    """A security policy was violated."""


class PathTraversalError(SecurityViolationError):
    """Path traversal attack detected."""


class UnauthorizedDirectoryError(SecurityViolationError):
    """Access to an unauthorized directory was attempted."""


class FileSizeLimitError(SecurityViolationError):
    """File exceeds the maximum allowed size."""


class UnsupportedFormatError(DiscoveryStudioError):
    """The requested file format is not supported."""


class LicenseRequiredError(DiscoveryStudioError):
    """A required license is not available."""


class PipelinePilotConnectionError(DiscoveryStudioError):
    """Could not connect to Pipeline Pilot Server."""


class UiFallbackDisabledError(DiscoveryStudioError):
    """UI fallback is disabled but the operation requires GUI."""


class AdapterNotAvailableError(DiscoveryStudioError):
    """The requested adapter is not available in the current environment."""


class ValidationError(DiscoveryStudioError):
    """Input validation failed."""
