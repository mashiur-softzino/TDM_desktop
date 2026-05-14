"""
Shared filesystem paths for installed and development runs.
"""

import os
import shutil
from pathlib import Path

COMPANY_NAME = "Softzino"
APP_NAME = "AUC-Sampler"


def app_base_dir() -> Path:
    """Directory containing source files in dev, or bundled files when frozen."""
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_base_dir() -> Path:
    """Directory containing read-only bundled resources."""
    import sys

    return Path(getattr(sys, "_MEIPASS", app_base_dir()))


def asset_path(*parts: str) -> Path:
    """Resolve an application asset from assets/ with legacy root fallback."""
    rel = Path(*parts)
    if rel.is_absolute():
        return rel

    bundled = bundled_base_dir()
    dev_base = app_base_dir()
    candidates = [
        bundled / "assets" / rel,
        bundled / rel,
        dev_base / "assets" / rel,
        dev_base / rel,
    ]
    return next((path for path in candidates if path.exists()), candidates[0])


def data_dir() -> Path:
    """
    Writable application data folder.

    On Windows this resolves to C:\\ProgramData\\Softzino\\AUC-Sampler.
    For development/non-Windows runs it falls back to the project directory.
    """
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        path = Path(program_data) / COMPANY_NAME / APP_NAME
    else:
        path = app_base_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_data_dirs() -> Path:
    root = data_dir()
    for child in ("logs", "generated_reports", "config", "backups", "signatures"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def log_dir() -> Path:
    return ensure_data_dirs() / "logs"


def reports_dir() -> Path:
    path = ensure_data_dirs() / "generated_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def license_file() -> Path:
    return ensure_data_dirs() / "license.json"


def backups_dir() -> Path:
    path = ensure_data_dirs() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_file(filename: str, destination: Path) -> None:
    """
    Move a writable file from older app-folder storage into ProgramData.

    Existing ProgramData files win, so installer upgrades do not overwrite data.
    """
    candidates = [
        app_base_dir() / filename,
        app_base_dir() / "_internal" / filename,
    ]
    legacy = next((path for path in candidates if path.exists()), None)
    if destination.exists() or legacy is None:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, destination)
