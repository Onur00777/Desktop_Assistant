"""Quotes and Google Calendar reminders.

Events come from the calendar's secret iCal address, refreshed in the background
and cached locally so the list still works offline.
Event fields: id, title, start, remind_minutes, all_day.
"""

from __future__ import annotations

import json
import random
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

SYNC_MINUTES = 10
LOOKAHEAD_DAYS = 60
DEFAULT_REMIND_MINUTES = 10
MAX_ICAL_BYTES = 10 * 1024 * 1024

_FALLBACK_QUOTES = (
    "Small steps build working systems.",
    "One window, one intention.",
    "Mute the noise. Keep the signal.",
)


def _read_json(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return default
    return data if isinstance(data, dict) else default


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(text, encoding="utf-8")
    try:
        temporary.replace(path)
    except OSError:
        path.write_text(text, encoding="utf-8")


def parse_when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def normalize_ical_url(url: str) -> str:
    text = url.strip().strip('"').strip()
    if text.lower().startswith("webcal://"):
        text = "https://" + text[len("webcal://"):]
    if not text.lower().startswith(("https://", "http://")):
        raise ValueError("Paste the full address starting with https://")
    if ".ics" not in text.lower():
        raise ValueError("That is not an iCal address. Copy the 'Secret address in iCal format'.")
    return text


def fetch_ical(url: str, timeout: float = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "DesktopAssistant/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_ICAL_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise RuntimeError("Calendar address not found. Copy the 'Secret address in iCal format'.") from exc
        raise RuntimeError(f"Google Calendar returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Could not reach Google Calendar. Check your connection.") from exc
    if len(data) > MAX_ICAL_BYTES:
        raise RuntimeError("Calendar is too large to sync.")
    return data


def parse_ical(data: bytes, now: datetime | None = None, days: int = LOOKAHEAD_DAYS) -> list[dict]:
    import icalendar
    import recurring_ical_events

    now = now or datetime.now()
    try:
        calendar = icalendar.Calendar.from_ical(data)
    except Exception as exc:
        raise RuntimeError("The address did not return a valid calendar.") from exc
    window = ((now - timedelta(days=7)).date(), (now + timedelta(days=days)).date())
    events: list[dict] = []
    for component in recurring_ical_events.of(calendar).between(*window):
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue
        try:
            raw_start = component.decoded("DTSTART")
        except KeyError:
            continue
        all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
        if all_day:
            start = datetime.combine(raw_start, time.min)
        elif raw_start.tzinfo is not None:
            start = raw_start.astimezone().replace(tzinfo=None)
        else:
            start = raw_start
        title = str(component.get("SUMMARY") or "Untitled event").strip() or "Untitled event"
        uid = str(component.get("UID") or title)
        stamp = start.isoformat(timespec="seconds")
        events.append(
            {
                "id": f"{uid}|{stamp}",
                "title": title,
                "start": stamp,
                "remind_minutes": _alarm_minutes(component, start),
                "all_day": all_day,
            }
        )
    events.sort(key=lambda event: event["start"])
    return events


def _alarm_minutes(component, start: datetime) -> int:
    leads: list[int] = []
    for alarm in component.walk("VALARM"):
        try:
            trigger = alarm.decoded("TRIGGER")
        except (KeyError, ValueError):
            continue
        if isinstance(trigger, timedelta):
            lead = -trigger
        elif isinstance(trigger, datetime):
            moment = trigger.astimezone().replace(tzinfo=None) if trigger.tzinfo else trigger
            lead = start - moment
        else:
            continue
        if lead >= timedelta(0):
            leads.append(int(lead.total_seconds() // 60))
    return min(leads) if leads else DEFAULT_REMIND_MINUTES


def _remind_minutes(value: object) -> int:
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_REMIND_MINUTES
    return max(0, min(minutes, 7 * 24 * 60))


class SchedulerManager(QObject):
    quote_ready = pyqtSignal(str, bool)
    event_alert = pyqtSignal(str)
    events_changed = pyqtSignal()
    calendar_synced = pyqtSignal(bool, str, bool)
    _fetched = pyqtSignal(object, str, bool, str)

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = Path(data_dir)
        self.quotes_path = self.data_dir / "quotes.json"
        self.config_path = self.data_dir / "calendar.json"
        self.cache_path = self.data_dir / "calendar_cache.json"
        self.notified_path = self.data_dir / "notified.json"
        self._last_quote = ""

        config = _read_json(self.config_path, {})
        self._calendar_url = str(config.get("ical_url") or "")
        cache = _read_json(self.cache_path, {}) if self._calendar_url else {}
        cached = cache.get("events", [])
        self._events: list[dict] = [event for event in cached if isinstance(event, dict)] if isinstance(cached, list) else []
        self._synced_at = str(cache.get("synced_at") or "")
        self._error = ""
        self._syncing = False

        self._quote_timer = QTimer(self)
        self._quote_timer.timeout.connect(lambda: self.emit_quote())
        self._event_timer = QTimer(self)
        self._event_timer.timeout.connect(self.poll_events)
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(lambda: self.sync())
        self._fetched.connect(self._on_fetched)

    def start(self) -> None:
        self._quote_timer.start(self._interval_ms())
        self._event_timer.start(20_000)
        self._sync_timer.start(SYNC_MINUTES * 60 * 1000)
        QTimer.singleShot(1200, self.poll_events)
        QTimer.singleShot(3000, lambda: self.sync())

    def emit_quote(self, now: bool = False) -> None:
        quote = self._pick_quote()
        if quote:
            self.quote_ready.emit(quote, now)

    @property
    def calendar_connected(self) -> bool:
        return bool(self._calendar_url)

    def calendar_status(self) -> str:
        if not self._calendar_url:
            return "Google Calendar is not connected."
        if self._syncing:
            return "Google Calendar • syncing…"
        if self._error:
            return f"Google Calendar • sync failed: {self._error}"
        synced = parse_when(self._synced_at)
        if synced is None:
            return "Google Calendar • waiting for first sync"
        return f"Google Calendar • synced {synced.strftime('%H:%M')}"

    def connect_calendar(self, url: str) -> None:
        self._calendar_url = normalize_ical_url(url)
        _write_json(self.config_path, {"ical_url": self._calendar_url})
        self._events = []
        self._synced_at = ""
        self._error = ""
        self.cache_path.unlink(missing_ok=True)
        self.events_changed.emit()
        self.sync(manual=True)

    def disconnect_calendar(self) -> None:
        self._calendar_url = ""
        self._events = []
        self._synced_at = ""
        self._error = ""
        self.config_path.unlink(missing_ok=True)
        self.cache_path.unlink(missing_ok=True)
        self.events_changed.emit()

    def sync(self, manual: bool = False) -> None:
        url = self._calendar_url
        if not url or self._syncing:
            return
        self._syncing = True
        self.events_changed.emit()

        def work() -> None:
            try:
                events = parse_ical(fetch_ical(url))
                self._fetched.emit(events, "", manual, url)
            except Exception as exc:
                self._fetched.emit(None, str(exc) or "Unknown error.", manual, url)

        threading.Thread(target=work, name="calendar-sync", daemon=True).start()

    def _on_fetched(self, events: object, error: str, manual: bool, url: str) -> None:
        self._syncing = False
        if url != self._calendar_url:
            self.events_changed.emit()
            return
        if isinstance(events, list):
            self._events = events
            self._error = ""
            self._synced_at = datetime.now().isoformat(timespec="seconds")
            _write_json(self.cache_path, {"synced_at": self._synced_at, "events": events})
            upcoming = len(self.upcoming(limit=1000))
            plural = "event" if upcoming == 1 else "events"
            self.calendar_synced.emit(True, f"Google Calendar synced • {upcoming} upcoming {plural}", manual)
            self.poll_events()
        else:
            self._error = error
            self.calendar_synced.emit(False, error, manual)
        self.events_changed.emit()

    def load_events(self) -> list[dict]:
        return list(self._events)

    def upcoming(self, limit: int = 5) -> list[dict]:
        now = datetime.now()
        horizon = now + timedelta(days=LOOKAHEAD_DAYS)
        items: list[dict] = []
        for event in self.load_events():
            start = parse_when(event.get("start"))
            if start is None:
                continue
            if event.get("all_day"):
                visible = now.date() <= start.date() <= horizon.date()
            else:
                visible = now - timedelta(minutes=10) <= start <= horizon
            if visible:
                items.append({**event, "start_dt": start})
        items.sort(key=lambda item: item["start_dt"])
        return items[:limit]

    def week_events(self, week_start: date) -> dict[date, list[dict]]:
        days = {week_start + timedelta(days=offset): [] for offset in range(7)}
        for event in self.load_events():
            start = parse_when(event.get("start"))
            if start is not None and start.date() in days:
                days[start.date()].append({**event, "start_dt": start})
        for items in days.values():
            items.sort(key=lambda item: (not item.get("all_day"), item["start_dt"]))
        return days

    def poll_events(self) -> None:
        now = datetime.now()
        state = _read_json(self.notified_path, {"ids": []})
        raw_ids = state.get("ids", [])
        done = {str(item) for item in raw_ids} if isinstance(raw_ids, list) else set()
        changed = False
        for event in self.load_events():
            start = parse_when(event.get("start"))
            if start is None or event.get("all_day"):
                continue
            key = f"{event.get('id') or event.get('title')}|{event.get('start')}"
            if key in done:
                continue
            delta = start - now
            remind = timedelta(minutes=_remind_minutes(event.get("remind_minutes", DEFAULT_REMIND_MINUTES)))
            if timedelta(minutes=-2) <= delta <= remind:
                self.event_alert.emit(_event_text(event, delta))
                done.add(key)
                changed = True
            elif delta < timedelta(minutes=-2):
                done.add(key)
                changed = True
        if changed:
            _write_json(self.notified_path, {"ids": list(done)[-400:]})

    def _interval_ms(self) -> int:
        data = _read_json(self.quotes_path, {})
        raw = data.get("interval_minutes", 15)
        try:
            minutes = float(raw)
        except (TypeError, ValueError):
            minutes = 15
        minutes = min(24 * 60, max(1, minutes))
        return int(minutes * 60 * 1000)

    def _pick_quote(self) -> str:
        data = _read_json(self.quotes_path, {})
        raw_quotes = data.get("quotes")
        if not isinstance(raw_quotes, list) or not raw_quotes:
            pool = list(_FALLBACK_QUOTES)
        else:
            pool = [str(quote).strip() for quote in raw_quotes if str(quote).strip()]
        if not pool:
            return ""
        choice = random.choice(pool)
        if choice == self._last_quote and len(pool) > 1:
            choice = random.choice([quote for quote in pool if quote != self._last_quote])
        self._last_quote = choice
        return choice


def _event_text(event: dict, delta: timedelta) -> str:
    title = str(event.get("title") or "Event")
    minutes = int(delta.total_seconds() // 60)
    if minutes <= 0:
        return f"{title} starts now."
    if minutes < 60:
        return f"{title} • in {minutes} min"
    hours, mins = divmod(minutes, 60)
    return f"{title} • in {hours} h {mins} min"
