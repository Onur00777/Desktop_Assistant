"""Create Desktop and Start Menu shortcuts that launch the assistant without a console.

Run again after moving the project folder:
    py -3 install_shortcut.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent
ICON_PATH = ROOT / "assets" / "app.ico"
NAME = "Desktop Assistant"


def build_icon() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.bot_icon import render_app_icon

    if not render_app_icon(256).pixmap(256, 256).save(str(ICON_PATH), "ICO"):
        raise RuntimeError(f"Could not write {ICON_PATH}")
    del app


def windowless_python() -> Path:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return pythonw if pythonw.exists() else Path(sys.executable)


def create_shortcut(folder: str) -> str:
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$folder = [Environment]::GetFolderPath('{folder}'); "
        f"$link = $shell.CreateShortcut((Join-Path $folder '{NAME}.lnk')); "
        f"$link.TargetPath = '{windowless_python()}'; "
        f"$link.Arguments = '\"{ROOT / 'main.py'}\"'; "
        f"$link.WorkingDirectory = '{ROOT}'; "
        f"$link.IconLocation = '{ICON_PATH},0'; "
        "$link.Description = 'Desktop Assistant'; "
        "$link.Save(); "
        "$link.FullName"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Shortcut could not be created.")
    return result.stdout.strip()


def main() -> int:
    if os.name != "nt":
        print("Shortcuts are only created on Windows.")
        return 1
    build_icon()
    for folder in ("Desktop", "Programs"):
        print("Created", create_shortcut(folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
