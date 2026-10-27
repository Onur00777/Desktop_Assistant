"""Seven-day schedule table opened from Upcoming Events."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.dashboard import DragHeader

DAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MAX_WEEKS_AHEAD = 8

WeekLoader = Callable[[date], dict[date, list[dict]]]


def _label(text: str, name: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return label


def _short_date(day: date) -> str:
    return f"{day.day} {day:%b}"


class WeekView(QWidget):
    def __init__(self, load_week: WeekLoader) -> None:
        super().__init__()
        self.load_week = load_week
        self.offset = 0

        self.setObjectName("weekRoot")
        self.setWindowTitle("Week Schedule")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.resize(1000, 560)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.hide)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 10)
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(frame)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(16, 12, 16, 14)
        frame_layout.setSpacing(10)

        header = DragHeader(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title = _label("WEEK SCHEDULE", "title")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.range_label = _label("", "muted")
        self.range_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.prev_btn = QPushButton("‹")
        self.today_btn = QPushButton("Today")
        self.next_btn = QPushButton("›")
        for button, step in ((self.prev_btn, -1), (self.next_btn, 1)):
            button.setFixedWidth(36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, s=step: self._go(self.offset + s))
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.clicked.connect(lambda: self._go(0))
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(title)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.range_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.prev_btn)
        header_layout.addWidget(self.today_btn)
        header_layout.addWidget(self.next_btn)
        header_layout.addSpacing(6)
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
        self.grid_host = QWidget()
        self.grid_host.setObjectName("scrollBody")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setHorizontalSpacing(8)
        for column in range(7):
            self.grid.setColumnStretch(column, 1)
        scroll.setWidget(self.grid_host)
        frame_layout.addWidget(scroll, 1)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(self.rect().adjusted(10, 12, -6, -4), 18, 18)

    def present(self, anchor: QWidget | None = None) -> None:
        self.offset = 0
        self.refresh()
        screen = None
        if anchor is not None:
            screen = QApplication.screenAt(anchor.frameGeometry().center()) or anchor.screen()
        screen = screen or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            width = min(1000, avail.width() - 40)
            height = min(560, avail.height() - 40)
            self.resize(width, height)
            self.move(avail.center().x() - width // 2, avail.center().y() - height // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self) -> None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=self.offset)
        week_end = week_start + timedelta(days=6)
        self.range_label.setText(
            ("This week" if self.offset == 0 else "Next week" if self.offset == 1 else f"In {self.offset} weeks")
            + f"  •  {_short_date(week_start)} – {_short_date(week_end)} {week_end.year}"
        )
        self.prev_btn.setEnabled(self.offset > 0)
        self.next_btn.setEnabled(self.offset < MAX_WEEKS_AHEAD)
        self.today_btn.setEnabled(self.offset != 0)

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        days = self.load_week(week_start)
        now = datetime.now()
        for column in range(7):
            day = week_start + timedelta(days=column)
            self.grid.addWidget(self._day_column(day, days.get(day, []), now), 0, column)

    def _go(self, offset: int) -> None:
        self.offset = max(0, min(MAX_WEEKS_AHEAD, offset))
        self.refresh()

    def _day_column(self, day: date, events: list[dict], now: datetime) -> QFrame:
        is_today = day == now.date()
        column = QFrame()
        column.setObjectName("todayColumn" if is_today else "dayColumn")
        column.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column.setMinimumWidth(110)
        layout = QVBoxLayout(column)
        margin = 2 if is_today else 1
        layout.setContentsMargins(margin, margin, margin, 8)
        layout.setSpacing(0)

        center = Qt.AlignmentFlag.AlignHCenter
        name = _label(DAY_NAMES[day.weekday()] + ("  •  TODAY" if is_today else ""), "todayName" if is_today else "dayName", center)
        stamp = _label(_short_date(day), "todayDate" if is_today else "dayDate", center)
        if not is_today:
            name.setContentsMargins(0, 8, 0, 0)
            stamp.setContentsMargins(0, 0, 0, 4)
        layout.addWidget(name)
        layout.addWidget(stamp)

        body = QVBoxLayout()
        body.setContentsMargins(6, 8, 6, 0)
        body.setSpacing(6)
        layout.addLayout(body)

        now_marked = not is_today
        for event in events:
            start = event["start_dt"]
            all_day = bool(event.get("all_day"))
            past = day < now.date() or (not all_day and start < now)
            if not now_marked and not all_day and start >= now:
                body.addWidget(self._now_line(now))
                now_marked = True
            body.addWidget(self._event_card(event, all_day, past))
        if not now_marked:
            body.addWidget(self._now_line(now))
        if not events:
            empty = _label("No events", "muted", center)
            empty.setContentsMargins(0, 6, 0, 0)
            body.addWidget(empty)
        body.addStretch(1)
        return column

    @staticmethod
    def _event_card(event: dict, all_day: bool, past: bool) -> QFrame:
        card = QFrame()
        card.setObjectName("eventCardPast" if past else "eventCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 7)
        layout.setSpacing(2)
        when = _label("ALL DAY" if all_day else event["start_dt"].strftime("%H:%M"), "eventTime")
        if past:
            when.setStyleSheet("color: #4f6656;")
        title = _label(str(event.get("title") or "Event"), "eventPast" if past else "eventTitle")
        title.setWordWrap(True)
        layout.addWidget(when)
        layout.addWidget(title)
        card.setToolTip(f"{event['start_dt']:%A %d %B %Y}" + ("" if all_day else f" • {event['start_dt']:%H:%M}") + f"\n{event.get('title') or 'Event'}")
        return card

    @staticmethod
    def _now_line(now: datetime) -> QLabel:
        line = _label(f"── now {now:%H:%M} ──", "eventTime", Qt.AlignmentFlag.AlignHCenter)
        line.setStyleSheet("font-size: 10px;")
        return line
