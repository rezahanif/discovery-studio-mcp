"""Configuration management for the Discovery Studio MCP server."""

import os
import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings


def _detect_ds_paths() -> tuple[str, str, str, bool]:
    candidates = [
        r"C:\Program Files\BIOVIA",
        r"C:\Program Files\Dassault Systemes",
        r"C:\Program Files (x86)\BIOVIA",
        r"C:\Program Files (x86)\Dassault Systemes",
    ]
    for base in candidates:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base), reverse=True):
            if "discovery studio" in name.lower():
                home = os.path.join(base, name)
                bin_dir = os.path.join(home, "bin")
                if os.path.isdir(bin_dir):
                    perl_exe = os.path.join(bin_dir, "perl.exe")
                    ds_exes = [
                        f for f in os.listdir(bin_dir)
                        if f.lower().startswith("discoverystudio") and f.lower().endswith(".exe")
                    ]
                    ds_exe = os.path.join(bin_dir, ds_exes[0]) if ds_exes else ""
                    return home, ds_exe, perl_exe, False
    return (
        r"C:\Program Files\BIOVIA\Discovery Studio 2020",
        r"C:\Program Files\BIOVIA\Discovery Studio 2020\bin\DiscoveryStudio2020.exe",
        r"C:\Program Files\BIOVIA\Discovery Studio 2020\bin\perl.exe",
        True,
    )


_default_ds_home, _default_ds_exe, _default_ds_perl, _default_mock = _detect_ds_paths()


class Settings(BaseSettings):
    """Server configuration loaded from environment variables and .env file."""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    # Discovery Studio paths
    ds_home: str = _default_ds_home
    ds_executable: str = _default_ds_exe
    ds_perl_executable: str = _default_ds_perl

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
    ds_mock_mode: bool = _default_mock

    @property
    def allowed_input_dirs(self) -> list[Path]:
        dirs = self.ds_allowed_input_dirs
        res: list[Path] = []
        if dirs:
            res = [Path(d.strip()) for d in dirs.split(";") if d.strip()]
        else:
            home = os.path.expanduser("~")
            res = [Path(home), Path(tempfile.gettempdir()), Path.cwd()]
        if os.path.isdir(self.ds_home):
            res.append(Path(self.ds_home))
        return res

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
