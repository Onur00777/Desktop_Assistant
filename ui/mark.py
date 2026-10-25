"""Terminal işaretli masaüstü ikonu çizimi."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from ui.styles import ACCENT


def paint_mark(painter: QPainter, rect: QRectF, cpu: float) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    side = min(rect.width(), rect.height())
    square = QRectF(
        rect.center().x() - side / 2,
        rect.center().y() - side / 2,
        side,
        side,
    )
    disk = square.adjusted(3, 3, -3, -3)
    painter.setPen(QPen(QColor(ACCENT), 2))
    painter.setBrush(QColor(8, 14, 10, 238))
    painter.drawEllipse(disk)

    arc = square.adjusted(7, 7, -7, -7)
    track = QPen(QColor(0, 255, 65, 48), 3)
    track.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(track)
    painter.drawEllipse(arc)

    span = -int(round(max(0.0, min(100.0, cpu)) / 100 * 360 * 16))
    if span:
        pen = QPen(QColor(ACCENT), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc, 90 * 16, span)

    painter.setPen(QColor(ACCENT))
    font = QFont("Consolas")
    font.setPixelSize(max(12, int(side * 0.28)))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(square, int(Qt.AlignmentFlag.AlignCenter), ">_")


def render_icon(cpu: float = 0, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_mark(painter, QRectF(1, 1, size - 2, size - 2), cpu)
    painter.end()
    return QIcon(pixmap)
