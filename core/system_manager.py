"""CPU, bellek, disk, pil ve Windows güç planları."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

LOW_BATTERY_PERCENT = 20
LOW_DISK_FREE_PERCENT = 5

PLANS: dict[str, dict[str, str]] = {
    "saver": {
        "guid": "a1841308-3541-4fab-bc81-f71556f20b4a",
        "label": "Güç Tasarrufu",
    },
    "balanced": {
        "guid": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "label": "Dengeli",
    },
    "performance": {
        "guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "label": "Yüksek Performans",
    },
}

_GUID_TO_ID = {plan["guid"]: key for key, plan in PLANS.items()}
_GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_SCHEME_RE = re.compile(
    r"(" + _GUID_RE.pattern + r")\s+\(([^)]+)\)"
)
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _plan_id_from_name(name: str) -> str:
    folded = name.strip().casefold()
    exact = {
        "power saver": "saver",
        "güç tasarrufu": "saver",
        "balanced": "balanced",
        "dengeli": "balanced",
        "high performance": "performance",
        "yüksek performans": "performance",
    }
    if folded in exact:
        return exact[folded]
    if "ultimate" in folded or "en yüksek" in folded:
        return ""
    if "güç tasarrufu" in folded or folded.startswith("power saver"):
        return "saver"
    if "yüksek performans" in folded or "high performance" in folded:
        return "performance"
    return ""


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.count(b"\x00") > len(data) // 4:
        return data.decode("utf-16-le", errors="replace")
    for encoding in ("utf-8", "oem", "cp857", "cp1254", "mbcs"):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


class SystemManager:
    def __init__(self, schemes_path: Path | None = None) -> None:
        self.schemes_path = Path(schemes_path) if schemes_path else None
        self._battery_latched = False
        self._disk_latched = False
        self._power_cache: tuple[float, dict[str, str] | None] | None = None
        self._resolved = self._load_resolved()
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def snapshot(self, refresh_power: bool = False) -> dict[str, Any]:
        return {
            "cpu": self.cpu_percent(),
            "memory": self.memory(),
            "disk": self.disk(),
            "battery": self.battery(),
            "power_plan": self.active_power_plan(refresh=refresh_power),
        }

    def cpu_percent(self) -> float:
        try:
            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return 0.0

    def memory(self) -> dict[str, float]:
        try:
            info = psutil.virtual_memory()
        except Exception:
            return {"percent": 0.0, "used": 0.0, "total": 0.0}
        return {
            "percent": float(info.percent),
            "used": float(info.used),
            "total": float(info.total),
        }

    def disk(self) -> dict[str, float | str]:
        mount = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        try:
            usage = psutil.disk_usage(mount)
        except Exception:
            return {"percent": 0.0, "used": 0.0, "total": 0.0, "free": 0.0, "mount": mount}
        return {
            "percent": float(usage.percent),
            "used": float(usage.used),
            "total": float(usage.total),
            "free": float(usage.free),
            "mount": mount,
        }

    def battery(self) -> dict[str, Any] | None:
        try:
            info = psutil.sensors_battery()
        except Exception:
            return None
        if info is None:
            return None
        seconds = info.secsleft
        if seconds is None or seconds < 0:
            seconds = None
        return {
            "percent": float(info.percent),
            "plugged": bool(info.power_plugged),
            "secs_left": seconds,
        }

    def active_power_plan(self, refresh: bool = False) -> dict[str, str] | None:
        now = time.monotonic()
        if not refresh and self._power_cache is not None:
            return self._power_cache[1]
        plan = self._query_active_plan()
        self._power_cache = (now, plan)
        return plan

    def set_power_plan(self, plan_id: str) -> tuple[bool, str]:
        plan = PLANS.get(plan_id)
        if plan is None:
            return False, "Bilinmeyen güç planı."
        if os.name != "nt":
            return False, "Güç planı yalnızca Windows üzerinde değiştirilebilir."
        guid = self._resolve_guid(plan_id)
        if not guid:
            return False, f"{plan['label']} şeması bulunamadı."
        result = self._powercfg(["/setactive", guid])
        self._power_cache = None
        if result is None or result.returncode != 0:
            detail = ""
            if result is not None:
                detail = (result.stderr or result.stdout).strip()
            return False, detail or "Güç planı değiştirilemedi."
        self.active_power_plan(refresh=True)
        return True, f"{plan['label']} etkin."

    def consume_alerts(self, stats: dict[str, Any]) -> list[tuple[str, str]]:
        alerts: list[tuple[str, str]] = []
        battery = stats.get("battery")
        if isinstance(battery, dict):
            low = (not battery.get("plugged")) and float(battery.get("percent") or 0) <= LOW_BATTERY_PERCENT
            if low and not self._battery_latched:
                self._battery_latched = True
                percent = float(battery.get("percent") or 0)
                ok, detail = self.set_power_plan("saver")
                if ok:
                    alerts.append(("SİSTEM", f"Pil %{percent:.0f}. Güç tasarrufu planına geçildi."))
                else:
                    alerts.append(("SİSTEM", f"Pil %{percent:.0f}. Plan değiştirilemedi: {detail}"))
            elif not low:
                self._battery_latched = False

        disk = stats.get("disk") if isinstance(stats.get("disk"), dict) else {}
        total = float(disk.get("total") or 0)
        free = float(disk.get("free") or 0)
        if total > 0:
            free_pct = free / total * 100
            if free_pct <= LOW_DISK_FREE_PERCENT and not self._disk_latched:
                self._disk_latched = True
                mount = disk.get("mount") or ""
                alerts.append(
                    ("SİSTEM", f"Disk alanı az: {free / (1024 ** 3):.1f} GB boş ({mount}).")
                )
            elif free_pct > LOW_DISK_FREE_PERCENT + 2:
                self._disk_latched = False
        return alerts

    def _resolve_guid(self, plan_id: str) -> str | None:
        template = PLANS[plan_id]["guid"]
        saved = self._resolved.get(plan_id, "")
        if saved and self._guid_exists(saved):
            return saved
        schemes = self._list_schemes()
        for guid, _name in schemes:
            if guid == template:
                return self._remember(plan_id, guid)
        for guid, name in schemes:
            if _plan_id_from_name(name) == plan_id:
                return self._remember(plan_id, guid)
        created = self._powercfg(["/duplicatescheme", template])
        if created is None or created.returncode != 0:
            return None
        found = [guid.lower() for guid in _GUID_RE.findall(created.stdout or "")]
        fresh = [guid for guid in found if guid != template]
        chosen = (fresh or found or [None])[-1]
        if not chosen:
            return None
        return self._remember(plan_id, chosen)

    def _guid_exists(self, guid: str) -> bool:
        result = self._powercfg(["/query", guid])
        return result is not None and result.returncode == 0

    def _remember(self, plan_id: str, guid: str) -> str:
        self._resolved[plan_id] = guid.lower()
        self._save_resolved()
        return self._resolved[plan_id]

    def _load_resolved(self) -> dict[str, str]:
        if self.schemes_path is None or not self.schemes_path.exists():
            return {}
        try:
            data = json.loads(self.schemes_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        resolved: dict[str, str] = {}
        for key, value in data.items():
            if key in PLANS and isinstance(value, str) and _GUID_RE.fullmatch(value.strip()):
                resolved[key] = value.strip().lower()
        return resolved

    def _save_resolved(self) -> None:
        if self.schemes_path is None:
            return
        self.schemes_path.parent.mkdir(parents=True, exist_ok=True)
        self.schemes_path.write_text(
            json.dumps(self._resolved, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _list_schemes(self) -> list[tuple[str, str]]:
        result = self._powercfg(["/list"])
        if result is None:
            return []
        return [(guid.lower(), name.strip()) for guid, name in _SCHEME_RE.findall(result.stdout or "")]

    def _query_active_plan(self) -> dict[str, str] | None:
        if os.name != "nt":
            return None
        result = self._powercfg(["/getactivescheme"])
        if result is None or result.returncode != 0:
            return None
        match = _SCHEME_RE.search(result.stdout or "")
        if match is None:
            return None
        guid = match.group(1).lower()
        name = match.group(2).strip()
        plan_id = _GUID_TO_ID.get(guid) or _plan_id_from_name(name)
        label = PLANS[plan_id]["label"] if plan_id else name
        return {"id": plan_id, "guid": guid, "label": label}

    def _powercfg(self, args: list[str]) -> subprocess.CompletedProcess[str] | None:
        if os.name != "nt":
            return None
        try:
            raw = subprocess.run(
                ["powercfg", *args],
                capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return subprocess.CompletedProcess(
            raw.args,
            raw.returncode,
            _decode_output(raw.stdout),
            _decode_output(raw.stderr),
        )
