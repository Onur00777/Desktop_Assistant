"""CPU, memory, disk, battery, processes, Windows power plans and brightness."""

from __future__ import annotations

import ctypes
import json
import os
import re
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psutil

LOW_BATTERY_PERCENT = 20
LOW_DISK_FREE_PERCENT = 5

PLANS: dict[str, dict[str, Any]] = {
    "saver": {
        "guid": "a1841308-3541-4fab-bc81-f71556f20b4a",
        "label": "Power Saver",
        "brightness": 35,
    },
    "balanced": {
        "guid": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "label": "Balanced",
        "brightness": 65,
    },
    "performance": {
        "guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "label": "Performance",
        "brightness": 100,
    },
}

PROTECTED_PROCESSES = {
    "system",
    "registry",
    "secure system",
    "memory compression",
    "csrss.exe",
    "lsass.exe",
    "lsaiso.exe",
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
    "audiodg.exe",
    "conhost.exe",
}

_GUID_TO_ID = {plan["guid"]: key for key, plan in PLANS.items()}
_GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_SCHEME_RE = re.compile(r"(" + _GUID_RE.pattern + r")\s+\(([^)]+)\)")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# psutil reads each process separately; on Windows that costs seconds of CPU per sweep.
# One SystemProcessInformation query returns the whole table in a few milliseconds.
_NT_TABLE = os.name == "nt" and struct.calcsize("P") == 8
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


def is_protected_process(name: str) -> bool:
    key = name.strip().lower()
    if key in PROTECTED_PROCESSES:
        return True
    return not key.endswith(".exe") and f"{key}.exe" in PROTECTED_PROCESSES


def power_impact(cpu: float, ram_percent: float) -> str:
    score = cpu + ram_percent * 0.25
    if score >= 15:
        return "Very High"
    if score >= 6:
        return "High"
    if score >= 1.5:
        return "Medium"
    return "Low"


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
        self._auto_plan = ""
        self._power_cache: tuple[float, dict[str, str] | None] | None = None
        self._power_lock = threading.Lock()
        self._resolved = self._load_resolved()
        self._proc_prev: dict[tuple[int, int], float] = {}
        self._proc_prev_at = 0.0
        self._nt_buffer = ctypes.create_string_buffer(1 << 20) if _NT_TABLE else None
        self._cpu_count = psutil.cpu_count() or 1
        try:
            self._ram_total = float(psutil.virtual_memory().total)
        except Exception:
            self._ram_total = 0.0
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

    def top_processes(self, limit: int = 6) -> list[dict[str, Any]]:
        now = time.monotonic()
        table = self._nt_process_table() if _NT_TABLE else None
        if table is None:
            table = self._psutil_process_table()
        elapsed = now - self._proc_prev_at if self._proc_prev_at else 0.0
        own_pid = os.getpid()
        groups: dict[str, dict[str, Any]] = {}
        current: dict[tuple[int, int], float] = {}
        for pid, created, name, cpu_seconds, memory in table:
            if pid == 0 or not name:
                continue
            key = (pid, created)
            current[key] = cpu_seconds
            previous = self._proc_prev.get(key)
            cpu = 0.0
            if previous is not None and elapsed > 0:
                cpu = max(0.0, cpu_seconds - previous) / (elapsed * self._cpu_count) * 100
            group = groups.setdefault(
                name.lower(),
                {"name": name, "count": 0, "cpu": 0.0, "ram": 0.0, "pids": [], "own": True},
            )
            group["count"] += 1
            group["cpu"] += cpu
            group["ram"] += memory
            group["pids"].append(pid)
            if pid != own_pid:
                group["own"] = False
        self._proc_prev = current
        self._proc_prev_at = now

        rows: list[dict[str, Any]] = []
        for group in groups.values():
            ram_percent = group["ram"] / self._ram_total * 100 if self._ram_total else 0.0
            cpu = min(100.0, group["cpu"])
            rows.append(
                {
                    "name": group["name"],
                    "count": group["count"],
                    "cpu": cpu,
                    "ram_mb": group["ram"] / (1024 * 1024),
                    "ram_percent": ram_percent,
                    "impact": power_impact(cpu, ram_percent),
                    "score": cpu + ram_percent * 0.25,
                    "protected": is_protected_process(group["name"]) or group["own"],
                }
            )
        rows.sort(key=lambda row: row["score"], reverse=True)
        return rows[:limit]

    def end_process_group(self, name: str) -> tuple[bool, str]:
        if is_protected_process(name):
            return False, f"{name} is a protected system process."
        own_pid = os.getpid()
        ended = 0
        denied = 0
        target = name.lower()
        for proc in psutil.process_iter(["pid", "name"]):
            proc_name = (proc.info.get("name") or "").lower()
            if proc_name != target or proc.info.get("pid") == own_pid:
                continue
            try:
                proc.terminate()
                ended += 1
            except psutil.AccessDenied:
                denied += 1
            except psutil.Error:
                continue
        if ended:
            plural = "process" if ended == 1 else "processes"
            suffix = f" ({denied} need admin rights)" if denied else ""
            return True, f"Ended {name} • {ended} {plural}{suffix}"
        if denied:
            return False, f"Access denied to {name}. Run the assistant as administrator."
        return False, f"{name} is no longer running."

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
            return False, "Unknown power plan."
        if os.name != "nt":
            return False, "Power plans can only be changed on Windows."
        with self._power_lock:
            guid = self._resolve_guid(plan_id)
            if not guid:
                return False, f"{plan['label']} scheme not found."
            level = int(plan["brightness"])
            # Each Windows plan stores its own display brightness and applies it on activation.
            for index in ("/setacvalueindex", "/setdcvalueindex"):
                self._powercfg([index, guid, "SUB_VIDEO", "VIDEONORMALLEVEL", str(level)])
            result = self._powercfg(["/setactive", guid])
            self._power_cache = None
            if result is None or result.returncode != 0:
                detail = ""
                if result is not None:
                    detail = (result.stderr or result.stdout).strip()
                return False, detail or "Could not change the power plan."
            applied = self.set_brightness(level)
            self.active_power_plan(refresh=True)
        if applied is None:
            return True, f"{plan['label']} active • Brightness control not supported on this display"
        return True, f"{plan['label']} active • Brightness set to {applied}%"

    def set_brightness(self, level: int) -> int | None:
        if os.name != "nt":
            return None
        level = max(0, min(100, int(level)))
        script = (
            "$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop; "
            f"$m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=[uint32]1; Brightness=[byte]{level}}} | Out-Null; "
            "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness -ErrorAction Stop | Select-Object -First 1).CurrentBrightness"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        text = _decode_output(result.stdout).strip()
        try:
            return int(text.splitlines()[-1])
        except (IndexError, ValueError):
            return level

    def pop_auto_plan(self) -> str:
        plan, self._auto_plan = self._auto_plan, ""
        return plan

    def consume_alerts(self, stats: dict[str, Any]) -> list[tuple[str, str]]:
        alerts: list[tuple[str, str]] = []
        battery = stats.get("battery")
        if isinstance(battery, dict):
            percent = float(battery.get("percent") or 0)
            low = (not battery.get("plugged")) and percent <= LOW_BATTERY_PERCENT
            if low and not self._battery_latched:
                self._battery_latched = True
                self._auto_plan = "saver"
                alerts.append(("SYSTEM ALERT", f"Battery at {percent:.0f}%. Switching to Power Saver."))
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
                    ("SYSTEM ALERT", f"Low disk space: {free / (1024 ** 3):.1f} GB free on {mount}")
                )
            elif free_pct > LOW_DISK_FREE_PERCENT + 2:
                self._disk_latched = False
        return alerts

    def _nt_process_table(self) -> list[tuple[int, int, str, float, float]] | None:
        buffer = self._nt_buffer
        if buffer is None:
            return None
        ntdll = ctypes.WinDLL("ntdll")
        query = ntdll.NtQuerySystemInformation
        query.restype = ctypes.c_long
        needed = ctypes.c_ulong(0)
        for _attempt in range(4):
            status = query(5, buffer, len(buffer), ctypes.byref(needed)) & 0xFFFFFFFF
            if status != _STATUS_INFO_LENGTH_MISMATCH:
                break
            buffer = ctypes.create_string_buffer(max(needed.value, len(buffer)) + (1 << 18))
            self._nt_buffer = buffer
        if status != 0:
            return None

        base = ctypes.addressof(buffer)
        size = len(buffer)
        table: list[tuple[int, int, str, float, float]] = []
        offset = 0
        while True:
            next_offset, = struct.unpack_from("<I", buffer, offset)
            private_ws, = struct.unpack_from("<q", buffer, offset + 8)
            created, user, kernel = struct.unpack_from("<qqq", buffer, offset + 32)
            name_len, = struct.unpack_from("<H", buffer, offset + 56)
            name_ptr, = struct.unpack_from("<Q", buffer, offset + 64)
            pid, = struct.unpack_from("<Q", buffer, offset + 80)
            name = ""
            start = name_ptr - base
            if name_ptr and 0 <= start and start + name_len <= size:
                name = buffer[start:start + name_len].decode("utf-16-le", errors="replace")
            table.append((int(pid), int(created), name, (user + kernel) / 1e7, float(private_ws)))
            if not next_offset:
                break
            offset += next_offset
        return table

    def _psutil_process_table(self) -> list[tuple[int, int, str, float, float]]:
        table: list[tuple[int, int, str, float, float]] = []
        for proc in psutil.process_iter(["pid", "name", "create_time", "cpu_times", "memory_info"]):
            info = proc.info
            times = info.get("cpu_times")
            memory = info.get("memory_info")
            if times is None or memory is None:
                continue
            table.append(
                (
                    int(info["pid"]),
                    int((info.get("create_time") or 0) * 1000),
                    info.get("name") or "",
                    float(times.user + times.system),
                    float(memory.rss),
                )
            )
        return table

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
        result = self._powercfg(["/query", guid, "SUB_VIDEO", "VIDEONORMALLEVEL"])
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
        plan_id = _GUID_TO_ID.get(guid) or next(
            (key for key, saved in self._resolved.items() if saved == guid), ""
        ) or _plan_id_from_name(name)
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
