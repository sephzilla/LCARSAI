"""Application configuration and data-root discovery."""
from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Computer"


def default_data_dir() -> Path:
    """Return an OS-appropriate per-user data directory.

    This is a safe default for development, not the future cross-OS shared vault.
    The shared vault should be explicitly selected in setup and checked for
    filesystem health before any writes are attempted.
    """
    override = os.environ.get("LCARSAI_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "LCARSAI" / "Data"
        return Path.home() / "AppData" / "Local" / "LCARSAI" / "Data"

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / "lcarsai"
    return Path.home() / ".local" / "share" / "lcarsai"


def ensure_private_directory(path: Path) -> Path:
    """Create a local directory if needed, using restrictive POSIX permissions.

    Do not call this against a shared NTFS vault until mount/hibernation checks
    and encryption initialization are implemented.
    """
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError:
            # Permission hardening is best-effort on filesystems that do not
            # expose POSIX mode bits. Callers should surface stronger failures.
            pass
    return path
