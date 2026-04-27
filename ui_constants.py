"""
UI constants, colours, global stylesheet, and small helper functions.
"""

from pathlib import Path
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel
from PyQt6.QtGui import QColor

# ─────────────────────────────────────────
# Colours & constants
# ─────────────────────────────────────────
BG        = "#F0F4F8"
CARD_BG   = "#FFFFFF"
BLUE      = "#1A73E8"
BLUE_DARK = "#1558B0"
NAVY      = "#0D2B6B"
LABEL_CLR = "#9E9E9E"
TEXT_CLR  = "#1A1A2E"
BORDER    = "#E8ECF0"
RED       = "#E53935"
GREEN     = "#2E7D32"
ORANGE    = "#F57C00"

DEFAULT_DURATION_OPTIONS = [4, 6, 10]
BASE_SAMPLE_TIMES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]


def sampling_times_for_duration(duration: int) -> list:
    duration = max(1, int(duration))
    if duration <= len(BASE_SAMPLE_TIMES):
        return BASE_SAMPLE_TIMES[:duration]
    times = list(BASE_SAMPLE_TIMES)
    last = times[-1]
    while len(times) < duration:
        last += 1.0
        times.append(last)
    return times

PATIENTS_FILE = Path(__file__).resolve().with_name("saved_patients.json")  # used only for migration

# ─────────────────────────────────────────
# Global stylesheet
# ─────────────────────────────────────────
STYLE = f"""
* {{
    font-family: "Helvetica Neue", "Segoe UI", Arial, sans-serif;
}}
QMainWindow, QWidget#root {{
    background-color: {BG};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: {BG};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #C5D0DE;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLineEdit {{
    background: white;
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: {TEXT_CLR};
}}
QLineEdit:focus {{
    border: 1.5px solid {BLUE};
}}
QLineEdit::placeholder {{
    color: #BDBDBD;
}}
QTableWidget {{
    background: white;
    border: 1.5px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    font-size: 14px;
}}
QTableWidget::item {{
    padding: 6px 12px;
    color: {TEXT_CLR};
}}
QTableWidget::item:selected {{
    background: #E8F0FE;
    color: {BLUE};
}}
QHeaderView::section {{
    background: #F8FAFC;
    color: {LABEL_CLR};
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 10px 14px;
    border: none;
    border-bottom: 1.5px solid {BORDER};
}}
QPushButton#mainTab {{
    background: transparent;
    color: #64748B;
    border: none;
    border-radius: 12px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 16px;
    padding-right: 16px;
    font-size: 14px;
    font-weight: bold;
}}
QPushButton#mainTab:hover {{
    background: #F3F7FB;
    color: #334155;
}}
QPushButton#mainTab:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #E8F1FF, stop:1 #F1F7FF);
    color: #123A73;
}}
QPushButton#mainTab:checked:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #E8F1FF, stop:1 #F1F7FF);
    color: #123A73;
}}
QPushButton#stepBtn {{
    background: transparent;
    color: #6B7D95;
    border: 1px solid transparent;
    border-radius: 14px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 16px;
    padding-right: 16px;
    font-size: 13px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#stepBtn:hover {{
    background: rgba(255,255,255,0.7);
    color: #16A34A;
    border: 1px solid rgba(22,163,74,0.2);
}}
QPushButton#stepBtn:checked {{
    background: white;
    color: #16A34A;
    border: 1px solid rgba(22,163,74,0.3);
}}
QPushButton#stepBtn:checked:hover {{
    background: white;
    color: #15803D;
}}
QPushButton#calcBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #EA580C, stop:1 #F97316);
    color: white;
    border: none;
    border-radius: 10px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 18px;
    padding-right: 18px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton#calcBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #C2410C, stop:1 #EA580C);
}}
QPushButton#calcBtn:disabled {{
    background: rgba(234, 88, 12, 0.30);
    color: rgba(255, 255, 255, 0.55);
}}
QPushButton#printBtn {{
    background: white;
    color: #EA580C;
    border: 1px solid #EA580C;
    border-radius: 8px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 20px;
    padding-right: 20px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton#printBtn:hover {{
    background: #FFF7ED;
}}
QPushButton#printBtn:disabled {{
    background: #FFF7ED;
    color: #FDBA74;
    border: 1px solid #FED7AA;
}}
QPushButton#resetBtn {{
    background: white;
    color: #92400E;
    border: 1px solid #FED7AA;
    border-radius: 8px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 20px;
    padding-right: 20px;
    font-size: 13px;
}}
QPushButton#resetBtn:hover {{
    background: #FFF7ED;
}}
QToolTip {{
    background: #102A43;
    color: white;
    border: 1px solid #1F4D7A;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────
def make_shadow(blur=20, offset_y=4, alpha=30):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    shadow.setColor(QColor(0, 0, 0, alpha))
    return shadow


def small_label(text, color=LABEL_CLR, size=11, bold=False, uppercase=True):
    lbl = QLabel(text.upper() if uppercase else text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px; font-weight: {'bold' if bold else 'normal'};"
        "letter-spacing: 0.8px;"
    )
    return lbl


def value_label(text, size=14, color=TEXT_CLR, bold=False):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px; font-weight: {'bold' if bold else 'normal'};"
    )
    return lbl
