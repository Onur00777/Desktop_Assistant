"""Çalışma alanı profilleri: uygulama, klasör, site ve arka plan işlemi."""

from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from pathlib import Path

import psutil

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_BLOCKED = {
    "system",
    "registry",
    "csrss.exe",
    "lsass.exe",
    "winlogon.exe",
    "services.exe",
    "smss.exe",
    "wininit.exe",
    "svchost.exe",
    "explorer.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "securityhealthservice.exe",
    "msmpeng.exe",
    "csrss",
    "lsass",
    "winlogon",
    "services",
    "smss",
    "wininit",
    "svchost",
    "explorer",
    "dwm",
}


def _clean_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"workspaces.json okunamadı: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("workspaces.json bir nesne olmalı.")
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError("profiles alanı bir liste olmalı.")
    data["profiles"] = profiles
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _blocked(name: str) -> bool:
    key = name.strip().lower()
    if key in _BLOCKED:
        return True
    if not key.endswith(".exe") and f"{key}.exe" in _BLOCKED:
        return True
    return False


def _same_process(proc_name: str, target: str) -> bool:
    proc = proc_name.lower()
    wanted = target.lower()
    if proc == wanted:
        return True
    if not wanted.endswith(".exe"):
        return proc == f"{wanted}.exe"
    return False


class WorkspaceManager:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def list_profiles(self) -> list[dict]:
        profiles: list[dict] = []
        for profile in self._load()["profiles"]:
            if not isinstance(profile, dict):
                continue
            profiles.append(
                {
                    "name": str(profile.get("name") or "").strip(),
                    "apps": _clean_list(profile.get("apps")),
                    "folders": _clean_list(profile.get("folders")),
                    "urls": _clean_list(profile.get("urls")),
                    "kill": _clean_list(profile.get("kill")),
                }
            )
        return [profile for profile in profiles if profile["name"]]

    def add_profile(self, profile: dict) -> None:
        name = str(profile.get("name") or "").strip()
        if not name:
            raise ValueError("Profil adı gerekli.")
        data = self._load()
        if any(str(item.get("name") or "").strip().casefold() == name.casefold() for item in data["profiles"] if isinstance(item, dict)):
            raise ValueError(f"Bu isimde bir profil zaten var: {name}")
        data["profiles"].append(
            {
                "name": name,
                "apps": _clean_list(profile.get("apps")),
                "folders": _clean_list(profile.get("folders")),
                "urls": _clean_list(profile.get("urls")),
                "kill": _clean_list(profile.get("kill")),
            }
        )
        _write_json(self.path, data)

    def remove_profile(self, name: str) -> bool:
        data = self._load()
        kept = [
            item
            for item in data["profiles"]
            if not (isinstance(item, dict) and str(item.get("name") or "") == name)
        ]
        if len(kept) == len(data["profiles"]):
            return False
        data["profiles"] = kept
        _write_json(self.path, data)
        return True

    def activate(self, name: str) -> dict[str, list[str]]:
        profile = next((item for item in self.list_profiles() if item["name"] == name), None)
        if profile is None:
            raise ValueError(f"Profil yok: {name}")
        launched: list[str] = []
        errors: list[str] = []
        for app in profile["apps"]:
            try:
                _launch_app(app)
                launched.append(app)
            except Exception as exc:
                errors.append(f"{app}: {exc}")
        for folder in profile["folders"]:
            try:
                _launch_folder(folder)
                launched.append(folder)
            except Exception as exc:
                errors.append(f"{folder}: {exc}")
        for url in profile["urls"]:
            try:
                _launch_url(url)
                launched.append(url)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        killed, kill_errors = _close_processes(profile["kill"])
        errors.extend(kill_errors)
        return {"launched": launched, "killed": killed, "errors": errors}

    def _load(self) -> dict:
        if not self.path.exists():
            return {"profiles": []}
        return _read_json(self.path)


def _launch_app(target: str) -> None:
    command = target.strip().strip('"')
    if not command:
        raise ValueError("boş uygulama")
    path = Path(command)
    if path.exists():
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)
        return
    if os.name == "nt":
        subprocess.Popen(
            ["cmd", "/c", "start", "", command],
            creationflags=_CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    subprocess.Popen(command, shell=True, start_new_session=True)


def _launch_folder(folder: str) -> None:
    path = Path(folder.strip().strip('"'))
    if not path.exists():
        raise FileNotFoundError(f"klasör yok: {path}")
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)], start_new_session=True)


def _launch_url(url: str) -> None:
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    if not webbrowser.open(target):
        raise RuntimeError(f"tarayıcı açılmadı: {target}")


def _close_processes(names: list[str]) -> tuple[list[str], list[str]]:
    killed: list[str] = []
    errors: list[str] = []
    targets: list[str] = []
    for name in names:
        if _blocked(name):
            errors.append(f"sistem işlemi korunuyor: {name}")
            continue
        targets.append(name)
    if not targets:
        return killed, errors
    own_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_name = proc.info["name"] or ""
            pid = int(proc.info["pid"])
        except (psutil.Error, TypeError, ValueError):
            continue
        if pid == own_pid or not proc_name:
            continue
        if not any(_same_process(proc_name, target) for target in targets):
            continue
        try:
            proc.terminate()
            killed.append(proc_name)
        except psutil.Error as exc:
            errors.append(f"{proc_name}: {exc}")
    return killed, errors
