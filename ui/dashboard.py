"""Compact control dashboard."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.workspace_manager import WorkspaceManager
from ui.styles import ACTIVE_BUTTON_QSS

PROCESS_ROWS = 6
IMPACT_COLORS = {
    "Low": "#7d9a86",
    "Medium": "#00FF41",
    "High": "#ffb020",
    "Very High": "#ff5a5a",
}


def _gb(num: float, digits: int = 1) -> str:
    return f"{num / (1024 ** 3):.{digits}f}"


def _remaining(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    minutes = int(seconds) // 60
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins}m left"
    return f"{mins}m left"


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section")
    label.setWordWrap(True)
    return label


def _hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background: #173222;")
    return line


def _lines(editor: QPlainTextEdit) -> list[str]:
    return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]


def _cell(text: str = "", name: str = "cell", align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return label


class DragHeader(QWidget):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("dragHeader")
        self._window = window
        self._offset: QPoint | None = None
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class ClickArea(QWidget):
    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("clickArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this week's schedule")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class StatRow(QWidget):
    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("statRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.caption = QLabel(caption)
        self.caption.setObjectName("mono")
        self.caption.setFixedWidth(64)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.value = QLabel("—")
        self.value.setObjectName("mono")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value.setMinimumWidth(150)
        layout.addWidget(self.caption)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value)

    def set_reading(self, percent: float, text: str, *, low_is_bad: bool = False) -> None:
        value = max(0.0, min(100.0, float(percent)))
        self.bar.setValue(int(round(value)))
        self.value.setText(text)
        if low_is_bad:
            if value <= 15:
                color = "#ff5a5a"
            elif value <= 30:
                color = "#ffb020"
            else:
                color = "#00FF41"
        elif value >= 95:
            color = "#ff5a5a"
        elif value >= 85:
            color = "#ffb020"
        else:
            color = "#00FF41"
        self._paint_bar(color)

    def set_empty(self, text: str) -> None:
        self.bar.setValue(0)
        self.value.setText(text)
        self._paint_bar("#1a3324")

    def _paint_bar(self, color: str) -> None:
        self.bar.setStyleSheet(
            "QProgressBar {"
            " background: #08110c;"
            " border: 1px solid #1a3324;"
            " border-radius: 4px;"
            " min-height: 10px;"
            " max-height: 10px;"
            "}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )


class ProcessRow:
    def __init__(self, grid: QGridLayout, row: int, on_end) -> None:
        self.process = ""
        self.impact = ""
        self.name = _cell(name="cell", align=Qt.AlignmentFlag.AlignLeft)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cpu = _cell()
        self.ram = _cell()
        self.power = _cell()
        self.end = QPushButton("End")
        self.end.setObjectName("endBtn")
        self.end.setFixedWidth(52)
        self.end.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end.clicked.connect(lambda _checked=False: on_end(self.process))
        for column, widget in enumerate((self.name, self.cpu, self.ram, self.power, self.end)):
            grid.addWidget(widget, row, column)
        self.set_visible(False)

    def set_visible(self, visible: bool) -> None:
        for widget in (self.name, self.cpu, self.ram, self.power, self.end):
            widget.setVisible(visible)

    def show_process(self, process: dict, armed: str) -> None:
        name = str(process.get("name") or "")
        count = int(process.get("count") or 1)
        self.process = name
        label = f"{name} ({count})" if count > 1 else name
        width = max(60, self.name.width() - 4)
        self.name.setText(self.name.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, width))
        self.name.setToolTip(label)
        self.cpu.setText(f"{float(process.get('cpu') or 0):.1f}%")
        self.ram.setText(f"{float(process.get('ram_mb') or 0):,.0f} MB / {float(process.get('ram_percent') or 0):.1f}%")
        impact = str(process.get("impact") or "Low")
        self.power.setText(impact)
        if impact != self.impact:
            self.impact = impact
            self.power.setStyleSheet(f"color: {IMPACT_COLORS.get(impact, '#d7ffe4')};")
        protected = bool(process.get("protected"))
        self.end.setEnabled(not protected)
        self.end.setText("Sure?" if armed == name and not protected else "End")
        self.end.setToolTip("Protected process" if protected else f"End all {name} processes")
        self.set_visible(True)


class Dashboard(QWidget):
    launch_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    profile_submitted = pyqtSignal(object)
    power_requested = pyqtSignal(str)
    quote_requested = pyqtSignal()
    process_end_requested = pyqtSignal(str)
    week_requested = pyqtSignal()
    calendar_connect_requested = pyqtSignal(str)
    calendar_sync_requested = pyqtSignal()
    calendar_disconnect_requested = pyqtSignal()

    def __init__(self, workspaces: WorkspaceManager) -> None:
        super().__init__()
        self.workspaces = workspaces
        self._active_plan = ""
        self._plan_buttons: dict[str, QPushButton] = {}
        self._armed_process = ""
        self._last_processes: list[dict] = []
        self._disarm_timer = QTimer(self)
        self._disarm_timer.setSingleShot(True)
        self._disarm_timer.timeout.connect(self._disarm_process)

        self.setObjectName("dashboardRoot")
        self.setWindowTitle("Desktop Assistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setMinimumSize(460, 520)
        self.resize(480, 680)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.hide)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 10)

        self.frame = QFrame()
        self.frame.setObjectName("panel")
        self.frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self.frame)

        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(16, 12, 16, 14)
        frame_layout.setSpacing(10)

        header = DragHeader(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("DESKTOP ASSISTANT")
        title.setObjectName("title")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(close_btn)
        frame_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.viewport().setObjectName("scrollViewport")
        scroll.viewport().setStyleSheet("QWidget#scrollViewport { background: transparent; }")

        content = QWidget()
        content.setObjectName("scrollBody")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 4, 0)
        body.setSpacing(8)

        body.addWidget(_section("SYSTEM TELEMETRY"))
        self.cpu_row = StatRow("CPU")
        self.ram_row = StatRow("RAM")
        self.disk_row = StatRow("DISK")
        self.battery_row = StatRow("BATTERY")
        for row in (self.cpu_row, self.ram_row, self.disk_row, self.battery_row):
            body.addWidget(row)

        self.plan_label = QLabel("Active Plan: —")
        self.plan_label.setObjectName("muted")
        body.addWidget(self.plan_label)

        plans = QHBoxLayout()
        plans.setSpacing(8)
        for plan_id, label, tip in (
            ("saver", "Power Saver", "Power Saver • brightness 35%"),
            ("balanced", "Balanced", "Balanced • brightness 65%"),
            ("performance", "Performance", "Performance • brightness 100%"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, pid=plan_id: self.power_requested.emit(pid))
            self._plan_buttons[plan_id] = button
            plans.addWidget(button, 1)
        body.addLayout(plans)
        body.addWidget(_hline())

        body.addWidget(_section("ACTIVE PROCESSES (TOP RESOURCE & POWER CONSUMERS)"))
        process_box = QWidget()
        process_box.setObjectName("processBox")
        grid = QGridLayout(process_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnMinimumWidth(1, 46)
        grid.setColumnMinimumWidth(2, 118)
        grid.setColumnMinimumWidth(3, 66)
        for column, (text, align) in enumerate(
            (
                ("PROCESS", Qt.AlignmentFlag.AlignLeft),
                ("CPU", Qt.AlignmentFlag.AlignRight),
                ("RAM (MB / %)", Qt.AlignmentFlag.AlignRight),
                ("POWER", Qt.AlignmentFlag.AlignRight),
                ("", Qt.AlignmentFlag.AlignRight),
            )
        ):
            grid.addWidget(_cell(text, "cellHead", align), 0, column)
        self.process_rows = [ProcessRow(grid, index + 1, self._on_end_clicked) for index in range(PROCESS_ROWS)]
        body.addWidget(process_box)
        self.process_hint = QLabel("Sampling processes…")
        self.process_hint.setObjectName("muted")
        body.addWidget(self.process_hint)
        body.addWidget(_hline())

        body.addWidget(_section("WORKSPACES"))
        self.profile_layout = QVBoxLayout()
        self.profile_layout.setSpacing(6)
        body.addLayout(self.profile_layout)

        self.form_button = QPushButton("New Profile")
        self.form_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.form_button.clicked.connect(self._toggle_form)
        body.addWidget(self.form_button)

        self.form = QWidget()
        self.form.setObjectName("formBox")
        form_layout = QVBoxLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Profile name  •  e.g. Coding")
        self.apps_edit = self._editor("One app per line\ne.g. code")
        self.folders_edit = self._editor("One folder path per line")
        self.urls_edit = self._editor("https://github.com")
        self.kill_edit = self._editor("Spotify.exe")
        self.feedback = QLabel("")
        self.feedback.setObjectName("muted")
        self.feedback.setWordWrap(True)
        save = QPushButton("Save Profile")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setProperty("active", True)
        save.clicked.connect(self._submit)
        self.name_edit.returnPressed.connect(self._submit)
        form_layout.addWidget(self.name_edit)
        for caption, editor in (
            ("Apps", self.apps_edit),
            ("Folders", self.folders_edit),
            ("Websites", self.urls_edit),
            ("Processes to close", self.kill_edit),
        ):
            label = QLabel(caption)
            label.setObjectName("muted")
            form_layout.addWidget(label)
            form_layout.addWidget(editor)
        form_layout.addWidget(self.feedback)
        form_layout.addWidget(save)
        self.form.setVisible(False)
        body.addWidget(self.form)
        self._restyle(save)

        body.addWidget(_hline())
        upcoming = QHBoxLayout()
        upcoming_header = ClickArea()
        header_layout = QHBoxLayout(upcoming_header)
        header_layout.setContentsMargins(4, 2, 8, 2)
        upcoming_title = _section("UPCOMING EVENTS  ›  WEEK VIEW")
        upcoming_title.setWordWrap(False)
        header_layout.addWidget(upcoming_title)
        upcoming_header.clicked.connect(self.week_requested.emit)
        upcoming.addWidget(upcoming_header)
        upcoming.addStretch(1)
        quote_btn = QPushButton("Get Quote")
        quote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quote_btn.clicked.connect(self.quote_requested.emit)
        upcoming.addWidget(quote_btn)
        body.addLayout(upcoming)

        event_area = ClickArea()
        event_area.clicked.connect(self.week_requested.emit)
        self.event_layout = QVBoxLayout(event_area)
        self.event_layout.setContentsMargins(4, 4, 4, 4)
        self.event_layout.setSpacing(4)
        body.addWidget(event_area)

        self.calendar_status = QLabel("")
        self.calendar_status.setObjectName("muted")
        self.calendar_status.setWordWrap(True)
        body.addWidget(self.calendar_status)

        self.calendar_connect_box = QWidget()
        self.calendar_connect_box.setObjectName("formBox")
        connect_layout = QVBoxLayout(self.calendar_connect_box)
        connect_layout.setContentsMargins(0, 0, 0, 0)
        connect_layout.setSpacing(6)
        connect_hint = QLabel(
            "Google Calendar → Settings → your calendar → Integrate calendar → "
            "copy “Secret address in iCal format” and paste it here."
        )
        connect_hint.setObjectName("muted")
        connect_hint.setWordWrap(True)
        connect_row = QHBoxLayout()
        connect_row.setSpacing(6)
        self.calendar_url_edit = QLineEdit()
        self.calendar_url_edit.setPlaceholderText("https://calendar.google.com/calendar/ical/…/basic.ics")
        self.calendar_url_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.calendar_url_edit.returnPressed.connect(self._submit_calendar)
        connect_btn = QPushButton("Connect")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.clicked.connect(self._submit_calendar)
        connect_row.addWidget(self.calendar_url_edit, 1)
        connect_row.addWidget(connect_btn)
        connect_layout.addWidget(connect_hint)
        connect_layout.addLayout(connect_row)
        body.addWidget(self.calendar_connect_box)

        self.calendar_manage_box = QWidget()
        self.calendar_manage_box.setObjectName("formBox")
        manage_row = QHBoxLayout(self.calendar_manage_box)
        manage_row.setContentsMargins(0, 0, 0, 0)
        manage_row.setSpacing(6)
        sync_btn = QPushButton("Sync Now")
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.clicked.connect(self.calendar_sync_requested.emit)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.setObjectName("danger")
        disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        disconnect_btn.clicked.connect(self.calendar_disconnect_requested.emit)
        manage_row.addStretch(1)
        manage_row.addWidget(sync_btn)
        manage_row.addWidget(disconnect_btn)
        body.addWidget(self.calendar_manage_box)
        self.set_calendar_state(False, "Google Calendar is not connected.")
        body.addStretch(1)

        scroll.setWidget(content)
        frame_layout.addWidget(scroll, 1)
        content.setStyleSheet("QWidget#scrollBody { background: transparent; }")

        self.refresh_profiles()
        self.set_events([])

    def _editor(self, placeholder: str) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setPlaceholderText(placeholder)
        editor.setFixedHeight(58)
        editor.setTabChangesFocus(True)
        return editor

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(self.rect().adjusted(10, 12, -6, -4), 18, 18)

    def present_near(self, anchor: QWidget) -> None:
        self.refresh_profiles()
        screen = QApplication.screenAt(anchor.frameGeometry().center())
        if screen is None:
            screen = anchor.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            height = min(720, max(520, avail.height() - 32))
            self.resize(480, height)
            anchor_rect = anchor.frameGeometry()
            x = anchor_rect.left() - self.width() - 14
            if x < avail.left():
                x = anchor_rect.right() + 14
            x = max(avail.left() + 8, min(x, avail.right() - self.width() - 8))
            y = anchor_rect.center().y() - int(self.height() / 2)
            y = max(avail.top() + 8, min(y, avail.bottom() - self.height() - 8))
            self.move(int(x), int(y))
        self.show()
        self.raise_()
        self.activateWindow()

    def set_stats(self, stats: dict) -> None:
        cpu = float(stats.get("cpu") or 0)
        memory = stats.get("memory") or {}
        disk = stats.get("disk") or {}
        battery = stats.get("battery")
        self.cpu_row.set_reading(cpu, f"{cpu:.0f}%")
        used = float(memory.get("used") or 0)
        total = float(memory.get("total") or 0)
        ram_text = f"{_gb(used)} / {_gb(total, 0)} GB" if total else "—"
        self.ram_row.set_reading(float(memory.get("percent") or 0), ram_text)
        free = float(disk.get("free") or 0)
        disk_text = f"{_gb(free, 0)} GB free" if disk else "—"
        self.disk_row.set_reading(float(disk.get("percent") or 0), disk_text)
        if not isinstance(battery, dict):
            self.battery_row.set_empty("n/a")
        else:
            percent = float(battery.get("percent") or 0)
            if battery.get("plugged"):
                text = f"{percent:.0f}% • plugged in"
            else:
                left = _remaining(battery.get("secs_left"))
                text = f"{percent:.0f}%" + (f" • {left}" if left else "")
            self.battery_row.set_reading(percent, text, low_is_bad=True)

        plan = stats.get("power_plan")
        if not isinstance(plan, dict):
            return
        self.plan_label.setText(f"Active Plan: {plan.get('label') or '—'}")
        plan_id = str(plan.get("id") or "")
        if plan_id != self._active_plan:
            self._active_plan = plan_id
            for key, button in self._plan_buttons.items():
                self._restyle(button, active=key == plan_id)

    def set_processes(self, processes: list[dict]) -> None:
        self._last_processes = processes
        for index, row in enumerate(self.process_rows):
            if index < len(processes):
                row.show_process(processes[index], self._armed_process)
            else:
                row.set_visible(False)
        if not processes:
            self.process_hint.setText("No process data available.")
        else:
            self.process_hint.setText("Grouped by name • Power is estimated from CPU and RAM load.")

    def set_calendar_state(self, connected: bool, status: str) -> None:
        self.calendar_status.setText(status)
        self.calendar_connect_box.setVisible(not connected)
        self.calendar_manage_box.setVisible(connected)
        if connected:
            self.calendar_url_edit.clear()

    def _submit_calendar(self) -> None:
        url = self.calendar_url_edit.text().strip()
        if not url:
            self.calendar_status.setText("Paste your secret iCal address first.")
            return
        self.calendar_connect_requested.emit(url)

    def set_events(self, events: list[dict]) -> None:
        self._clear(self.event_layout)
        if not events:
            empty = QLabel("No upcoming events.")
            empty.setObjectName("muted")
            self.event_layout.addWidget(empty)
            return
        now = datetime.now()
        for event in events:
            start = event.get("start_dt")
            title = str(event.get("title") or "Event")
            if isinstance(start, datetime) and event.get("all_day"):
                days = (start.date() - now.date()).days
                extra = " • today" if days == 0 else " • tomorrow" if days == 1 else ""
                text = f"{start.strftime('%d %b')} all day{extra}   {title}"
            elif isinstance(start, datetime):
                when = start.strftime("%d %b %H:%M")
                mins = int((start - now).total_seconds() // 60)
                if mins < 0:
                    extra = " • now"
                elif mins < 60:
                    extra = f" • in {mins} min"
                elif mins < 60 * 36:
                    extra = f" • in {mins // 60} h"
                else:
                    extra = ""
                text = f"{when}{extra}   {title}"
            else:
                text = title
            label = QLabel(text)
            label.setObjectName("mono")
            label.setWordWrap(True)
            self.event_layout.addWidget(label)

    def refresh_profiles(self) -> None:
        self._clear(self.profile_layout)
        try:
            profiles = self.workspaces.list_profiles()
        except ValueError as exc:
            self.show_feedback(str(exc))
            return
        if not profiles:
            empty = QLabel("No profiles yet.")
            empty.setObjectName("muted")
            self.profile_layout.addWidget(empty)
            return
        for profile in profiles:
            self.profile_layout.addWidget(self._profile_row(profile))

    def show_feedback(self, text: str) -> None:
        self.feedback.setText(text)

    def clear_form(self) -> None:
        self.name_edit.clear()
        for editor in (self.apps_edit, self.folders_edit, self.urls_edit, self.kill_edit):
            editor.clear()
        self.feedback.setText("Saved.")

    def _on_end_clicked(self, name: str) -> None:
        if not name:
            return
        if self._armed_process != name:
            self._armed_process = name
            self._disarm_timer.start(3000)
            self.set_processes(self._last_processes)
            return
        self._disarm_process()
        self.process_end_requested.emit(name)

    def _disarm_process(self) -> None:
        self._disarm_timer.stop()
        self._armed_process = ""
        self.set_processes(self._last_processes)

    def _toggle_form(self) -> None:
        visible = not self.form.isVisible()
        self.form.setVisible(visible)
        self.form_button.setText("Close Form" if visible else "New Profile")
        if visible:
            self.name_edit.setFocus()

    def _submit(self) -> None:
        name = self.name_edit.text().strip()
        profile = {
            "name": name,
            "apps": _lines(self.apps_edit),
            "folders": _lines(self.folders_edit),
            "urls": _lines(self.urls_edit),
            "kill": _lines(self.kill_edit),
        }
        if not name:
            self.show_feedback("Profile name is required.")
            return
        if not any(profile[key] for key in ("apps", "folders", "urls", "kill")):
            self.show_feedback("Enter at least one app, folder, website or process.")
            return
        self.profile_submitted.emit(profile)

    def _profile_row(self, profile: dict) -> QWidget:
        name = str(profile.get("name") or "")
        row = QWidget()
        row.setObjectName("profileRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(name)
        label.setObjectName("mono")
        label.setWordWrap(True)
        tips: list[str] = []
        for key, title in (
            ("apps", "Apps"),
            ("folders", "Folders"),
            ("urls", "Websites"),
            ("kill", "Close"),
        ):
            values = profile.get(key) or []
            if values:
                tips.append(f"{title}: {', '.join(str(value) for value in values)}")
        row.setToolTip("\n".join(tips) if tips else name)
        open_btn = QPushButton("Launch")
        open_btn.setFixedWidth(72)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda _checked=False, profile_name=name: self.launch_requested.emit(profile_name))
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("danger")
        delete_btn.setFixedWidth(72)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(
            lambda _checked=False, profile_name=name, button=delete_btn: self._confirm_delete(profile_name, button)
        )
        layout.addWidget(label, 1)
        layout.addWidget(open_btn)
        layout.addWidget(delete_btn)
        return row

    def _confirm_delete(self, name: str, button: QPushButton) -> None:
        if button.property("armed") != name:
            button.setProperty("armed", name)
            button.setText("Sure?")
            QTimer.singleShot(2500, lambda b=button, profile_name=name: self._disarm(b, profile_name))
            return
        self.delete_requested.emit(name)

    def _disarm(self, button: QPushButton, name: str) -> None:
        try:
            if button.property("armed") == name:
                button.setProperty("armed", None)
                button.setText("Delete")
        except RuntimeError:
            return

    def _restyle(self, button: QPushButton, active: bool | None = None) -> None:
        if active is None:
            active = bool(button.property("active"))
        button.setProperty("active", active)
        button.setStyleSheet(ACTIVE_BUTTON_QSS if active else "")

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
