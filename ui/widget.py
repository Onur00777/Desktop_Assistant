"""Draggable frameless desktop icon with a state-driven robot face."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QWidget

from ui.bot_icon import INNER_RATIO, aligned_faces, face_pixmap, paint_badge

NORMAL = "NORMAL"
HAPPY = "HAPPY"

SIZE = 96
BADGE_RADIUS = 36
FADE_MS = 220


class DesktopWidget(QWidget):
    clicked = pyqtSignal()
    open_requested = pyqtSignal()
    moved = pyqtSignal()
    dropped = pyqtSignal()
    hide_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._cpu = 0.0
        self._hover = False
        self._dragged = False
        self._press_global: QPointF | None = None
        self._origin: QPoint | None = None
        self.allow_close = False

        self.state = NORMAL
        self.happy_opacity = 0.0
        self._faces = aligned_faces()
        self._face_side = int(round(BADGE_RADIUS * 2 * INNER_RATIO))
        self._pixmaps: tuple[QPixmap, QPixmap] | None = None
        self._pixmap_ratio = 0.0

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade.valueChanged.connect(self._on_fade)
        self._revert = QTimer(self)
        self._revert.setSingleShot(True)
        self._revert.timeout.connect(lambda: self._set_state(NORMAL))

        self.setObjectName("desktopWidget")
        self.setWindowTitle("Desktop Assistant")
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
        self.setFixedSize(SIZE, SIZE)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet("QWidget#desktopWidget { background: transparent; }")
        self.setToolTip("Desktop Assistant\nDrag to move • Left click: dashboard • Right click: menu")

    def trigger_success_expression(self, duration_ms: int = 2500) -> None:
        self._set_state(HAPPY)
        self._revert.start(max(0, int(duration_ms)))

    def set_status(self, cpu: float, ram: float | None = None) -> None:
        cpu = max(0.0, min(100.0, float(cpu)))
        ram_text = f" • RAM {ram:.0f}%" if ram is not None else ""
        self.setToolTip(
            f"Desktop Assistant\nCPU {cpu:.0f}%{ram_text}\nDrag to move • Left click: dashboard • Right click: menu"
        )
        if abs(cpu - self._cpu) < 0.5:
            return
        self._cpu = cpu
        self.update()

    def _set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        self._fade.stop()
        self._fade.setStartValue(float(self.happy_opacity))
        self._fade.setEndValue(1.0 if state == HAPPY else 0.0)
        self._fade.start()

    def _on_fade(self, value: object) -> None:
        self.happy_opacity = float(value)
        self.update()

    def _face_pixmaps(self) -> tuple[QPixmap, QPixmap]:
        ratio = self.devicePixelRatioF()
        if self._pixmaps is None or abs(ratio - self._pixmap_ratio) > 0.01:
            normal, happy = self._faces
            self._pixmaps = (
                face_pixmap(normal, self._face_side, ratio),
                face_pixmap(happy, self._face_side, ratio),
            )
            self._pixmap_ratio = ratio
        return self._pixmaps

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 255, 65, 78 if self._hover else 42), 6))
        painter.drawEllipse(center, BADGE_RADIUS + 4, BADGE_RADIUS + 4)
        normal, happy = self._face_pixmaps()
        paint_badge(painter, center, BADGE_RADIUS, normal, happy, self.happy_opacity, self._cpu)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition()
            self._origin = self.pos()
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition() - self._press_global
        if delta.manhattanLength() > 6:
            self._dragged = True
            if self._origin is not None:
                self.move(self._origin + delta.toPoint())
                self.moved.emit()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            dragged = self._dragged
            self._press_global = None
            self._origin = None
            self._dragged = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if dragged:
                self.dropped.emit()
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("Open Dashboard", self.open_requested.emit)
        menu.addAction("Hide", self.hide_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_requested.emit)
        menu.exec(event.globalPos())

    def closeEvent(self, event) -> None:
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide_requested.emit()
