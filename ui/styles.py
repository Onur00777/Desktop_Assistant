"""Koyu terminal teması. Vurgu rengi neon yeşil."""

ACCENT = "#00FF41"

ACTIVE_BUTTON_QSS = """
QPushButton {
    background: #00FF41;
    color: #041208;
    border: none;
    border-radius: 8px;
    font-weight: 700;
    padding: 6px 10px;
}
QPushButton:hover {
    background: #6dff9a;
    color: #041208;
}
"""
BG = "#0c120e"
TEXT = "#d7ffe4"
MUTED = "#7d9a86"

APP_QSS = """
QFrame#panel {
    background-color: #0c120e;
    border: 1px solid #00FF41;
    border-radius: 16px;
}
QWidget#scrollBody,
QWidget#dragHeader,
QWidget#statRow,
QWidget#profileRow,
QWidget#formBox {
    background: transparent;
}
QLabel {
    background: transparent;
    color: #d7ffe4;
}
QLabel#title {
    color: #00FF41;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#section {
    color: #00FF41;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    letter-spacing: 1px;
}
QLabel#muted {
    color: #7d9a86;
    font-size: 12px;
}
QLabel#mono {
    font-family: Consolas, "Cascadia Mono", monospace;
    color: #d7ffe4;
}
QPushButton {
    background: transparent;
    color: #00FF41;
    border: 1px solid #1f6b38;
    border-radius: 8px;
    padding: 6px 10px;
}
QPushButton:hover {
    background: #12331f;
    border-color: #00FF41;
}
QPushButton:pressed {
    background: #00FF41;
    color: #041208;
}
QPushButton[active="true"] {
    background: #00FF41;
    color: #041208;
    font-weight: 700;
    border: none;
}
QPushButton[active="true"]:hover {
    background: #6dff9a;
    color: #041208;
}
QPushButton#danger {
    color: #ff8d8d;
    border-color: #5a2424;
}
QPushButton#danger:hover {
    background: #3a1414;
    color: #ffb4b4;
}
QPushButton#closeBtn {
    border: none;
    color: #d7ffe4;
    font-size: 18px;
    padding: 0;
    border-radius: 6px;
}
QPushButton#closeBtn:hover {
    background: #3a1414;
    color: #ffffff;
}
QLineEdit, QPlainTextEdit {
    background: #08110c;
    color: #d7ffe4;
    border: 1px solid #1f6b38;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #00FF41;
    selection-color: #041208;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: #1f6b38;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}
QMenu {
    background: #0c120e;
    color: #d7ffe4;
    border: 1px solid #00FF41;
    padding: 4px;
}
QMenu::item {
    padding: 6px 18px;
    background: transparent;
}
QMenu::item:selected {
    background: #12331f;
    color: #00FF41;
}
QMenu::separator {
    height: 1px;
    background: #173222;
    margin: 4px 8px;
}
QToolTip {
    background: #0c120e;
    color: #d7ffe4;
    border: 1px solid #00FF41;
}
QMessageBox {
    background: #0c120e;
}
QMessageBox QLabel {
    color: #d7ffe4;
}
"""
