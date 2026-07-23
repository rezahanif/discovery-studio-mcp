"""Configuration management for the Discovery Studio MCP server."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Server configuration loaded from environment variables and .env file."""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    # Discovery Studio paths
    ds_home: str = r"C:\Program Files\BIOVIA\Discovery Studio 2020"
    ds_executable: str = r"C:\Program Files\BIOVIA\Discovery Studio 2020\bin\DiscoveryStudio2020.exe"
    ds_perl_executable: str = r"C:\Program Files\BIOVIA\Discovery Studio 2020\bin\perl.exe"

    # Pipeline Pilot
    ds_pipeline_pilot_url: str = ""
    ds_pipeline_pilot_username: str = ""
    ds_pipeline_pilot_password: str = ""

    # Security
    ds_allowed_input_dirs: str = ""
    ds_output_dir: str = "./workspace"
    ds_max_file_size_mb: int = 500
    ds_max_concurrent_jobs: int = 1
    ds_job_timeout_seconds: int = 3600

    # Features
    ds_enable_ui_fallback: bool = False
    ds_mock_mode: bool = True

    @property
    def allowed_input_dirs(self) -> list[Path]:
        dirs = self.ds_allowed_input_dirs
        if not dirs:
            home = os.path.expanduser("~")
            return [Path(home) / "Documents"]
        return [Path(d.strip()) for d in dirs.split(";") if d.strip()]

    @property
    def output_path(self) -> Path:
        path = Path(self.ds_output_dir)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def permit_script_running_in_client(self) -> bool:
        """Whether scripts can be run inside the Discovery Studio client process."""
        return os.path.isfile(self.ds_executable)

    @property
    def permit_cli_perl(self) -> bool:
        """Whether Perl scripts can be run from command line."""
        return os.path.isfile(self.ds_perl_executable)

    @property
    def has_pipeline_pilot(self) -> bool:
        return bool(self.ds_pipeline_pilot_url)


settings = Settings()
