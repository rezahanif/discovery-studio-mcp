"""Security module for path validation, file size checks, and access control."""

import os
from pathlib import Path

from discovery_studio_mcp.config import settings
from discovery_studio_mcp.errors import (
    FileSizeLimitError,
    PathTraversalError,
    UnauthorizedDirectoryError,
)


def validate_path(path: str | Path, must_exist: bool = False) -> Path:
    """
    Validate a path for security:
    - Resolve to absolute
    - Check for path traversal
    - Check against allowed directories
    """
    resolved = Path(path).resolve()

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    if must_exist and not _is_in_allowed_dirs(resolved):
        raise UnauthorizedDirectoryError(
            f"Path is not in allowed input directories: {resolved}. "
            f"Allowed: {settings.allowed_input_dirs}"
        )

    return resolved


def validate_output_path(path: str | Path) -> Path:
    """Validate that an output path is within the configured output directory."""
    resolved = Path(path).resolve()
    output_root = settings.output_path.resolve()

    try:
        resolved.relative_to(output_root)
    except ValueError:
        raise UnauthorizedDirectoryError(
            f"Output path must be within: {output_root}"
        )

    return resolved


def validate_file_size(path: Path) -> None:
    """Check that file size is within limits."""
    if not path.is_file():
        return
    limit_bytes = settings.ds_max_file_size_mb * 1024 * 1024
    actual = path.stat().st_size
    if actual > limit_bytes:
        raise FileSizeLimitError(
            f"File size {actual} exceeds limit of {limit_bytes} bytes "
            f"({settings.ds_max_file_size_mb} MB)"
        )


def sanitize_filename(name: str) -> str:
    """Remove path traversal characters from a filename."""
    return os.path.basename(name).replace("\\", "_").replace("/", "_")


def is_safe_extension(filename: str, allowed: set[str] | None = None) -> bool:
    """Check file extension against allowed set."""
    ext = Path(filename).suffix.lower()
    if allowed is None:
        allowed = {".pdb", ".mol", ".mol2", ".sdf", ".sd", ".msv", ".dsv",
                   ".cif", ".dsx", ".csv", ".car", ".msi", ".xyz", ".smi",
                   ".txt", ".log", ".json", ".png", ".jpg"}
    return ext in allowed


def _is_in_allowed_dirs(path: Path) -> bool:
    """Check if path is under one of the allowed input directories."""
    for allowed in settings.allowed_input_dirs:
        try:
            path.relative_to(allowed.resolve())
            return True
        except ValueError:
            continue
    return False
