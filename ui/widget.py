"""Sürüklenebilir, çerçevesiz masaüstü ikonu."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QMenu, QWidget

from ui.mark import paint_mark


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

        self.setObjectName("desktopWidget")
        self.setWindowTitle("Masaüstü Asistan")
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
        self.setFixedSize(88, 88)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet("QWidget#desktopWidget { background: transparent; }")
        self.setToolTip("Masaüstü Asistan\nSürükle · Sol tık: panel · Sağ tık: menü")

    def set_status(self, cpu: float, ram: float | None = None) -> None:
        cpu = max(0.0, min(100.0, float(cpu)))
        ram_text = f" · RAM %{ram:.0f}" if ram is not None else ""
        self.setToolTip(
            f"Masaüstü Asistan\nCPU %{cpu:.0f}{ram_text}\nSürükle · Sol tık: panel · Sağ tık: menü"
        )
        if abs(cpu - self._cpu) < 0.5:
            return
        self._cpu = cpu
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(0, 255, 65, 78 if self._hover else 42), 6)
        painter.setPen(pen)
        painter.drawEllipse(center, 33, 33)
        paint_mark(painter, QRectF(14, 14, 60, 60), self._cpu)

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
        menu.addAction("Paneli aç", self.open_requested.emit)
        menu.addAction("Gizle", self.hide_requested.emit)
        menu.addSeparator()
        menu.addAction("Çıkış", self.quit_requested.emit)
        menu.exec(event.globalPos())

    def closeEvent(self, event) -> None:
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide_requested.emit()
