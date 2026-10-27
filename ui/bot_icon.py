"""Robot face images: white background removal, alignment and scaling."""

from __future__ import annotations

from collections import deque
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

from ui.styles import ACCENT

ASSETS = Path(__file__).resolve().parent.parent / "assets"
NORMAL_PATH = ASSETS / "Bot-icon.png"
HAPPY_PATH = ASSETS / "Bot-icon-happy.png"

WHITE_CUTOFF = 245
FEATHER_FROM = 200
OUTLINE_MAX = 140
WORK_SIZE = 420
INNER_RATIO = 0.74


def remove_white_background(image: QImage) -> QImage:
    """Make white pixels connected to the image border fully transparent.

    White areas enclosed by the outline (the robot's face and body) stay opaque.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    pointer = image.constBits()
    pointer.setsize(image.sizeInBytes())
    data = bytearray(pointer.asstring())

    def offset(x: int, y: int) -> int:
        return y * stride + x * 4

    def is_white(x: int, y: int) -> bool:
        i = offset(x, y)
        return data[i] > WHITE_CUTOFF and data[i + 1] > WHITE_CUTOFF and data[i + 2] > WHITE_CUTOFF

    cleared = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if cleared[index] or not is_white(x, y):
            continue
        cleared[index] = 1
        data[offset(x, y) + 3] = 0
        if x > 0:
            queue.append((x - 1, y))
        if x < width - 1:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y < height - 1:
            queue.append((x, y + 1))

    # Soften the light anti-aliased edge between the removed background and the outline.
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            index = row + x
            if cleared[index]:
                continue
            if not (cleared[index - 1] or cleared[index + 1] or cleared[index - width] or cleared[index + width]):
                continue
            i = offset(x, y)
            lightest = min(data[i], data[i + 1], data[i + 2])
            if lightest > FEATHER_FROM:
                data[i + 3] = int(255 * (255 - lightest) / (255 - FEATHER_FROM))

    return QImage(bytes(data), width, height, stride, QImage.Format.Format_ARGB32).copy()


def outline_bounds(image: QImage) -> QRectF:
    """Bounding box of the dark robot outline, ignoring light effect strokes."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    pointer = image.constBits()
    pointer.setsize(image.sizeInBytes())
    data = pointer.asstring()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        base = y * stride
        for x in range(width):
            i = base + x * 4
            if data[i + 3] > 128 and max(data[i], data[i + 1], data[i + 2]) < OUTLINE_MAX:
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y
    if right < 0:
        return QRectF(0, 0, width, height)
    return QRectF(left, top, right - left + 1, bottom - top + 1)


def _working_copy(path: Path) -> QImage:
    image = QImage(str(path))
    if image.isNull():
        raise FileNotFoundError(f"Missing icon image: {path}")
    return image.scaled(
        WORK_SIZE,
        WORK_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


@lru_cache(maxsize=1)
def aligned_faces() -> tuple[QImage, QImage]:
    """Both faces on identical square canvases with the robot outline centered.

    The canvas side comes from the larger outline, and each image is scaled so its
    outline has the same height, so the head never moves during a cross-fade.
    """
    sources = [_working_copy(NORMAL_PATH), _working_copy(HAPPY_PATH)]
    cleaned = [remove_white_background(image) for image in sources]
    bounds = [outline_bounds(image) for image in cleaned]
    reference = max(bounds[0].height(), bounds[1].height())
    side = int(round(max(max(b.width(), b.height()) * reference / b.height() for b in bounds) * 1.04))
    faces: list[QImage] = []
    for image, box in zip(cleaned, bounds):
        scale = reference / box.height()
        canvas = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(side / 2, side / 2)
        painter.scale(scale, scale)
        painter.translate(-box.center())
        painter.drawImage(QPointF(0, 0), image)
        painter.end()
        faces.append(canvas)
    return faces[0], faces[1]


def face_pixmap(image: QImage, side: int, device_ratio: float) -> QPixmap:
    pixels = max(1, int(round(side * device_ratio)))
    scaled = image.scaled(
        pixels,
        pixels,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    pixmap = QPixmap.fromImage(scaled)
    pixmap.setDevicePixelRatio(device_ratio)
    return pixmap


def paint_badge(
    painter: QPainter,
    center: QPointF,
    radius: float,
    normal: QPixmap,
    happy: QPixmap | None = None,
    happy_opacity: float = 0.0,
    cpu: float | None = None,
) -> None:
    """Dark disc, neon ring and optional CPU arc, with the face clipped inside the ring."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setPen(QPen(QColor(ACCENT), 2))
    painter.setBrush(QColor(8, 14, 10, 238))
    painter.drawEllipse(center, radius - 1, radius - 1)

    ring = radius - 4.5
    if cpu is not None:
        track = QPen(QColor(0, 255, 65, 48), 3)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(track)
        painter.drawEllipse(center, ring, ring)
        span = -int(round(max(0.0, min(100.0, cpu)) / 100 * 360 * 16))
        if span:
            pen = QPen(QColor(ACCENT), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(QRectF(center.x() - ring, center.y() - ring, ring * 2, ring * 2), 90 * 16, span)

    side = normal.width() / normal.devicePixelRatio()
    target = QRectF(center.x() - side / 2, center.y() - side / 2, side, side)
    clip = QPainterPath()
    clip_radius = ring - 2 if cpu is not None else radius - 3
    clip.addEllipse(center, clip_radius, clip_radius)

    painter.save()
    painter.setClipPath(clip)
    if happy is None or happy_opacity < 0.999:
        painter.setOpacity(1.0)
        painter.drawPixmap(target.topLeft(), normal)
    if happy is not None and happy_opacity > 0.001:
        painter.setOpacity(happy_opacity)
        painter.drawPixmap(target.topLeft(), happy)
    painter.restore()


def render_app_icon(size: int = 64) -> QIcon:
    normal, _happy = aligned_faces()
    radius = size / 2
    face_side = int(round(size * INNER_RATIO))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_badge(painter, QPointF(radius, radius), radius, face_pixmap(normal, face_side, 1.0))
    painter.end()
    return QIcon(pixmap)
