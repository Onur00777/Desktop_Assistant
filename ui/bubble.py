"""Speech bubble shown next to the desktop icon."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ui.styles import ACCENT

QUOTE = "QUOTE"
INFO = "SYSTEM INFO"
ALERT = "SYSTEM ALERT"
EVENT = "EVENT"

_KIND_COLORS = {
    QUOTE: "#00FF41",
    ALERT: "#ffb020",
    EVENT: "#8dffc1",
    INFO: "#00FF41",
}


class SpeechBubble(QWidget):
    shown = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._anchor: QWidget | None = None
        self._tail = "bottom"
        self._queue: list[tuple[str, str, int]] = []
        self._suspended = False

        self.setObjectName("bubble")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QWidget#bubble { background: transparent; }"
            "QLabel { background: transparent; color: #d7ffe4; }"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 24)
        self._layout.setSpacing(4)

        self.kind_label = QLabel(INFO)
        kind_font = QFont("Consolas", 9)
        kind_font.setBold(True)
        self.kind_label.setFont(kind_font)
        self.body = QLabel("")
        self.body.setFont(QFont("Segoe UI", 11))
        self.body.setWordWrap(True)
        self.body.setFixedWidth(252)
        self.kind_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._layout.addWidget(self.kind_label)
        self._layout.addWidget(self.body)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def bind(self, anchor: QWidget) -> None:
        self._anchor = anchor

    def push(self, kind: str, text: str, timeout_ms: int = 11000, now: bool = False) -> None:
        """Queue a message. With now=True it replaces whatever is on screen."""
        clean = " ".join(str(text).split())
        if not clean:
            return
        if len(clean) > 360:
            clean = clean[:357] + "..."
        if now:
            self._queue.insert(0, (kind, clean, timeout_ms))
        else:
            self._queue.append((kind, clean, timeout_ms))
        if len(self._queue) > 6:
            self._queue = self._queue[:6] if now else self._queue[-6:]
        if self._suspended:
            return
        if now or not self.isVisible():
            self._timer.stop()
            self._show_next()

    def suspend(self) -> None:
        self._suspended = True
        self._timer.stop()
        self.hide()

    def resume(self) -> None:
        self._suspended = False
        if self._queue and not self.isVisible():
            self._show_next()

    def sync_position(self) -> None:
        anchor = self._anchor
        if anchor is None:
            return
        anchor_rect = anchor.frameGeometry()
        screen = QApplication.screenAt(anchor_rect.center())
        if screen is None:
            screen = anchor.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else None
        gap = 8
        tail = "bottom"
        if avail is not None and anchor_rect.top() - self.height() - gap < avail.top() + 4:
            tail = "top"
        if tail != self._tail:
            self._set_tail(tail)
            self._resize_to_text()
        x = anchor_rect.center().x() - self.width() // 2
        y = anchor_rect.top() - self.height() - gap if self._tail == "bottom" else anchor_rect.bottom() + gap
        if avail is not None:
            x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
            y = max(avail.top() + 4, min(y, avail.bottom() - self.height() - 4))
        self.move(int(x), int(y))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body, tail = self._shape()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 85))
        painter.drawRoundedRect(body.translated(0, 3), 12, 12)
        painter.setPen(QPen(QColor(ACCENT), 1.4))
        painter.setBrush(QColor(12, 18, 14, 244))
        painter.drawRoundedRect(body, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(12, 18, 14, 244))
        painter.drawPolygon(tail)
        painter.setPen(QPen(QColor(ACCENT), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(tail)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._timer.stop()
            self._on_timeout()
            event.accept()
            return
        super().mousePressEvent(event)

    def _show_next(self) -> None:
        if self._suspended or not self._queue:
            self.hide()
            return
        kind, text, timeout = self._queue.pop(0)
        self._apply_kind(kind)
        self.body.setText(text)
        if self._tail != "bottom":
            self._set_tail("bottom")
        self._resize_to_text()
        self.sync_position()
        self.show()
        self.raise_()
        self._timer.start(max(2500, timeout))
        self.shown.emit(kind)

    def _on_timeout(self) -> None:
        if self._suspended:
            self.hide()
            return
        if self._queue:
            self._show_next()
            return
        self.hide()

    def _apply_kind(self, kind: str) -> None:
        color = _KIND_COLORS.get(kind, ACCENT)
        self.kind_label.setText(kind)
        self.kind_label.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: 700; letter-spacing: 1px;"
        )

    def _set_tail(self, tail: str) -> None:
        self._tail = tail
        if tail == "bottom":
            self._layout.setContentsMargins(16, 12, 16, 24)
        else:
            self._layout.setContentsMargins(16, 24, 16, 12)

    def _resize_to_text(self) -> None:
        self.body.setFixedWidth(252)
        self._layout.activate()
        hint = self.sizeHint()
        self.resize(max(284, hint.width()), max(76, hint.height()))

    def _shape(self) -> tuple[QRectF, QPolygonF]:
        width = self.width()
        height = self.height()
        tail_h = 12
        if self._tail == "bottom":
            body = QRectF(1.5, 1.5, width - 3, height - tail_h - 1)
            base_y = body.bottom() - 3
            tip_y = height - 2
        else:
            body = QRectF(1.5, tail_h, width - 3, height - tail_h - 1.5)
            base_y = body.top() + 3
            tip_y = 2.0
        center_x = width / 2
        if self._anchor is not None:
            local = self._anchor.frameGeometry().center().x() - self.x()
            center_x = max(22, min(width - 22, local))
        tail = QPolygonF(
            [
                QPointF(center_x - 9, base_y),
                QPointF(center_x, tip_y),
                QPointF(center_x + 9, base_y),
            ]
        )
        return body, tail
