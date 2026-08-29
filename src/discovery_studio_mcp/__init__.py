"""Discovery Studio MCP Server - Programmatic automation for BIOVIA Discovery Studio."""

# A plain literal, deliberately. Deriving this from importlib.metadata looks tidier but
# is wrong here: `run_server.py` puts `src/` on sys.path, and a stale
# `src/discovery_studio_mcp.egg-info` left by an earlier setuptools install is found
# first, so metadata resolution reported 0.1.0 from a build artifact rather than the
# real version. The gateway spawns this connector as `python3 run_server.py` from an
# extracted package that is never pip-installed, so the literal is the only value that
# is always correct.
#
# This is what the server reports over MCP `initialize`. Keep it equal to
# pyproject.toml and manifest.json; it was 0.1.0 here while both of those said 1.0.0.
__version__ = "1.0.0"
