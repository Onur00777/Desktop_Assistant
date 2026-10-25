"""Masaüstü Asistan.

Çalıştırma:
    py -3 main.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from core.scheduler_manager import SchedulerManager
from core.system_manager import SystemManager
from core.workspace_manager import WorkspaceManager
from ui.bubble import SpeechBubble
from ui.dashboard import Dashboard
from ui.mark import render_icon
from ui.styles import APP_QSS
from ui.tray import AssistantTray
from ui.widget import DesktopWidget

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE_PATH = DATA / "widget_state.json"
_INSTANCE = "MasaustuAsistan.single"


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
    app.setApplicationName("Masaüstü Asistan")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(APP_QSS)

    busy, server = _acquire_instance()
    if busy:
        QMessageBox.information(None, "Masaüstü Asistan", "Asistan zaten çalışıyor.")
        return 0
    app._instance_server = server  # type: ignore[attr-defined]

    icon = render_icon(0)
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
    tray.setIcon(icon)

    ticks = [0]
    icon_cpu = [0.0]

    def refresh_view(refresh_power: bool = False) -> None:
        stats = system.snapshot(refresh_power=refresh_power)
        memory = stats.get("memory") or {}
        widget.set_status(float(stats["cpu"]), float(memory.get("percent") or 0))
        if dashboard.isVisible():
            dashboard.set_stats(stats)
        for kind, text in system.consume_alerts(stats):
            bubble.push(kind, text, 15000)
        cpu = float(stats["cpu"])
        if tray.available and abs(cpu - icon_cpu[0]) >= 4:
            icon_cpu[0] = cpu
            tray.setIcon(render_icon(cpu))

    def tick() -> None:
        try:
            ticks[0] += 1
            refresh_view(refresh_power=dashboard.isVisible() and ticks[0] % 10 == 0)
            if dashboard.isVisible() and ticks[0] % 8 == 0:
                dashboard.set_events(scheduler.upcoming())
        except Exception:
            traceback.print_exc()

    def open_dashboard() -> None:
        try:
            dashboard.set_events(scheduler.upcoming())
            dashboard.set_stats(system.snapshot(refresh_power=True))
        except Exception:
            traceback.print_exc()
        dashboard.present_near(widget)

    def toggle_dashboard() -> None:
        if dashboard.isVisible():
            dashboard.hide()
            return
        open_dashboard()

    def launch_profile(name: str) -> None:
        try:
            result = workspaces.activate(name)
        except ValueError as exc:
            bubble.push("SİSTEM", str(exc), 10000)
            return
        text = f"{name}: {len(result['launched'])} açıldı, {len(result['killed'])} işlem kapatıldı."
        if result["killed"]:
            text += " Kapatılan: " + ", ".join(result["killed"]) + "."
        if result["errors"]:
            text += " " + " ".join(result["errors"])
        bubble.push("SİSTEM" if result["errors"] else "BİLGİ", text, 10000)

    def save_profile(profile: dict) -> None:
        try:
            workspaces.add_profile(profile)
        except ValueError as exc:
            dashboard.show_feedback(str(exc))
            bubble.push("SİSTEM", str(exc), 8000)
            return
        dashboard.clear_form()
        dashboard.refresh_profiles()
        bubble.push("BİLGİ", f"{profile.get('name', 'Profil')} kaydedildi.", 7000)

    def delete_profile(name: str) -> None:
        try:
            removed = workspaces.remove_profile(name)
        except ValueError as exc:
            bubble.push("SİSTEM", str(exc), 8000)
            return
        if removed:
            dashboard.refresh_profiles()
            bubble.push("BİLGİ", f"{name} silindi.", 6000)

    def change_plan(plan_id: str) -> None:
        ok, detail = system.set_power_plan(plan_id)
        bubble.push("BİLGİ" if ok else "SİSTEM", detail, 8000)
        if dashboard.isVisible():
            dashboard.set_stats(system.snapshot(refresh_power=True))

    def hide_widget() -> None:
        if not tray.available:
            bubble.push("SİSTEM", "Sistem tepsisi yok. Sağ tık menüsünden çıkabilirsin.", 8000)
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
        bubble.push("ETKİNLİK", text, 14000)
        if dashboard.isVisible():
            dashboard.set_events(scheduler.upcoming())

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
    dashboard.power_requested.connect(change_plan)
    dashboard.quote_requested.connect(scheduler.emit_quote)

    tray.toggle_widget_requested.connect(toggle_widget)
    tray.toggle_dashboard_requested.connect(toggle_dashboard)
    tray.launch_workspace.connect(launch_profile)
    tray.quit_requested.connect(shutdown)

    scheduler.quote_ready.connect(lambda text: bubble.push("SÖZ", text, 12000))
    scheduler.event_alert.connect(on_event)

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
            "BİLGİ",
            "Hazır. İkonu sürükleyebilir, sol tıkla paneli açabilirsin.",
            6500,
        ),
    )
    QTimer.singleShot(2200, scheduler.emit_quote)
    QTimer.singleShot(400, lambda: refresh_view(refresh_power=False))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
