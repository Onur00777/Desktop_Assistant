"""Charcoal surfaces with a muted green accent."""

BG = "#202321"
SURFACE = "#282c29"
BORDER = "#3b433e"
TEXT = "#edf0ed"
MUTED = "#aeb8b0"
ACCENT = "#a6c7ac"
ACCENT_BG = "#34483a"
HOVER = "#353c37"
WARNING = "#dfb779"
DANGER = "#e5a29a"

APP_QSS = f"""
QFrame#panel {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QWidget#scrollBody,
QWidget#dragHeader,
QWidget#statRow,
QWidget#profileRow,
QWidget#processBox,
QWidget#formBox {{
    background: transparent;
}}
QWidget#clickArea {{
    background: transparent;
    border-radius: 7px;
}}
QWidget#clickArea:hover {{
    background: {SURFACE};
}}
QFrame#summaryCard,
QFrame#dayColumn,
QFrame#todayColumn {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#todayColumn {{
    border-color: #57715f;
}}
QLabel {{
    background: transparent;
    color: {TEXT};
}}
QLabel#title {{
    font-size: 19px;
    font-weight: 600;
}}
QLabel#section {{
    font-size: 14px;
    font-weight: 600;
}}
QLabel#muted,
QLabel#dayName {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#dayDate,
QLabel#todayDate {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#todayName,
QLabel#todayDate {{
    color: {ACCENT};
    background: {ACCENT_BG};
}}
QLabel#todayName {{
    font-size: 12px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding-top: 4px;
}}
QLabel#todayDate {{
    padding-bottom: 4px;
}}
QFrame#eventCard,
QFrame#eventCardPast {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 7px;
}}
QLabel#eventTime {{
    font-size: 12px;
    font-weight: 600;
    color: {ACCENT};
}}
QLabel#eventTitle,
QLabel#eventPast,
QLabel#cell {{
    font-size: 12px;
}}
QLabel#eventPast,
QLabel#cellHead {{
    color: {MUTED};
}}
QLabel#cellHead {{
    font-size: 11px;
    font-weight: 600;
}}
QPushButton {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 10px;
}}
QPushButton:hover {{
    background: {HOVER};
    border-color: #5a695f;
}}
QPushButton:pressed,
QPushButton[active="true"] {{
    background: {ACCENT_BG};
    border-color: #65846d;
    color: {ACCENT};
}}
QPushButton[active="true"] {{
    font-weight: 600;
}}
QPushButton[active="true"]:hover {{
    background: #405648;
}}
QPushButton:focus,
QLineEdit:focus,
QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QPushButton#endBtn,
QPushButton#danger {{
    background: transparent;
    color: {MUTED};
}}
QPushButton#endBtn {{
    padding: 2px 6px;
    font-size: 12px;
}}
QPushButton#endBtn:hover,
QPushButton#danger:hover {{
    background: #42302e;
    color: {DANGER};
    border-color: #805650;
}}
QPushButton#endBtn:disabled {{
    color: #777e78;
    border-color: transparent;
}}
QPushButton#closeBtn {{
    background: transparent;
    border-color: transparent;
    color: {MUTED};
    font-size: 18px;
    padding: 0;
}}
QPushButton#closeBtn:hover {{
    background: {HOVER};
    color: {TEXT};
}}
QLineEdit, QPlainTextEdit {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: {BG};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 0;
}}
QScrollBar::handle:vertical {{
    background: #536058;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0;
}}
QMenu, QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {HOVER};
    color: {TEXT};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}
QMessageBox {{
    background: {BG};
}}
"""
