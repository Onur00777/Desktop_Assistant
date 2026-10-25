"""Kompakt kontrol paneli."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.workspace_manager import WorkspaceManager
from ui.styles import ACTIVE_BUTTON_QSS


def _gb(num: float, digits: int = 1) -> str:
    return f"{num / (1024 ** 3):.{digits}f}"


def _remaining(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    minutes = int(seconds) // 60
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours} sa {mins} dk"
    return f"{mins} dk"


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section")
    return label


def _hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background: #173222;")
    return line


def _lines(editor: QPlainTextEdit) -> list[str]:
    return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]


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


class StatRow(QWidget):
    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("statRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.caption = QLabel(caption)
        self.caption.setObjectName("mono")
        self.caption.setFixedWidth(48)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.value = QLabel("—")
        self.value.setObjectName("mono")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value.setMinimumWidth(136)
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


class Dashboard(QWidget):
    launch_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    profile_submitted = pyqtSignal(object)
    power_requested = pyqtSignal(str)
    quote_requested = pyqtSignal()

    def __init__(self, workspaces: WorkspaceManager) -> None:
        super().__init__()
        self.workspaces = workspaces
        self._active_plan = ""
        self._plan_buttons: dict[str, QPushButton] = {}

        self.setObjectName("dashboardRoot")
        self.setWindowTitle("Masaüstü Asistan")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setMinimumSize(420, 520)
        self.resize(440, 640)
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
        title = QLabel("MASAÜSTÜ ASİSTAN")
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
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setObjectName("scrollBody")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 4, 0)
        body.setSpacing(8)

        body.addWidget(_section("SİSTEM"))
        self.cpu_row = StatRow("CPU")
        self.ram_row = StatRow("RAM")
        self.disk_row = StatRow("DİSK")
        self.battery_row = StatRow("PİL")
        for row in (self.cpu_row, self.ram_row, self.disk_row, self.battery_row):
            body.addWidget(row)

        self.plan_label = QLabel("Etkin plan: —")
        self.plan_label.setObjectName("muted")
        body.addWidget(self.plan_label)

        plans = QHBoxLayout()
        plans.setSpacing(8)
        for plan_id, label, tip in (
            ("saver", "Tasarruf", "Güç Tasarrufu"),
            ("balanced", "Dengeli", "Dengeli"),
            ("performance", "Performans", "Yüksek Performans"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, pid=plan_id: self.power_requested.emit(pid))
            self._plan_buttons[plan_id] = button
            plans.addWidget(button, 1)
        body.addLayout(plans)
        body.addWidget(_hline())

        body.addWidget(_section("ÇALIŞMA ALANLARI"))
        self.profile_layout = QVBoxLayout()
        self.profile_layout.setSpacing(6)
        body.addLayout(self.profile_layout)

        self.form_button = QPushButton("Yeni profil")
        self.form_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.form_button.clicked.connect(self._toggle_form)
        body.addWidget(self.form_button)

        self.form = QWidget()
        self.form.setObjectName("formBox")
        form_layout = QVBoxLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Profil adı  ·  örn. Kodlama")
        self.apps_edit = self._editor("Her satıra bir uygulama\nörn. code")
        self.folders_edit = self._editor("Her satıra bir klasör yolu")
        self.urls_edit = self._editor("https://github.com")
        self.kill_edit = self._editor("Spotify.exe")
        self.feedback = QLabel("")
        self.feedback.setObjectName("muted")
        self.feedback.setWordWrap(True)
        save = QPushButton("Kaydet")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setProperty("active", True)
        save.clicked.connect(self._submit)
        self.name_edit.returnPressed.connect(self._submit)
        form_layout.addWidget(self.name_edit)
        for caption, editor in (
            ("Uygulamalar", self.apps_edit),
            ("Klasörler", self.folders_edit),
            ("Siteler", self.urls_edit),
            ("Kapatılacak işlemler", self.kill_edit),
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
        upcoming.addWidget(_section("YAKLAŞAN"))
        upcoming.addStretch(1)
        quote_btn = QPushButton("Söz getir")
        quote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quote_btn.clicked.connect(self.quote_requested.emit)
        upcoming.addWidget(quote_btn)
        body.addLayout(upcoming)

        self.event_layout = QVBoxLayout()
        self.event_layout.setSpacing(4)
        body.addLayout(self.event_layout)
        hint = QLabel("Etkinlikler data/events.json dosyasından okunur.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        body.addWidget(hint)
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
            height = min(660, max(520, avail.height() - 32))
            self.resize(440, height)
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
        self.cpu_row.set_reading(cpu, f"%{cpu:.0f}")
        used = float(memory.get("used") or 0)
        total = float(memory.get("total") or 0)
        ram_text = f"{_gb(used)}/{_gb(total, 0)} GB" if total else "—"
        self.ram_row.set_reading(float(memory.get("percent") or 0), ram_text)
        free = float(disk.get("free") or 0)
        disk_text = f"{_gb(free, 0)} GB boş" if disk else "—"
        self.disk_row.set_reading(float(disk.get("percent") or 0), disk_text)
        if not isinstance(battery, dict):
            self.battery_row.set_empty("yok")
        else:
            percent = float(battery.get("percent") or 0)
            if battery.get("plugged"):
                text = f"%{percent:.0f} AC"
            else:
                left = _remaining(battery.get("secs_left"))
                text = f"%{percent:.0f}" + (f" · {left}" if left else "")
            self.battery_row.set_reading(percent, text, low_is_bad=True)

        plan = stats.get("power_plan")
        if not isinstance(plan, dict):
            return
        self.plan_label.setText(f"Etkin plan: {plan.get('label') or '—'}")
        plan_id = str(plan.get("id") or "")
        if plan_id != self._active_plan:
            self._active_plan = plan_id
            for key, button in self._plan_buttons.items():
                self._restyle(button, active=key == plan_id)

    def set_events(self, events: list[dict]) -> None:
        self._clear(self.event_layout)
        if not events:
            empty = QLabel("Yaklaşan etkinlik yok.")
            empty.setObjectName("muted")
            self.event_layout.addWidget(empty)
            return
        now = datetime.now()
        for event in events:
            start = event.get("start_dt")
            title = str(event.get("title") or "Etkinlik")
            if isinstance(start, datetime):
                when = start.strftime("%d.%m %H:%M")
                mins = int((start - now).total_seconds() // 60)
                if mins < 0:
                    extra = " · şimdi"
                elif mins < 60:
                    extra = f" · {mins} dk"
                elif mins < 60 * 36:
                    extra = f" · {mins // 60} sa"
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
            empty = QLabel("Henüz profil yok.")
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
        self.feedback.setText("Kaydedildi.")

    def _toggle_form(self) -> None:
        visible = not self.form.isVisible()
        self.form.setVisible(visible)
        self.form_button.setText("Formu kapat" if visible else "Yeni profil")
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
            self.show_feedback("Profil adı gerekli.")
            return
        if not any(profile[key] for key in ("apps", "folders", "urls", "kill")):
            self.show_feedback("En az bir uygulama, klasör, site veya işlem gir.")
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
            ("apps", "Uygulama"),
            ("folders", "Klasör"),
            ("urls", "Site"),
            ("kill", "Kapat"),
        ):
            values = profile.get(key) or []
            if values:
                tips.append(f"{title}: {', '.join(str(value) for value in values)}")
        row.setToolTip("\n".join(tips) if tips else name)
        open_btn = QPushButton("Aç")
        open_btn.setFixedWidth(52)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda _checked=False, profile_name=name: self.launch_requested.emit(profile_name))
        delete_btn = QPushButton("Sil")
        delete_btn.setObjectName("danger")
        delete_btn.setFixedWidth(58)
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
            button.setText("Emin?")
            QTimer.singleShot(2500, lambda b=button, profile_name=name: self._disarm(b, profile_name))
            return
        self.delete_requested.emit(name)

    def _disarm(self, button: QPushButton, name: str) -> None:
        try:
            if button.property("armed") == name:
                button.setProperty("armed", None)
                button.setText("Sil")
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
