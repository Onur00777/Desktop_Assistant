"""Desktop Assistant.

Run:
    py -3 main.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from core.scheduler_manager import SchedulerManager
from core.system_manager import PLANS, SystemManager
from core.workspace_manager import WorkspaceManager
from ui.bot_icon import render_app_icon
from ui.bubble import ALERT, EVENT, INFO, QUOTE, SpeechBubble
from ui.dashboard import Dashboard
from ui.styles import APP_QSS
from ui.tray import AssistantTray
from ui.widget import DesktopWidget

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE_PATH = DATA / "widget_state.json"
_INSTANCE = "MasaustuAsistan.single"


class PowerRelay(QObject):
    finished = pyqtSignal(str, bool, str)


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Masaustu.Asistan.Widget")
    except Exception:
        return


def _install_excepthook() -> None:
    def handle(exc_type, value, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, value, tb))
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            with (DATA / "error.log").open("a", encoding="utf-8") as handle_log:
                handle_log.write(text + "\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, value, tb)

    sys.excepthook = handle


def _read_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(pos: QWidget) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"x": pos.x(), "y": pos.y()}, indent=2) + "\n",
        encoding="utf-8",
    )


def _clamp(window: QWidget) -> None:
    screen = QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
    if screen is None:
        return
    avail = screen.availableGeometry()
    x = min(max(window.x(), avail.left()), max(avail.left(), avail.right() - window.width()))
    y = min(max(window.y(), avail.top()), max(avail.top(), avail.bottom() - window.height()))
    window.move(x, y)


def _acquire_instance() -> tuple[bool, QLocalServer | None]:
    socket = QLocalSocket()
    socket.connectToServer(_INSTANCE)
    if socket.waitForConnected(250):
        socket.disconnectFromServer()
        return True, None
    QLocalServer.removeServer(_INSTANCE)
    server = QLocalServer()
    if server.listen(_INSTANCE):
        return False, server
    socket.connectToServer(_INSTANCE)
    if socket.waitForConnected(250):
        socket.disconnectFromServer()
        return True, None
    return False, server


def _place_widget(widget: DesktopWidget) -> None:
    state = _read_state()
    if "x" in state and "y" in state:
        try:
            widget.move(int(state["x"]), int(state["y"]))
        except (TypeError, ValueError):
            state = {}
    if "x" not in state or "y" not in state:
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            widget.move(avail.right() - widget.width() - 28, avail.bottom() - widget.height() - 36)
    _clamp(widget)


def main() -> int:
    _set_windows_app_id()
    _install_excepthook()
    DATA.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Assistant")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(APP_QSS)

    busy, server = _acquire_instance()
    if busy:
        QMessageBox.information(None, "Desktop Assistant", "The assistant is already running.")
        return 0
    app._instance_server = server  # type: ignore[attr-defined]

    icon = render_app_icon()
    app.setWindowIcon(icon)

    system = SystemManager(DATA / "power_schemes.json")
    workspaces = WorkspaceManager(DATA / "workspaces.json")
    scheduler = SchedulerManager(DATA)

    widget = DesktopWidget()
    bubble = SpeechBubble()
    bubble.bind(widget)
    dashboard = Dashboard(workspaces)
    dashboard.setWindowIcon(icon)
    tray = AssistantTray(icon, workspaces)

    relay = PowerRelay()
    power_state = {"busy": False, "pending": ""}
    ticks = [0]

    def smile() -> None:
        widget.trigger_success_expression()

    def refresh_processes() -> None:
        if dashboard.isVisible():
            dashboard.set_processes(system.top_processes())

    def refresh_view(refresh_power: bool = False) -> None:
        stats = system.snapshot(refresh_power=refresh_power)
        memory = stats.get("memory") or {}
        widget.set_status(float(stats["cpu"]), float(memory.get("percent") or 0))
        if dashboard.isVisible():
            dashboard.set_stats(stats)
        for kind, text in system.consume_alerts(stats):
            bubble.push(kind, text, 15000)
        auto_plan = system.pop_auto_plan()
        if auto_plan:
            request_plan(auto_plan)

    def tick() -> None:
        try:
            ticks[0] += 1
            refresh_view(refresh_power=dashboard.isVisible() and ticks[0] % 10 == 0)
            refresh_processes()
            if dashboard.isVisible() and ticks[0] % 8 == 0:
                refresh_calendar()
        except Exception:
            traceback.print_exc()

    def refresh_calendar() -> None:
        dashboard.set_calendar_state(scheduler.calendar_connected, scheduler.calendar_status())
        dashboard.set_events(scheduler.upcoming())

    def connect_calendar(url: str) -> None:
        try:
            scheduler.connect_calendar(url)
        except (ValueError, OSError) as exc:
            dashboard.set_calendar_state(False, str(exc))
            bubble.push(ALERT, str(exc), 9000, now=True)

    def disconnect_calendar() -> None:
        scheduler.disconnect_calendar()
        bubble.push(INFO, "Google Calendar disconnected", 6000, now=True)

    def on_calendar_synced(ok: bool, message: str, manual: bool) -> None:
        if manual:
            bubble.push(INFO if ok else ALERT, message if ok else f"Calendar sync failed • {message}", 9000, now=True)

    def open_dashboard() -> None:
        try:
            refresh_calendar()
            dashboard.set_stats(system.snapshot(refresh_power=True))
            system.top_processes()
        except Exception:
            traceback.print_exc()
        dashboard.present_near(widget)
        QTimer.singleShot(700, refresh_processes)

    def toggle_dashboard() -> None:
        if dashboard.isVisible():
            dashboard.hide()
            return
        open_dashboard()

    def launch_profile(name: str) -> None:
        try:
            result = workspaces.activate(name)
        except ValueError as exc:
            bubble.push(ALERT, str(exc), 10000, now=True)
            return
        text = f"{name} launched • {len(result['launched'])} opened, {len(result['killed'])} closed"
        if result["killed"]:
            text += " (" + ", ".join(result["killed"]) + ")"
        if result["errors"]:
            text += " • " + "; ".join(result["errors"])
        bubble.push(ALERT if result["errors"] else INFO, text, 10000, now=True)
        if result["launched"] or result["killed"]:
            smile()

    def save_profile(profile: dict) -> None:
        try:
            workspaces.add_profile(profile)
        except ValueError as exc:
            dashboard.show_feedback(str(exc))
            bubble.push(ALERT, str(exc), 8000, now=True)
            return
        dashboard.clear_form()
        dashboard.refresh_profiles()
        bubble.push(INFO, f"Profile saved • {profile.get('name', 'Profile')}", 7000, now=True)
        smile()

    def delete_profile(name: str) -> None:
        try:
            removed = workspaces.remove_profile(name)
        except ValueError as exc:
            bubble.push(ALERT, str(exc), 8000, now=True)
            return
        if removed:
            dashboard.refresh_profiles()
            bubble.push(INFO, f"Profile deleted • {name}", 6000, now=True)

    def request_plan(plan_id: str) -> None:
        if plan_id not in PLANS:
            return
        if power_state["busy"]:
            power_state["pending"] = plan_id
            return
        power_state["busy"] = True

        def work() -> None:
            try:
                ok, detail = system.set_power_plan(plan_id)
            except Exception as exc:
                ok, detail = False, f"Power plan error: {exc}"
            relay.finished.emit(plan_id, ok, detail)

        threading.Thread(target=work, name="power-plan", daemon=True).start()

    def on_plan_finished(_plan_id: str, ok: bool, detail: str) -> None:
        power_state["busy"] = False
        bubble.push(INFO if ok else ALERT, detail, 8000, now=True)
        if ok:
            smile()
        if dashboard.isVisible():
            dashboard.set_stats(system.snapshot(refresh_power=True))
        pending, power_state["pending"] = power_state["pending"], ""
        if pending:
            request_plan(pending)

    def end_process(name: str) -> None:
        ok, detail = system.end_process_group(name)
        bubble.push(INFO if ok else ALERT, detail, 8000, now=True)
        if ok:
            smile()
            QTimer.singleShot(600, refresh_processes)

    def on_bubble_shown(kind: str) -> None:
        if kind != ALERT:
            smile()

    def hide_widget() -> None:
        if not tray.available:
            bubble.push(ALERT, "No system tray available. Use the right-click menu to quit.", 8000, now=True)
            return
        widget.hide()
        bubble.suspend()
        dashboard.hide()
        tray.set_widget_visible(False)

    def show_widget() -> None:
        widget.show()
        widget.raise_()
        bubble.resume()
        tray.set_widget_visible(True)

    def toggle_widget() -> None:
        if widget.isVisible():
            hide_widget()
        else:
            show_widget()

    def on_event(text: str) -> None:
        bubble.push(EVENT, text, 14000)
        if dashboard.isVisible():
            refresh_calendar()

    def shutdown() -> None:
        widget.allow_close = True
        timer.stop()
        bubble.suspend()
        dashboard.hide()
        tray.hide()
        widget.hide()
        app.quit()

    widget.clicked.connect(toggle_dashboard)
    widget.open_requested.connect(open_dashboard)
    widget.moved.connect(lambda: bubble.sync_position() if bubble.isVisible() else None)
    widget.dropped.connect(lambda: _write_state(widget))
    widget.hide_requested.connect(hide_widget)
    widget.quit_requested.connect(shutdown)

    dashboard.launch_requested.connect(launch_profile)
    dashboard.delete_requested.connect(delete_profile)
    dashboard.profile_submitted.connect(save_profile)
    dashboard.power_requested.connect(request_plan)
    dashboard.process_end_requested.connect(end_process)
    dashboard.quote_requested.connect(lambda: scheduler.emit_quote(now=True))
    dashboard.calendar_connect_requested.connect(connect_calendar)
    dashboard.calendar_sync_requested.connect(lambda: scheduler.sync(manual=True))
    dashboard.calendar_disconnect_requested.connect(disconnect_calendar)

    relay.finished.connect(on_plan_finished)
    bubble.shown.connect(on_bubble_shown)

    tray.toggle_widget_requested.connect(toggle_widget)
    tray.toggle_dashboard_requested.connect(toggle_dashboard)
    tray.launch_workspace.connect(launch_profile)
    tray.quit_requested.connect(shutdown)

    scheduler.quote_ready.connect(lambda text, now: bubble.push(QUOTE, text, 12000, now=now))
    scheduler.event_alert.connect(on_event)
    scheduler.events_changed.connect(lambda: refresh_calendar() if dashboard.isVisible() else None)
    scheduler.calendar_synced.connect(on_calendar_synced)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(2000)

    _place_widget(widget)
    widget.show()
    if tray.available:
        tray.show()
    scheduler.start()
    QTimer.singleShot(
        800,
        lambda: bubble.push(
            INFO,
            "Ready. Drag the icon to move it, left click to open the dashboard.",
            6500,
        ),
    )
    QTimer.singleShot(2200, scheduler.emit_quote)
    QTimer.singleShot(400, lambda: refresh_view(refresh_power=False))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
