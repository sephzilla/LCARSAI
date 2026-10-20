"""Per-user OS-login startup integration for Computer."""
from __future__ import annotations

import os
import shlex
import sys
import subprocess
from pathlib import Path


APP_NAME = "Computer"


def _command() -> str:
    if sys.platform == "win32":
        if getattr(sys, "frozen", False):
            return subprocess.list2cmdline([str(Path(sys.executable).resolve())])
        return subprocess.list2cmdline([sys.executable, "-m", "lcarsai.main"])
    if getattr(sys, "frozen", False):
        return shlex.quote(str(Path(sys.executable).resolve()))
    return shlex.quote(sys.executable) + " -m lcarsai.main"


def set_startup_enabled(enabled: bool) -> None:
    """Enable or disable launch at login without administrator privileges."""
    if sys.platform == "win32":
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            if enabled:
                winreg.SetValueEx(key, "ComputerLCARS", 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, "ComputerLCARS")
                except FileNotFoundError:
                    pass
        return

    if sys.platform.startswith("linux"):
        autostart = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
        entry = autostart / "computer-lcars.desktop"
        if enabled:
            autostart.mkdir(parents=True, exist_ok=True)
            entry.write_text(
                "[Desktop Entry]\nType=Application\nName=Computer\n"
                "Comment=Local voice-first LCARS assistant\n"
                f"Exec={_command()}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            entry.unlink(missing_ok=True)
        return

    raise RuntimeError("Automatic login startup is supported on Windows and Linux only.")
