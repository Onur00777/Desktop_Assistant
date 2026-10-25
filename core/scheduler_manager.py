"""Özlü söz ve yerel takvim hatırlatıcıları.

Google Calendar bağlanırken yalnızca load_events() değişir.
Beklenen alanlar: id, title, start, remind_minutes.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_FALLBACK_QUOTES = (
    "Küçük adımlar, çalışan sistemler kurar.",
    "Tek pencere, tek niyet.",
    "Gürültüyü kapat. Sinyali bırak.",
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
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _remind_minutes(value: object) -> int:
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 15
    return max(0, min(minutes, 24 * 60))


class SchedulerManager(QObject):
    quote_ready = pyqtSignal(str)
    event_alert = pyqtSignal(str)

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = Path(data_dir)
        self.quotes_path = self.data_dir / "quotes.json"
        self.events_path = self.data_dir / "events.json"
        self.notified_path = self.data_dir / "notified.json"
        self._last_quote = ""
        self._quote_timer = QTimer(self)
        self._quote_timer.timeout.connect(self.emit_quote)
        self._event_timer = QTimer(self)
        self._event_timer.timeout.connect(self.poll_events)

    def start(self) -> None:
        self._quote_timer.start(self._interval_ms())
        self._event_timer.start(20_000)
        QTimer.singleShot(1200, self.poll_events)

    def emit_quote(self) -> None:
        quote = self._pick_quote()
        if quote:
            self.quote_ready.emit(quote)

    def load_events(self) -> list[dict]:
        data = _read_json(self.events_path, {"events": []})
        events = data.get("events", [])
        if not isinstance(events, list):
            return []
        return [event for event in events if isinstance(event, dict)]

    def upcoming(self) -> list[dict]:
        now = datetime.now()
        horizon = now + timedelta(days=60)
        items: list[dict] = []
        for event in self.load_events():
            start = parse_when(event.get("start"))
            if start is None:
                continue
            if now - timedelta(minutes=10) <= start <= horizon:
                items.append({**event, "start_dt": start})
        items.sort(key=lambda item: item["start_dt"])
        return items[:5]

    def poll_events(self) -> None:
        now = datetime.now()
        state = _read_json(self.notified_path, {"ids": []})
        raw_ids = state.get("ids", [])
        done = {str(item) for item in raw_ids} if isinstance(raw_ids, list) else set()
        changed = False
        for event in self.load_events():
            start = parse_when(event.get("start"))
            if start is None:
                continue
            key = f"{event.get('id') or event.get('title')}|{event.get('start')}"
            if key in done:
                continue
            delta = start - now
            remind = timedelta(minutes=_remind_minutes(event.get("remind_minutes", 15)))
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
    title = str(event.get("title") or "Etkinlik")
    minutes = int(delta.total_seconds() // 60)
    if minutes <= 0:
        return f"{title} şimdi başlıyor."
    if minutes < 60:
        return f"{title} · {minutes} dk sonra"
    hours, mins = divmod(minutes, 60)
    return f"{title} · {hours} sa {mins} dk sonra"
