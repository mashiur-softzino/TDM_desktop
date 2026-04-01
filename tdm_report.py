"""
TDM Report — Therapeutic Drug Monitoring
Modern single-page design with card layout and gradient chart
"""

import sys
import json
import tempfile
import webbrowser
import base64
from io import BytesIO
from datetime import datetime
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import matplotlib.pyplot as plt

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QMessageBox, QComboBox, QDialog, QDialogButtonBox, QDateEdit,
    QDateTimeEdit,
    QTimeEdit,
    QSizePolicy, QGridLayout, QGraphicsDropShadowEffect,
    QButtonGroup, QAbstractButton, QFileDialog, QSpacerItem,
    QListWidget, QListWidgetItem, QStackedWidget, QCalendarWidget,
    QToolButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QDate, QDateTime, QObject, QEvent
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush, QPen, QPalette
import qtawesome as qta
from calculations import calculate_auc_full, interpret_result, THERAPEUTIC_RANGES


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

TIME_SCHEMES = {
    4:  [0.5, 1.0, 1.5, 2.0],
    6:  [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    10: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0],
}

PATIENTS_FILE = Path(__file__).resolve().with_name("saved_patients.json")

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
QPushButton#calcBtn {{
    background: {BLUE};
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
    background: {BLUE_DARK};
}}
QPushButton#calcBtn:disabled {{
    background: #BFD3F3;
    color: #F7FAFF;
}}
QPushButton#printBtn {{
    background: white;
    color: {BLUE};
    border: 1px solid {BLUE};
    border-radius: 8px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 20px;
    padding-right: 20px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton#printBtn:hover {{
    background: #E8F0FE;
}}
QPushButton#printBtn:disabled {{
    background: #F5F8FC;
    color: #9FB4CF;
    border: 1px solid #C8D8EA;
}}
QPushButton#resetBtn {{
    background: white;
    color: {LABEL_CLR};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 20px;
    padding-right: 20px;
    font-size: 13px;
}}
QPushButton#resetBtn:hover {{
    background: #F5F5F5;
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


def small_label(text, color=LABEL_CLR, size=11, bold=False):
    lbl = QLabel(text.upper())
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


# ─────────────────────────────────────────
# Card widget
# ─────────────────────────────────────────
class Card(QFrame):
    def __init__(self, title='', icon='', icon_color=BLUE, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {CARD_BG};
                border-radius: 16px;
                border: none;
            }}
        """)
        self.setGraphicsEffect(make_shadow(20, 3, 25))

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(28, 24, 28, 24)
        self._layout.setSpacing(18)

        if title:
            header = QHBoxLayout()
            header.setSpacing(10)
            if icon:
                icon_lbl = QLabel()
                icon_lbl.setFixedSize(24, 24)
                icon_lbl.setPixmap(qta.icon(icon, color=icon_color).pixmap(20, 20))
                icon_lbl.setStyleSheet("background: transparent;")
                header.addWidget(icon_lbl)
            t = QLabel(title)
            t.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {TEXT_CLR};"
            )
            header.addWidget(t)
            header.addStretch()
            self._layout.addLayout(header)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background: {BORDER}; max-height: 1px;")
            self._layout.addWidget(sep)

    def body(self):
        return self._layout


# ─────────────────────────────────────────
# Toggle button group (4h / 6h / 10h)
# ─────────────────────────────────────────
# ─────────────────────────────────────────
# Modern Sample Table  (replaces QTableWidget)
# ─────────────────────────────────────────

# Rainbow palette — one colour per row position (up to 10)
ROW_COLORS = [
    "#F44336", "#FF7043", "#FF9800", "#FFC107",
    "#8BC34A", "#26A69A", "#29B6F6", "#5C6BC0",
    "#AB47BC", "#EC407A",
]


class SampleRow(QFrame):
    """Single editable row: [dot] [time pill] ──────── [conc input]"""
    changed = pyqtSignal()

    def __init__(self, time_val: float, idx: int, is_last: bool = False, parent=None):
        super().__init__(parent)
        self._idx = idx
        dot_color = ROW_COLORS[idx % len(ROW_COLORS)]

        self.setObjectName("sampleRow")
        self.setStyleSheet(f"""
            QFrame#sampleRow {{
                background: #FCFDFF;
                border: none;
                border-bottom: 1px solid {'transparent' if is_last else '#EEF3F8'};
            }}
            QFrame#sampleRow:hover {{
                background: #F7FBFF;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(14)

        # Coloured dot
        dot = QLabel("●")
        dot.setFixedWidth(18)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 13px; background: transparent;")
        row.addWidget(dot)

        # Time pill (editable)
        self.time_edit = QLineEdit(str(time_val))
        self.time_edit.setFixedWidth(80)
        self.time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #EEF4FB;
                border: none;
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: bold;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                background: #E3EDFF;
                color: {BLUE};
            }}
        """)
        row.addWidget(self.time_edit)

        unit = QLabel("h")
        unit.setStyleSheet(f"color: {LABEL_CLR}; font-size: 12px; background: transparent;")
        row.addWidget(unit)

        row.addStretch()

        # Concentration input
        self.conc_edit = QLineEdit()
        self.conc_edit.setPlaceholderText("Enter value…")
        self.conc_edit.setFixedWidth(200)
        self.conc_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conc_edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1px solid #DCE7F2;
                border-radius: 12px;
                padding: 9px 16px;
                font-size: 14px;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                background: white;
                border: 1px solid {BLUE};
                color: {TEXT_CLR};
            }}
        """)
        self.conc_edit.textChanged.connect(self.changed)
        self.time_edit.textChanged.connect(self.changed)
        row.addWidget(self.conc_edit)

    def get_values(self):
        try:
            t = float(self.time_edit.text().strip())
            c = float(self.conc_edit.text().strip())
            return t, c
        except ValueError:
            return None, None

    def has_concentration(self):
        return bool(self.conc_edit.text().strip())

    def set_values(self, time_val, conc_val=""):
        self.time_edit.setText(str(time_val))
        self.conc_edit.setText("" if conc_val in ("", None) else str(conc_val))


class ModernSampleTable(QFrame):
    """
    Modern table replacement for sample points.
    Rounded container, per-row colour dots, pill time labels, clean inputs.
    """
    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sampleTable")
        self.setStyleSheet(f"""
            QFrame#sampleTable {{
                background: #FBFDFF;
                border: 1px solid #E3EBF4;
                border-radius: 18px;
            }}
        """)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("sampleHdr")
        hdr.setStyleSheet(f"""
            QFrame#sampleHdr {{
                background: #F4F8FC;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
                border-bottom: 1px solid #E3EBF4;
            }}
        """)
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(18, 10, 18, 10)

        lbl_time = QLabel("TIME (H)")
        lbl_time.setStyleSheet(
            f"color: {LABEL_CLR}; font-size: 11px; font-weight: bold;"
            "letter-spacing: 1px; background: transparent;"
        )
        lbl_conc = QLabel("CONC. (μg/mL)")
        lbl_conc.setStyleSheet(
            f"color: {LABEL_CLR}; font-size: 11px; font-weight: bold;"
            "letter-spacing: 1px; background: transparent;"
        )
        hdr_row.addSpacing(32)
        hdr_row.addWidget(lbl_time)
        hdr_row.addStretch()
        hdr_row.addWidget(lbl_conc)
        hdr_row.addSpacing(4)
        self._outer.addWidget(hdr)

        # Rows container
        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._outer.addWidget(self._rows_widget)

        self._rows: list[SampleRow] = []

    def populate(self, times: list):
        # Clear existing rows
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

        n = len(times)
        for i, t in enumerate(times):
            row = SampleRow(t, i, is_last=(i == n - 1))
            row.changed.connect(self.data_changed)
            self._rows_layout.addWidget(row)
            self._rows.append(row)

    def get_data(self):
        """Returns (times, concs) for rows that have a concentration value."""
        times, concs = [], []
        for row in self._rows:
            t, c = row.get_values()
            if t is not None and c is not None:
                times.append(t)
                concs.append(c)
        return times, concs

    def get_data_strict(self):
        """Returns (times, concs) or (None, None) if any row is incomplete."""
        times, concs = [], []
        for row in self._rows:
            t, c = row.get_values()
            if t is None or c is None:
                return None, None
            times.append(t)
            concs.append(c)
        return times, concs

    def set_data(self, times: list, concs: list):
        self.populate(times)
        for row, t, c in zip(self._rows, times, concs):
            row.set_values(t, c)

    def get_rows_payload(self):
        payload = []
        for row in self._rows:
            payload.append({
                "time": row.time_edit.text().strip(),
                "concentration": row.conc_edit.text().strip(),
            })
        return payload

    def set_rows_payload(self, rows_payload: list):
        times = []
        concs = []
        for item in rows_payload:
            times.append(item.get("time", ""))
            concs.append(item.get("concentration", ""))
        self.populate(times)
        for row, t, c in zip(self._rows, times, concs):
            row.set_values(t, c)


class ToggleButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setMinimumWidth(72)
        self._update_style()
        self.toggled.connect(self._update_style)

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {BLUE};
                    color: white;
                    border: none;
                    border-radius: 14px;
                    font-size: 14px;
                    font-weight: bold;
                    padding-left: 18px;
                    padding-right: 18px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: #FBFDFF;
                    color: {TEXT_CLR};
                    border: 1px solid #DCE6F0;
                    border-radius: 14px;
                    font-size: 14px;
                    padding-left: 18px;
                    padding-right: 18px;
                }}
                QPushButton:hover {{
                    background: #F4F8FC;
                }}
            """)


# ─────────────────────────────────────────
# Gradient matplotlib canvas
# ─────────────────────────────────────────
class GradientCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 4), dpi=110, facecolor='white')
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(360)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.88, bottom=0.20)
        self._draw_empty()

    def _draw_empty(self):
        self.ax.clear()
        self.ax.set_facecolor('white')
        self.ax.set_xlabel('Time (h)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_ylabel('Conc. (μg/mL)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_title('Concentration–Time Curve', fontsize=13,
                           fontweight='bold', color='#1A1A2E', pad=14)
        self.ax.grid(True, linestyle='--', color='#EEEEEE', alpha=0.9)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color(BORDER)
        self.ax.spines['bottom'].set_color(BORDER)
        self.ax.tick_params(colors='#9E9E9E', labelsize=10)
        self.ax.text(0.5, 0.5, 'Enter concentrations to see the graph',
                     transform=self.ax.transAxes, ha='center', va='center',
                     color='#BDBDBD', fontsize=12)
        self.draw()

    def plot(self, times, concs, drug='MPA'):
        self.ax.clear()
        times = np.array(times, dtype=float)
        concs = np.array(concs, dtype=float)

        self.ax.set_facecolor('white')
        self.ax.grid(True, linestyle='--', color='#EEEEEE', alpha=0.9, zorder=0)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color(BORDER)
        self.ax.spines['bottom'].set_color(BORDER)
        self.ax.tick_params(colors='#9E9E9E', labelsize=10)

        # Smooth curve via cubic spline
        if len(times) >= 3:
            cs = CubicSpline(times, concs)
            t_fine = np.linspace(times[0], times[-1], 500)
            c_fine = np.clip(cs(t_fine), 0, None)
        else:
            t_fine = times
            c_fine = concs

        # ── Rainbow gradient line ──────────────────────
        points = np.array([t_fine, c_fine]).T.reshape(-1, 1, 2)
        segs = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(t_fine[0], t_fine[-1])
        lc = LineCollection(segs, cmap='rainbow', norm=norm, linewidth=2.8, zorder=3)
        lc.set_array(t_fine)
        self.ax.add_collection(lc)

        # ── Gradient fill (batched for performance) ──
        n_fill = 80
        t_segs = np.linspace(t_fine[0], t_fine[-1], n_fill + 1)
        for i in range(n_fill):
            ts = t_segs[i:i + 2]
            cs_seg = np.clip(cs(ts), 0, None) if len(times) >= 3 else np.interp(ts, times, concs)
            col = plt.cm.rainbow(norm(t_segs[i]))
            self.ax.fill_between(ts, 0, cs_seg, color=col, alpha=0.18, zorder=1)

        # ── Data points with matching rainbow colours ──
        dot_colors = plt.cm.rainbow(np.linspace(0, 1, len(times)))
        for i, (t, c, col) in enumerate(zip(times, concs, dot_colors)):
            self.ax.scatter(t, c, color=col, s=90, zorder=5,
                            edgecolors='white', linewidth=2)

        # ── Trough label ──
        self.ax.annotate(
            'Trough', (times[0], concs[0]),
            xytext=(8, 12), textcoords='offset points',
            color=RED, fontsize=9, fontweight='bold',
            arrowprops=dict(arrowstyle='-', color=RED, lw=1)
        )

        conc_unit = 'μg/mL' if drug == 'MPA' else 'ng/mL'
        self.ax.set_xlabel('Time (h)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_ylabel(f'Conc. ({conc_unit})', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_title('Concentration–Time Curve', fontsize=13,
                           fontweight='bold', color='#1A1A2E', pad=14)
        self.ax.set_xlim(left=max(-0.15, times[0] - 0.2))
        self.ax.set_ylim(bottom=0)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.88, bottom=0.20)
        self.draw()


# ─────────────────────────────────────────
# Medication tag + modal
# ─────────────────────────────────────────

DEFAULT_MEDICATIONS = [
    "Tacrolimus (TAC)", "Cyclosporine (CsA)", "Mycophenolate (MPA)",
    "Prednisolone", "Methylprednisolone", "Amlodipine", "Metoprolol",
    "Losartan", "Atorvastatin", "Rosuvastatin", "Furosemide",
    "Spironolactone", "Omeprazole", "Pantoprazole", "Insulin",
    "Glimepiride", "Metformin", "Febuxostat", "Allopurinol",
    "Cotrimoxazole", "Valganciclovir", "Fluconazole", "Omega-3",
    "Calcium + Vitamin D", "Sirolimus", "Everolimus", "Azathioprine",
    "Linagliptin", "Losartan", "Ostoref-D", "Shelcal",
]


class MedTag(QFrame):
    """Single selected medication pill with × remove button."""
    removed = pyqtSignal(str)

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setObjectName("medTag")
        self.setStyleSheet(f"""
            QFrame#medTag {{
                background: #EEF2FF;
                border-radius: 20px;
                border: none;
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 5, 8, 5)
        row.setSpacing(6)

        lbl = QLabel(name)
        lbl.setStyleSheet(f"color: {BLUE}; font-size: 12px; font-weight: 600; background: transparent;")
        row.addWidget(lbl)

        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #C7D2FE;
                color: {BLUE};
                border: none;
                border-radius: 9px;
                font-size: 13px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{ background: #A5B4FC; }}
        """)
        btn.clicked.connect(lambda: self.removed.emit(self.name))
        row.addWidget(btn)


class MedAddModal(QDialog):
    """Modal to add a custom medication not in the default list."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Medication")
        self.setFixedWidth(360)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{ background: white; border-radius: 12px; }}
            QLabel {{ color: {TEXT_CLR}; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        title = QLabel("Add Custom Medication")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_CLR};")
        lay.addWidget(title)

        sub = QLabel("Enter the medication name to add it to the list.")
        sub.setStyleSheet(f"font-size: 12px; color: {LABEL_CLR};")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("e.g. Voriconazole")
        self.edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1.5px solid {BORDER};
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
            }}
            QLineEdit:focus {{ border: 1.5px solid {BLUE}; }}
        """)
        lay.addWidget(self.edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Add")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(f"""
            QPushButton {{
                background: {BLUE}; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {BLUE_DARK}; }}
        """)
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(f"""
            QPushButton {{
                background: white; color: {LABEL_CLR};
                border: 1.5px solid {BORDER}; border-radius: 8px; padding: 8px 20px;
            }}
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_text(self):
        return self.edit.text().strip()


class MedicationSelector(QFrame):
    """
    Search-as-you-type medication field with persistent inline dropdown.

    Layout (vertical, all inside one QFrame):
      ┌─[🔍 search…]──────────────────[+]─┐
      │ ┌─ dropdown list (inline) ────────┐│  ← shown/hidden, never closes on focus-out
      │ │  option 1                       ││
      │ │  option 2  …                    ││
      │ └─────────────────────────────────┘│
      │  [tag×]  [tag×]  [tag×]  …        │
      └────────────────────────────────────┘
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._all_meds = list(DEFAULT_MEDICATIONS)
        self._selected: list[str] = []

        # Install app-level mouse press filter to detect outside clicks
        QApplication.instance().installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Search row ────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        search_wrap = QFrame()
        search_wrap.setObjectName("searchWrap")
        search_wrap.setStyleSheet(f"""
            QFrame#searchWrap {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 10px;
            }}
            QFrame#searchWrap:focus-within {{
                border: 1.5px solid {BLUE};
            }}
        """)
        sw_lay = QHBoxLayout(search_wrap)
        sw_lay.setContentsMargins(12, 0, 12, 0)
        sw_lay.setSpacing(8)

        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi6.magnify", color=LABEL_CLR).pixmap(16, 16))
        search_icon.setFixedSize(16, 16)
        search_icon.setStyleSheet("background: transparent;")
        sw_lay.addWidget(search_icon)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search medication…")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background: transparent;
                font-size: 13px;
                color: {TEXT_CLR};
                padding: 10px 0;
            }}
        """)
        self._search.textChanged.connect(self._on_search)
        self._search.mousePressEvent = self._search_clicked
        sw_lay.addWidget(self._search, 1)

        ctrl.addWidget(search_wrap, 1)

        add_btn = QPushButton()
        add_btn.setFixedSize(42, 42)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add custom medication")
        add_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        add_btn.setIconSize(add_btn.size() * 0.52)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BLUE}; border: none; border-radius: 10px;
            }}
            QPushButton:hover {{ background: {BLUE_DARK}; }}
        """)
        add_btn.clicked.connect(self._open_modal)
        ctrl.addWidget(add_btn)

        outer.addLayout(ctrl)

        # ── Inline dropdown (always in layout, shown/hidden) ──
        self._drop_frame = QFrame()
        self._drop_frame.setObjectName("inlineDrop")
        self._drop_frame.setStyleSheet(f"""
            QFrame#inlineDrop {{
                background: white;
                border: 1.5px solid {BORDER};
                border-top: none;
                border-radius: 0 0 12px 12px;
            }}
        """)
        self._drop_frame.setGraphicsEffect(make_shadow(16, 6, 30))

        drop_lay = QVBoxLayout(self._drop_frame)
        drop_lay.setContentsMargins(6, 4, 6, 6)
        drop_lay.setSpacing(0)

        self._list = QListWidget()
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # key: never steals focus
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                font-size: 13px;
                color: {TEXT_CLR};
                outline: none;
            }}
            QListWidget::item {{
                padding: 9px 14px;
                border-radius: 8px;
            }}
            QListWidget::item:hover {{
                background: #EEF2FF;
                color: {BLUE};
            }}
        """)
        self._list.itemClicked.connect(self._on_item_clicked)
        drop_lay.addWidget(self._list)

        self._drop_frame.setVisible(False)
        outer.addWidget(self._drop_frame)

        outer.addSpacing(8)

        # ── Tags scroll ───────────────────────────
        self._tags_widget = QWidget()
        self._tags_widget.setStyleSheet("background: transparent;")
        self._tags_layout = QHBoxLayout(self._tags_widget)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(6)
        self._tags_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._tags_scroll = QScrollArea()
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tags_scroll.setFixedHeight(44)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setWidget(self._tags_widget)
        self._tags_scroll.setStyleSheet("background: transparent;")
        outer.addWidget(self._tags_scroll)

    # ── Show all options when search field is clicked empty ──
    def _search_clicked(self, event):
        if not self._search.text().strip():
            self._show_options(self._all_meds)
        type(self._search).mousePressEvent(self._search, event)

    # ── Filter as user types ──────────────────────
    def _on_search(self, text: str):
        q = text.strip().lower()
        if not q:
            self._show_options(self._all_meds)
            return
        matches = [m for m in self._all_meds if q in m.lower()]
        if not any(m.lower() == q for m in self._all_meds):
            matches.append(f'Add "{text.strip()}"')
        self._show_options(matches)

    def _show_options(self, items: list[str]):
        self._list.clear()
        for name in items:
            item = QListWidgetItem(name)
            if name.startswith('Add "'):
                item.setForeground(QColor(BLUE))
            self._list.addItem(item)
        rows = min(len(items), 7)
        self._list.setFixedHeight(max(rows, 1) * 42)
        self._drop_frame.setVisible(True)

    def eventFilter(self, _obj: QObject, event: QEvent) -> bool:
        """Close dropdown when user clicks anywhere outside this widget."""
        if (event.type() == QEvent.Type.MouseButtonPress
                and self._drop_frame.isVisible()):
            # Check if click was inside self (the whole MedicationSelector frame)
            click_pos = event.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(click_pos)
            if not self.rect().contains(local_pos):
                self._hide_dropdown()
        return False  # never consume the event

    def _hide_dropdown(self):
        self._drop_frame.setVisible(False)
        self._list.clear()

    # ── Item selected from list ───────────────────
    def _on_item_clicked(self, item: QListWidgetItem):
        name = item.text()
        self._hide_dropdown()
        self._search.clear()
        if name.startswith('Add "') and name.endswith('"'):
            name = name[5:-1].strip()
            if name and name not in self._all_meds:
                self._all_meds.append(name)
        self._add_tag(name)

    # ── + modal ───────────────────────────────────
    def _open_modal(self):
        self._hide_dropdown()
        dlg = MedAddModal(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.get_text()
            if name and name not in self._all_meds:
                self._all_meds.append(name)
            if name:
                self._add_tag(name)

    # ── Tag management ────────────────────────────
    def _add_tag(self, name: str):
        if not name or name in self._selected:
            return
        self._selected.append(name)
        tag = MedTag(name, self._tags_widget)
        tag.removed.connect(self._remove_tag)
        self._tags_layout.addWidget(tag)

    def _remove_tag(self, name: str):
        if name in self._selected:
            self._selected.remove(name)
        for i in range(self._tags_layout.count()):
            w = self._tags_layout.itemAt(i)
            if w and isinstance(w.widget(), MedTag) and w.widget().name == name:
                w.widget().deleteLater()
                break

    def get_medications(self) -> list[str]:
        return list(self._selected)

    def get_text(self) -> str:
        return ", ".join(self._selected)

    def clear_selection(self):
        self._selected.clear()
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._search.clear()
        self._hide_dropdown()


# ─────────────────────────────────────────
# Result stat widget
# ─────────────────────────────────────────
class IconCircle(QWidget):
    """Rounded square with a qtawesome vector icon inside."""
    def __init__(self, icon_name: str, icon_color: str, bg_color: str, size=44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._bg = QColor(bg_color)
        self._icon = qta.icon(icon_name, color=icon_color)
        self._icon_size = size - 18

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setBrush(QBrush(self._bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 13, 13)
        icon_rect = QRect(
            (self.width() - self._icon_size) // 2,
            (self.height() - self._icon_size) // 2,
            self._icon_size,
            self._icon_size,
        )
        self._icon.paint(p, icon_rect, Qt.AlignmentFlag.AlignCenter)


class StatBox(QFrame):
    """
    Modern dashboard stat card — vector icon + bold value + label.
    Layout (vertical):
        [icon circle]   ···
        value  (bold)
        label  (gray)
        unit   (lighter)
    """
    def __init__(self, label, value='—', unit='',
                 icon_name='mdi6.circle-outline',
                 icon_color='#7C3AED', icon_bg='#EDE9FE',
                 value_color=TEXT_CLR, parent=None):
        super().__init__(parent)
        self.setObjectName("statBox")
        self._default_value_color = value_color
        self.setMinimumWidth(148)
        self.setStyleSheet("""
            QFrame#statBox {
                background: white;
                border-radius: 16px;
                border: none;
            }
        """)
        self.setGraphicsEffect(make_shadow(18, 4, 20))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(0)

        # ── Top row: icon circle + dots menu ─────
        top = QHBoxLayout()
        top.setSpacing(0)
        top.addWidget(IconCircle(icon_name, icon_color, icon_bg))
        top.addStretch()
        dots = QLabel("•••")
        dots.setStyleSheet("color: #CBD5E1; font-size: 13px; letter-spacing: 3px;")
        top.addWidget(dots)
        outer.addLayout(top)

        outer.addSpacing(14)

        # ── Bold value ────────────────────────────
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {value_color};"
            "background: transparent; letter-spacing: -0.5px;"
        )
        outer.addWidget(self._val)

        outer.addSpacing(4)

        # ── Label ─────────────────────────────────
        self._lbl = QLabel(label)
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(
            f"font-size: 12px; color: {LABEL_CLR}; background: transparent;"
        )
        outer.addWidget(self._lbl)

        # ── Unit ──────────────────────────────────
        if unit:
            self._unit = QLabel(unit)
            self._unit.setStyleSheet(
                "font-size: 10px; color: #B0BEC5; background: transparent;"
            )
            outer.addWidget(self._unit)
        else:
            self._unit = None

    def set_value(self, val, color=None):
        self._val.setText(val)
        c = color or self._default_value_color
        self._val.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {c};"
            "background: transparent; letter-spacing: -0.5px;"
        )

    def set_label(self, text):
        self._lbl.setText(text)

    def set_unit(self, text):
        if self._unit is None:
            self._unit = QLabel()
            self._unit.setStyleSheet(
                "font-size: 10px; color: #B0BEC5; background: transparent;"
            )
            self.layout().addWidget(self._unit)
        self._unit.setText(text)


class ResultsDialog(QDialog):
    def __init__(self, parent=None, print_handler=None):
        super().__init__(parent)
        self.setWindowTitle("Generated Result")
        self.resize(1100, 820)
        self.setMinimumSize(980, 700)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")
        self._print_handler = print_handler

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(18)

        self.results_card = Card("Pharmacokinetic Results", "mdi6.chart-box-outline", icon_color=BLUE)
        grid = QGridLayout()
        grid.setSpacing(14)

        self.stat_trough = StatBox(
            "Trough Concentration", unit="μg/mL",
            icon_name="mdi6.water-outline", icon_color="#7C3AED", icon_bg="#EDE9FE",
        )
        self.stat_clast = StatBox(
            "Last Sample Concentration", unit="μg/mL",
            icon_name="mdi6.flask-outline", icon_color="#0284C7", icon_bg="#E0F2FE",
        )
        self.stat_auc = StatBox(
            "Observed AUC", unit="mg·h/L",
            icon_name="mdi6.chart-bell-curve", icon_color="#D97706", icon_bg="#FEF3C7",
        )
        self.stat_auc12 = StatBox(
            "MPA AUC extrapolated to 12 hr", unit="mg·h/L",
            icon_name="mdi6.chart-line", icon_color="#1A73E8", icon_bg="#DBEAFE", value_color=BLUE,
        )
        self.stat_interp = StatBox(
            "Interpretation", unit="Therapeutic: 30–60 mg·h/L",
            icon_name="mdi6.stethoscope", icon_color="#059669", icon_bg="#D1FAE5",
        )
        self.stat_thalf = StatBox(
            "Terminal  t½", unit="hours",
            icon_name="mdi6.timer-sand", icon_color="#DB2777", icon_bg="#FCE7F3",
        )
        boxes = [
            self.stat_trough, self.stat_clast, self.stat_auc,
            self.stat_auc12, self.stat_interp, self.stat_thalf,
        ]
        for i, box in enumerate(boxes):
            grid.addWidget(box, i // 3, i % 3)
        self.results_card.body().addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.print_btn = QPushButton("Print / Export PDF")
        self.print_btn.setObjectName("printBtn")
        self.print_btn.clicked.connect(self._on_print)
        btn_row.addWidget(self.print_btn)
        self.results_card.body().addLayout(btn_row)
        content_lay.addWidget(self.results_card)

        self.graph_card = Card("Concentration–Time Curve", "mdi6.chart-line", icon_color=BLUE)
        self.canvas = GradientCanvas()
        self.graph_card.body().addWidget(self.canvas)
        content_lay.addWidget(self.graph_card)

        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("printBtn")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        lay.addLayout(close_row)

    def _on_print(self):
        if self._print_handler is not None:
            self._print_handler()

    def apply_results(self, pk, interp):
        def fmt_hour(v):
            return f"{int(v)}" if float(v).is_integer() else f"{v:.1f}"

        def fmt(v, d=3):
            return f"{v:.{d}f}" if v is not None else "N/A"

        last_hr = fmt_hour(pk['t_last'])
        self.stat_trough.set_label("Trough Concentration")
        self.stat_trough.set_unit("μg/mL")
        self.stat_trough.set_value(fmt(pk['c_trough'], 2))
        self.stat_clast.set_label(f"{last_hr} hr Concentration")
        self.stat_clast.set_unit("μg/mL")
        self.stat_clast.set_value(fmt(pk['c_last'], 2))
        self.stat_auc.set_label(f"AUC (0 → {last_hr} hr)")
        self.stat_auc.set_unit("Observed exposure  •  mg·h/L")
        self.stat_auc.set_value(fmt(pk['auc_0_last'], 3))
        self.stat_auc12.set_label(f"{last_hr} hour extrapolated to 12 hr MPA AUC")
        self.stat_auc12.set_unit("mg·h/L")
        self.stat_auc12.set_value(fmt(pk['auc_0_12'], 3))
        self.stat_thalf.set_label("Terminal  t½")
        self.stat_thalf.set_unit("hours")
        self.stat_thalf.set_value(fmt(pk['t_half'], 2) if pk['t_half'] else 'N/A')
        _, rng = interpret_result('MPA', pk['auc_0_12'])
        interp_color = {'Low': RED, 'High': RED, 'Therapeutic': GREEN}.get(interp, TEXT_CLR)
        self.stat_interp.set_label("Interpretation")
        self.stat_interp.set_unit(f"Therapeutic range: {rng[0]}–{rng[1]} mg·h/L")
        self.stat_interp.set_value(interp, color=interp_color)

    def plot_data(self, times, concs, drug='MPA'):
        self.canvas.plot(times, concs, drug=drug)


class SmartDateEdit(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._date = QDate.currentDate()
        self.setStyleSheet("background: transparent;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._shell = QFrame()
        self._shell.setObjectName("smartDateShell")
        self._shell.setStyleSheet(f"""
            QFrame#smartDateShell {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 16px;
            }}
            QFrame#smartDateShell:hover {{
                border: 1.5px solid #D8E6F5;
            }}
        """)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(16, 0, 0, 0)
        shell_lay.setSpacing(0)

        self._text = QLineEdit()
        self._text.setReadOnly(True)
        self._text.setFrame(False)
        self._text.setText(self._date.toString("dd  MMM  yyyy"))
        self._text.setStyleSheet(
            f"background: transparent; color: {TEXT_CLR}; border: none; "
            "font-size: 13px; font-weight: 600; padding: 12px 0;"
        )
        shell_lay.addWidget(self._text, 1)

        self._btn = QPushButton()
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedSize(48, 46)
        self._btn.setIcon(qta.icon("mdi6.calendar-month-outline", color=BLUE))
        self._btn.setIconSize(self._btn.size() * 0.42)
        self._btn.setStyleSheet(
            "QPushButton { background: #F4F8FD; border: none; border-left: 1px solid #E8EEF5; "
            "border-top-right-radius: 16px; border-bottom-right-radius: 16px; }"
            "QPushButton:hover { background: #ECF4FF; }"
        )
        self._btn.clicked.connect(self._show_popup)
        shell_lay.addWidget(self._btn)
        outer.addWidget(self._shell)

        self._popup = None  # created lazily on first open
        self._calendar = None

    def _build_popup(self):
        self._popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        pop_lay = QVBoxLayout(self._popup)
        pop_lay.setContentsMargins(0, 8, 0, 0)
        pop_lay.setSpacing(0)

        card = QFrame()
        card.setMinimumSize(320, 332)
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #DDE7F0;
                border-radius: 22px;
            }}
            QCalendarWidget {{
                background: transparent;
                border: none;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: transparent;
                border: none;
                border-bottom: 1px solid #EDF2F7;
                min-height: 48px;
            }}
            QCalendarWidget QToolButton {{
                color: {TEXT_CLR};
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
                subcontrol-position: center;
            }}
            QCalendarWidget QToolButton:hover {{
                background: #EEF5FF;
                color: {BLUE};
            }}
            QCalendarWidget QMenu {{
                background: white;
                border: 1px solid #DCE6F0;
                padding: 6px;
            }}
            QCalendarWidget QSpinBox {{
                background: transparent;
                border: none;
                color: {TEXT_CLR};
                font-size: 14px;
                font-weight: 700;
            }}
            QCalendarWidget QHeaderView::section {{
                background: transparent;
                color: #8A97A8;
                border: none;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 0 10px 0;
            }}
            QCalendarWidget QTableView {{
                background: white;
                border: none;
                outline: 0;
                selection-background-color: {BLUE};
                selection-color: white;
                alternate-background-color: white;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: {TEXT_CLR};
                background: white;
                font-size: 13px;
                selection-background-color: {BLUE};
                selection-color: white;
                outline: 0;
                show-decoration-selected: 1;
            }}
            QCalendarWidget QAbstractItemView::item:hover {{
                background: #EAF3FF;
                color: {BLUE};
                border-radius: 8px;
            }}
        """)
        card.setGraphicsEffect(make_shadow(22, 8, 35))
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 8)
        card_lay.setSpacing(4)

        self._calendar = MonthOnlyCalendar()
        self._calendar.setMinimumSize(300, 244)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.setGridVisible(False)
        self._calendar.setSelectedDate(self._date)
        self._calendar.setDateEditEnabled(False)
        self._calendar.setNavigationBarVisible(True)
        self._calendar.clicked.connect(self._on_date_selected)
        cal_palette = self._calendar.palette()
        cal_palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        cal_palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        cal_palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_CLR))
        self._calendar.setPalette(cal_palette)
        card_lay.addWidget(self._calendar)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        today_btn = QPushButton("Today")
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.setFixedHeight(32)
        today_btn.setStyleSheet(
            f"QPushButton {{ background: #EEF5FF; color: {BLUE}; border: none; border-radius: 10px; "
            f"padding: 6px 12px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #E2EEFF; }}"
        )
        today_btn.clicked.connect(lambda: self._on_date_selected(QDate.currentDate()))
        footer.addWidget(today_btn)
        footer.addStretch()
        card_lay.addLayout(footer)

        pop_lay.addWidget(card)
        self._style_calendar_nav()
        self._fix_calendar_viewport()

    def _style_calendar_nav(self):
        calendar = self._calendar
        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        month_btn = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
        year_btn = calendar.findChild(QToolButton, "qt_calendar_yearbutton")

        if prev_btn is not None:
            prev_btn.setText("")
            prev_btn.setIcon(qta.icon("mdi6.chevron-left", color=BLUE))
            prev_btn.setIconSize(prev_btn.sizeHint() * 0.55)
        if next_btn is not None:
            next_btn.setText("")
            next_btn.setIcon(qta.icon("mdi6.chevron-right", color=BLUE))
            next_btn.setIconSize(next_btn.sizeHint() * 0.55)
        for btn in [month_btn, year_btn]:
            if btn is not None:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _fix_calendar_viewport(self):
        view = self._calendar.findChild(QWidget, "qt_calendar_calendarview")
        if view is None:
            return
        view.setAutoFillBackground(True)
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_CLR))
        view.setPalette(palette)
        view.setStyleSheet(
            f"background: white; color: {TEXT_CLR}; border: none; "
            f"selection-background-color: {BLUE}; selection-color: white;"
        )

    def _show_popup(self):
        if self._popup is None:
            self._build_popup()
        self._calendar.setSelectedDate(self._date)
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(pos.x(), pos.y() + 6)
        self._popup.adjustSize()
        self._popup.show()

    def _on_date_selected(self, date):
        self.setDate(date)
        self._popup.hide()

    def date(self):
        return self._date

    def setDate(self, date):
        self._date = date
        self._text.setText(self._date.toString("dd  MMM  yyyy"))


class SmartDateTimeEdit(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dt = QDateTime.currentDateTime()
        self.setStyleSheet("background: transparent;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._shell = QFrame()
        self._shell.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 16px;
            }}
            QFrame:hover {{
                border: 1.5px solid #D8E6F5;
            }}
        """)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(16, 0, 0, 0)
        shell_lay.setSpacing(8)

        self._text = QLabel()
        self._text.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700; background: transparent;")
        shell_lay.addWidget(self._text)

        shell_lay.addStretch()

        self._btn = QPushButton()
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedSize(48, 46)
        self._btn.setIcon(qta.icon("mdi6.clock-edit-outline", color=BLUE))
        self._btn.setIconSize(self._btn.size() * 0.42)
        self._btn.setStyleSheet(
            "QPushButton { background: #F4F8FD; border: none; border-left: 1px solid #E8EEF5; "
            "border-top-right-radius: 16px; border-bottom-right-radius: 16px; }"
            "QPushButton:hover { background: #ECF4FF; }"
        )
        self._btn.clicked.connect(self._show_popup)
        shell_lay.addWidget(self._btn)
        outer.addWidget(self._shell)

        self._popup = None  # created lazily on first open
        self._calendar = None
        self._time_edit = None
        self._refresh_text()

    def _build_popup(self):
        self._popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        pop_lay = QVBoxLayout(self._popup)
        pop_lay.setContentsMargins(0, 8, 0, 0)
        pop_lay.setSpacing(0)

        card = QFrame()
        card.setMinimumSize(320, 400)
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #DDE7F0;
                border-radius: 22px;
            }}
            QCalendarWidget {{
                background: transparent;
                border: none;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: transparent;
                border: none;
                border-bottom: 1px solid #EDF2F7;
                min-height: 48px;
            }}
            QCalendarWidget QToolButton {{
                color: {TEXT_CLR};
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QCalendarWidget QToolButton:hover {{
                background: #EEF5FF;
                color: {BLUE};
            }}
            QCalendarWidget QHeaderView::section {{
                background: transparent;
                color: #8A97A8;
                border: none;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 0 10px 0;
            }}
            QCalendarWidget QTableView {{
                background: white;
                border: none;
                outline: 0;
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: {TEXT_CLR};
                background: white;
                font-size: 13px;
                selection-background-color: {BLUE};
                selection-color: white;
                outline: 0;
            }}
        """)
        card.setGraphicsEffect(make_shadow(22, 8, 35))
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        card_lay.setSpacing(8)

        self._calendar = MonthOnlyCalendar()
        self._calendar.setMinimumSize(300, 244)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.setGridVisible(False)
        self._calendar.setSelectedDate(self._dt.date())
        self._calendar.clicked.connect(self._on_date_clicked)
        card_lay.addWidget(self._calendar)

        time_row = QFrame()
        time_row.setStyleSheet("background: #F7FAFE; border-radius: 14px;")
        time_lay = QHBoxLayout(time_row)
        time_lay.setContentsMargins(12, 10, 12, 10)
        time_lay.setSpacing(10)

        clock = QLabel()
        clock.setPixmap(qta.icon("mdi6.clock-time-four-outline", color=BLUE).pixmap(18, 18))
        time_lay.addWidget(clock)

        time_text = QLabel("Dose Time")
        time_text.setStyleSheet(f"color: {TEXT_CLR}; font-size: 12px; font-weight: 700;")
        time_lay.addWidget(time_text)
        time_lay.addStretch()

        self._time_edit = QTimeEdit(self._dt.time())
        self._time_edit.setDisplayFormat("hh:mm AP")
        self._time_edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self._time_edit.setStyleSheet(
            f"background: white; color: {TEXT_CLR}; border: 1px solid #DCE6F0; border-radius: 10px; "
            "padding: 6px 10px; font-size: 12px; font-weight: 700;"
        )
        self._time_edit.timeChanged.connect(self._on_time_changed)
        time_lay.addWidget(self._time_edit)
        card_lay.addWidget(time_row)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        now_btn = QPushButton("Now")
        now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        now_btn.setFixedHeight(32)
        now_btn.setStyleSheet(
            f"QPushButton {{ background: #EEF5FF; color: {BLUE}; border: none; border-radius: 10px; "
            f"padding: 6px 12px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #E2EEFF; }}"
        )
        now_btn.clicked.connect(self._set_now)
        footer.addWidget(now_btn)
        footer.addStretch()
        card_lay.addLayout(footer)

        pop_lay.addWidget(card)
        self._style_calendar_nav()

    def _style_calendar_nav(self):
        prev_btn = self._calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = self._calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        for btn, icon_name in [(prev_btn, "mdi6.chevron-left"), (next_btn, "mdi6.chevron-right")]:
            if btn is not None:
                btn.setText("")
                btn.setIcon(qta.icon(icon_name, color=BLUE))
                btn.setIconSize(btn.sizeHint() * 0.55)

    def _refresh_text(self):
        self._text.setText(self._dt.toString("dd.MM.yy   hh:mm AP"))

    def _show_popup(self):
        if self._popup is None or self._calendar is None or self._time_edit is None:
            self._build_popup()
        self._calendar.setSelectedDate(self._dt.date())
        self._time_edit.setTime(self._dt.time())
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(pos.x(), pos.y() + 6)
        self._popup.adjustSize()
        self._popup.show()

    def _on_date_clicked(self, date):
        self._dt.setDate(date)
        self._refresh_text()

    def _on_time_changed(self, time):
        self._dt.setTime(time)
        self._refresh_text()

    def _set_now(self):
        self.setDateTime(QDateTime.currentDateTime())

    def dateTime(self):
        return self._dt

    def setDateTime(self, dt):
        self._dt = dt
        if self._calendar is not None:
            self._calendar.setSelectedDate(dt.date())
        if self._time_edit is not None:
            self._time_edit.setTime(dt.time())
        self._refresh_text()


class MonthOnlyCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        year, month = self.yearShown(), self.monthShown()
        self._page_year = year
        self._page_month = month
        self.currentPageChanged.connect(self._on_page_changed)

    def _on_page_changed(self, year, month):
        self._page_year = year
        self._page_month = month
        view = self.findChild(QWidget, "qt_calendar_calendarview")
        if view is not None:
            view.update()
        self.update()

    def paintCell(self, painter, rect, date):
        if date.year() != self._page_year or date.month() != self._page_month:
            painter.save()
            painter.fillRect(rect, QColor("white"))
            painter.restore()
            return
        super().paintCell(painter, rect, date)


class PatientReportDialog(QDialog):
    def __init__(self, snapshot: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Saved Patient Report")
        self.resize(820, 760)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel(snapshot.get('patient', {}).get('name', 'Saved Report'))
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_CLR};")
        lay.addWidget(title)

        sub = QLabel(
            f"{snapshot.get('patient', {}).get('drug', 'N/A')}  •  "
            f"Saved on {snapshot.get('saved_at', 'N/A')}"
        )
        sub.setStyleSheet(f"font-size: 12px; color: {LABEL_CLR};")
        lay.addWidget(sub)

        from report_print import build_report_widget
        report = build_report_widget(
            patient=snapshot.get('patient', {}),
            pk=snapshot.get('pk', {}),
            interp=snapshot.get('interp', 'N/A'),
            times=snapshot.get('times', []),
            concs=snapshot.get('concs', []),
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(report)
        lay.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("printBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)


class PatientRow(QFrame):
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, snapshot: dict, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.setObjectName("patientRow")
        self.setStyleSheet(f"""
            QFrame#patientRow {{
                background: #FCFDFE;
                border: 1px solid #E7EEF6;
                border-radius: 18px;
            }}
            QFrame#patientRow:hover {{
                background: #F8FBFF;
                border: 1px solid #D7E5F5;
            }}
            QLabel#cellValue {{
                font-size: 13px;
                color: {TEXT_CLR};
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#drugBadge {{
                background: #EAF2FF;
                color: {BLUE};
                border-radius: 10px;
                border: none;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QLabel#dateText {{
                font-size: 12px;
                color: #718096;
                background: transparent;
                border: none;
            }}
            QWidget#actionsWrap {{
                background: transparent;
                border: none;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(22, 18, 22, 18)
        row.setSpacing(16)

        def text_cell(text, stretch=2, object_name="cellValue"):
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setStyleSheet("background: transparent; border: none;")
            row.addWidget(lbl, stretch)

        text_cell(snapshot.get('patient', {}).get('name', 'N/A'))
        text_cell(snapshot.get('patient', {}).get('hosp_id', 'N/A'))

        drug = QLabel(snapshot.get('patient', {}).get('drug', 'N/A'))
        drug.setObjectName("drugBadge")
        drug.setStyleSheet("border: none;")
        row.addWidget(drug, 2)

        text_cell(snapshot.get('patient', {}).get('dose', 'N/A'))
        text_cell(snapshot.get('saved_at', 'N/A'), object_name="dateText")

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        view_btn = QPushButton()
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setIcon(qta.icon("mdi6.pencil-outline", color=BLUE))
        view_btn.setToolTip("Open sample")
        view_btn.setFixedSize(34, 34)
        view_btn.setStyleSheet(
            "QPushButton { background: #EEF5FF; border: none; border-radius: 17px; }"
            "QPushButton:hover { background: #DCEBFF; }"
        )
        view_btn.clicked.connect(lambda: self.edit_requested.emit(snapshot['id']))
        actions.addWidget(view_btn)

        delete_btn = QPushButton()
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setIcon(qta.icon("mdi6.trash-can-outline", color=RED))
        delete_btn.setToolTip("Delete patient")
        delete_btn.setFixedSize(34, 34)
        delete_btn.setStyleSheet(
            "QPushButton { background: #FFF1F2; border: none; border-radius: 17px; }"
            "QPushButton:hover { background: #FFE1E5; }"
        )
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(snapshot['id']))
        actions.addWidget(delete_btn)

        actions_wrap = QWidget()
        actions_wrap.setObjectName("actionsWrap")
        actions_wrap.setLayout(actions)
        row.addWidget(actions_wrap, 1)


class PatientsListCard(Card):
    def __init__(self, title="Sample List", empty_text="No saved samples yet.", parent=None):
        super().__init__(title, "mdi6.format-list-bulleted-square", icon_color=BLUE, parent=parent)
        self._empty = QLabel(empty_text)
        self._empty.setStyleSheet(
            f"font-size: 13px; color: {LABEL_CLR}; background: #F8FBFF; "
            f"border: 1px dashed #D9E6F2; border-radius: 16px; padding: 28px;"
        )

        self._table = QFrame()
        self._table.setStyleSheet(
            f"background: #F8FBFF; border: 1px solid #E0EAF4; border-radius: 22px;"
        )
        self._table_lay = QVBoxLayout(self._table)
        self._table_lay.setContentsMargins(12, 12, 12, 12)
        self._table_lay.setSpacing(10)

        hdr = QFrame()
        hdr.setStyleSheet(
            "background: #EFF4FA; border: none; border-radius: 16px;"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 14)
        hdr_lay.setSpacing(16)
        for text, stretch in [
            ("NAME", 2), ("HOSPITAL ID", 2), ("DRUG", 2),
            ("DOSE", 2), ("DATE", 2), ("ACTIONS", 1)
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #6B7C93; "
                "letter-spacing: 1.1px; background: transparent;"
            )
            hdr_lay.addWidget(lbl, stretch)
        self._table_lay.addWidget(hdr)

        self._rows_host = QWidget()
        self._rows_host.setStyleSheet("background: transparent;")
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(10)
        self._table_lay.addWidget(self._rows_host)

        self.body().addWidget(self._empty)
        self.body().addWidget(self._table)

    def set_empty_visible(self, visible: bool):
        self._empty.setVisible(visible)
        self._table.setVisible(not visible)


class ToastMessage(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toastMessage")
        self.setVisible(False)
        self.setStyleSheet("""
            QFrame#toastMessage {
                background: #BFF1C7;
                border: none;
                border-radius: 18px;
            }
        """)
        self.setGraphicsEffect(make_shadow(18, 6, 28))

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(12)

        self.icon = QLabel()
        self.icon.setFixedSize(34, 34)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(
            "background: white; border-radius: 17px; color: #179B48; font-size: 18px; font-weight: bold;"
        )
        row.addWidget(self.icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel()
        self.title.setStyleSheet("color: #123524; font-size: 14px; font-weight: 700;")
        self.body = QLabel()
        self.body.setStyleSheet("color: #335847; font-size: 11px;")
        self.body.setWordWrap(True)
        text_col.addWidget(self.title)
        text_col.addWidget(self.body)
        row.addLayout(text_col, 1)

        self.close_btn = QPushButton()
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setIcon(qta.icon("mdi6.close", color="#4A6A58"))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.close_btn.clicked.connect(self.hide)
        row.addWidget(self.close_btn)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, title, body, duration_ms=2600):
        self.icon.setPixmap(qta.icon("mdi6.check", color="#179B48").pixmap(18, 18))
        self.title.setText(title)
        self.body.setText(body)
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)


# ─────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────
class TDMMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TDM Report — Therapeutic Drug Monitoring")
        self.resize(1000, 820)
        self._saved_patients = []
        self._drafts = []
        self._results_dialog = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._live_plot)
        self._load_saved_patients()
        self._setup_ui()

    # ──────────────────────────────────────
    # Build UI
    # ──────────────────────────────────────
    def _setup_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top header ────────────────────
        header = self._make_header()
        root_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("root")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(32, 28, 32, 40)
        body_layout.setSpacing(20)

        body_layout.addWidget(self._make_tabs())

        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_report_page())
        self.page_stack.addWidget(self._build_patients_page())
        self.page_stack.addWidget(self._build_drafts_page())
        body_layout.addWidget(self.page_stack)
        body_layout.addStretch()

        scroll.setWidget(body)
        root_layout.addWidget(scroll, 1)
        self._toast = ToastMessage(root)
        self._refresh_patients_list()
        self._switch_page(0)
        self._update_action_buttons()
        self._position_toast()

    def _build_report_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)

        lay.addWidget(self._make_patient_card())
        lay.addWidget(self._make_sampling_card())

        calc_row = QHBoxLayout()
        calc_row.setSpacing(12)
        calc_row.addStretch()

        self.calc_btn = QPushButton("Generate Report")
        self.calc_btn.setObjectName("calcBtn")
        self.calc_btn.setFixedHeight(40)
        self.calc_btn.setEnabled(False)
        self.calc_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.calc_btn.clicked.connect(self._calculate)
        calc_row.addWidget(self.calc_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("printBtn")
        self.save_btn.setFixedHeight(40)
        self.save_btn.setEnabled(False)
        self.save_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.save_btn.clicked.connect(self._save_current_patient)
        calc_row.addWidget(self.save_btn)

        self.draft_btn = QPushButton("Draft")
        self.draft_btn.setObjectName("printBtn")
        self.draft_btn.setFixedHeight(40)
        self.draft_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.draft_btn.clicked.connect(self._save_draft)
        calc_row.addWidget(self.draft_btn)

        lay.addLayout(calc_row)
        return page

    def _build_patients_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.sample_list_card = PatientsListCard("Sample List", "No saved samples yet.")
        lay.addWidget(self.sample_list_card)
        return page

    def _build_drafts_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.draft_list_card = PatientsListCard("Draft List", "No drafts yet.")
        lay.addWidget(self.draft_list_card)
        return page

    def _make_tabs(self):
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        shell = QFrame()
        shell.setStyleSheet("background: #E9EEF5; border-radius: 16px;")
        shell_lay = QHBoxLayout(shell)
        shell_lay.setContentsMargins(6, 6, 6, 6)
        shell_lay.setSpacing(6)

        self.report_tab_btn = QPushButton("Report")
        self.report_tab_btn.setIcon(qta.icon("mdi6.flask-outline", color="#718096"))
        self.report_tab_btn.clicked.connect(lambda: self._switch_page(0))
        shell_lay.addWidget(self.report_tab_btn)

        self.patients_tab_btn = QPushButton("Sample List")
        self.patients_tab_btn.setIcon(qta.icon("mdi6.format-list-bulleted-square", color="#718096"))
        self.patients_tab_btn.clicked.connect(lambda: self._switch_page(1))

        self.drafts_tab_btn = QPushButton("Draft List")
        self.drafts_tab_btn.setIcon(qta.icon("mdi6.file-document-edit-outline", color="#718096"))
        self.drafts_tab_btn.clicked.connect(lambda: self._switch_page(2))

        for btn in [self.report_tab_btn, self.patients_tab_btn, self.drafts_tab_btn]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFlat(True)
            btn.setMinimumWidth(122)

        self.patients_badge = QLabel("0")
        self.patients_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.patients_badge.setFixedSize(18, 18)
        self.patients_badge.setStyleSheet(
            f"background: {BLUE}; color: white; border-radius: 9px; font-size: 10px; font-weight: bold;"
        )
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(8)
        badge_row.addWidget(self.patients_tab_btn)
        badge_row.addWidget(self.patients_badge)
        badge_row.addWidget(self.drafts_tab_btn)
        badge_row.addStretch()

        container = QWidget()
        container.setLayout(badge_row)
        shell_lay.addWidget(container)

        row.addWidget(shell)
        row.addStretch()
        return wrap

    def _switch_page(self, index):
        self.page_stack.setCurrentIndex(index)
        self.report_tab_btn.setChecked(index == 0)
        self.patients_tab_btn.setChecked(index == 1)
        self.drafts_tab_btn.setChecked(index == 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def _position_toast(self):
        if not hasattr(self, '_toast'):
            return
        width = min(360, max(280, self.width() - 80))
        self._toast.setFixedWidth(width)
        self._toast.move(self.width() - width - 28, 84)

    def _show_toast(self, title, body):
        self._position_toast()
        self._toast.show_message(title, body)

    # ──────────────────────────────────────
    # Header
    # ──────────────────────────────────────
    def _make_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(62)
        hdr.setStyleSheet(f"background: {NAVY};")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(28, 0, 28, 0)

        # Logo box
        logo_box = QLabel("⚕")
        logo_box.setFixedSize(38, 38)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet(
            f"background: {BLUE}; border-radius: 10px; font-size: 18px; color: white;"
        )
        lay.addWidget(logo_box)
        lay.addSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        t1 = QLabel("TDM Report")
        t1.setStyleSheet("color: white; font-size: 15px; font-weight: bold;")
        t2 = QLabel("Therapeutic Drug Monitoring")
        t2.setStyleSheet("color: #8BAFD4; font-size: 11px;")
        title_col.addWidget(t1)
        title_col.addWidget(t2)
        lay.addLayout(title_col)
        lay.addStretch()

        # Reset button
        reset = QPushButton("New Patient")
        reset.setObjectName("printBtn")
        reset.setFixedHeight(34)
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)

        return hdr

    # ──────────────────────────────────────
    # Patient card
    # ──────────────────────────────────────
    def _make_patient_card(self):
        card = Card("Patient Information", "mdi6.account-outline", icon_color=BLUE)

        field_style = f"""
            QLineEdit {{
                background: #F7FAFE;
                border: 1.5px solid #D6E2EE;
                border-radius: 16px;
                padding: 13px 16px;
                font-size: 14px;
                font-weight: 500;
                color: {TEXT_CLR};
            }}
            QLineEdit:hover {{
                border: 1.5px solid #C3D6EA;
                background: white;
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BLUE};
                background: white;
                selection-background-color: #DDEBFF;
            }}
            QLineEdit::placeholder {{
                color: #95A3B7;
            }}
        """
        combo_style = f"""
            QComboBox {{
                background: #F7FAFE;
                border: 1.5px solid #D6E2EE;
                border-radius: 16px;
                padding: 13px 16px;
                font-size: 14px;
                font-weight: 500;
                color: {TEXT_CLR};
            }}
            QComboBox:hover {{
                border: 1.5px solid #C3D6EA;
                background: white;
            }}
            QComboBox:focus {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: right center;
                border: none;
                width: 34px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0; height: 0;
            }}
            QComboBox QAbstractItemView {{
                border: 1.5px solid {BORDER};
                border-radius: 8px;
                selection-background-color: #EEF2FF;
                selection-color: {BLUE};
                font-size: 13px;
                padding: 4px;
                background: white;
            }}
        """

        def field(placeholder):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            e.setStyleSheet(field_style)
            return e

        self.f_name    = field("Enter patient name")
        self.f_age     = field("e.g. 45")
        self.f_weight  = field("e.g. 70")
        self.f_hosp_no = field("e.g. 01914700094")
        self.f_ward    = field("e.g. Ward 8")
        self.f_dept    = field("e.g. Neph-2")
        self.f_diag    = field("e.g. Post Renal Transplant")
        self.f_diag.setText("Post Rental Transplant")

        # Sex selector
        self.f_sex = QComboBox()
        self.f_sex.addItems(["Male", "Female", "Other"])
        self.f_sex.setStyleSheet(combo_style)

        self.f_tx_date = SmartDateEdit()


        # Medication selector
        self.f_med = MedicationSelector()

        def add_field(layout, row, col, label, widget, span=1):
            col_lbl = QVBoxLayout()
            col_lbl.setSpacing(7)
            col_lbl.addWidget(small_label(label, color="#7E8DA3", size=10, bold=True))
            col_lbl.addWidget(widget)
            layout.addLayout(col_lbl, row, col, 1, span)

        intro = QFrame()
        intro.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F5F9FF, stop:0.55 #FBFDFF, stop:1 #F6FBF9);
            border: none;
            border-radius: 22px;
        """)
        intro_lay = QHBoxLayout(intro)
        intro_lay.setContentsMargins(20, 18, 20, 18)
        intro_lay.setSpacing(16)

        avatar = QLabel()
        avatar.setFixedSize(48, 48)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setPixmap(qta.icon("mdi6.account-heart-outline", color=BLUE).pixmap(22, 22))
        avatar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #EAF2FF, stop:1 #DCEBFF);
            border-radius: 24px;
        """)
        intro_lay.addWidget(avatar)

        intro_text = QVBoxLayout()
        intro_text.setSpacing(3)
        intro_title = QLabel("Patient Intake")
        intro_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 15px; font-weight: 700;")
        intro_sub = QLabel("Core demographics, transplant context and medication profile")
        intro_sub.setStyleSheet("color: #73839A; font-size: 11px;")
        intro_text.addWidget(intro_title)
        intro_text.addWidget(intro_sub)
        intro_lay.addLayout(intro_text)
        intro_lay.addStretch()

        card.body().addWidget(intro)

        demographics_box = QFrame()
        demographics_box.setStyleSheet("""
            background: transparent;
            border: none;
        """)
        demographics_lay = QVBoxLayout(demographics_box)
        demographics_lay.setContentsMargins(2, 2, 2, 2)
        demographics_lay.setSpacing(14)

        demo_head = QHBoxLayout()
        demo_head.setSpacing(10)
        demo_icon = QLabel()
        demo_icon.setFixedSize(28, 28)
        demo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        demo_icon.setPixmap(qta.icon("mdi6.badge-account-outline", color=BLUE).pixmap(16, 16))
        demo_icon.setStyleSheet("background: #EAF2FF; border-radius: 14px;")
        demo_head.addWidget(demo_icon)
        demo_title = QLabel("Patient Demographics")
        demo_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        demo_head.addWidget(demo_title)
        demo_head.addStretch()
        demographics_lay.addLayout(demo_head)

        demo_grid = QGridLayout()
        demo_grid.setSpacing(16)
        demo_grid.setHorizontalSpacing(20)

        # Row 0: Name (wide) | Age | Sex
        add_field(demo_grid, 0, 0, "Patient Name", self.f_name, span=2)
        add_field(demo_grid, 0, 2, "Age (Years)", self.f_age)
        add_field(demo_grid, 0, 3, "Sex", self.f_sex)

        # Row 1: Hospital No | Ward | Department/Unit | Weight
        add_field(demo_grid, 1, 0, "Hospital Number", self.f_hosp_no)
        add_field(demo_grid, 1, 1, "Ward", self.f_ward)
        add_field(demo_grid, 1, 2, "Department / Unit", self.f_dept)
        add_field(demo_grid, 1, 3, "Weight (kg)", self.f_weight)

        demographics_lay.addLayout(demo_grid)
        card.body().addWidget(demographics_box)

        clinical_box = QFrame()
        clinical_box.setStyleSheet("""
            background: transparent;
            border: none;
        """)
        clinical_lay = QVBoxLayout(clinical_box)
        clinical_lay.setContentsMargins(2, 6, 2, 2)
        clinical_lay.setSpacing(14)

        clinical_head = QHBoxLayout()
        clinical_head.setSpacing(10)
        clinical_icon = QLabel()
        clinical_icon.setFixedSize(28, 28)
        clinical_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clinical_icon.setPixmap(qta.icon("mdi6.heart-pulse", color="#14B8A6").pixmap(16, 16))
        clinical_icon.setStyleSheet("background: #E8FBF4; border-radius: 14px;")
        clinical_head.addWidget(clinical_icon)
        clinical_title = QLabel("Clinical Context")
        clinical_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        clinical_head.addWidget(clinical_title)
        clinical_head.addStretch()
        clinical_lay.addLayout(clinical_head)

        clinical_grid = QGridLayout()
        clinical_grid.setSpacing(16)
        clinical_grid.setHorizontalSpacing(20)

        # Row 2: Transplant Date | Diagnosis
        add_field(clinical_grid, 0, 0, "Date of Transplant", self.f_tx_date)
        add_field(clinical_grid, 0, 1, "Diagnosis", self.f_diag)

        clinical_lay.addLayout(clinical_grid)

        # Row 3: Medications (full width)
        med_col = QVBoxLayout()
        med_col.setSpacing(8)
        med_col.addWidget(small_label("Medications", color="#7E8DA3", size=10, bold=True))
        med_col.addWidget(self.f_med)
        clinical_lay.addLayout(med_col)

        card.body().addWidget(clinical_box)

        return card

    # ──────────────────────────────────────
    # Sampling card
    # ──────────────────────────────────────
    def _make_sampling_card(self):
        card = Card("Sampling Configuration", "mdi6.flask-outline", icon_color="#14B8A6")

        field_style = f"""
            QLineEdit {{
                background: #F7FAFE;
                border: 1px solid #D6E2EE;
                border-radius: 16px;
                padding: 13px 16px;
                font-size: 14px;
                font-weight: 500;
                color: {TEXT_CLR};
            }}
            QLineEdit:hover {{
                background: white;
                border: 1px solid #C3D6EA;
            }}
            QLineEdit:focus {{
                background: white;
                border: 1px solid {BLUE};
            }}
            QLineEdit::placeholder {{
                color: #95A3B7;
            }}
        """
        def field(placeholder):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            e.setStyleSheet(field_style)
            return e

        meta_grid = QGridLayout()
        meta_grid.setSpacing(14)
        meta_grid.setHorizontalSpacing(18)

        self.f_drug = field("e.g. MPA")
        self.f_drug.setText("MPA")
        self.f_preparation = field("e.g. Mycept-5")
        self.f_preparation.setText("Mycept-5")
        self.f_dose = field("e.g. 540 mg - 720 mg")
        self.f_dose.setText("540mg - 720mg")
        self.f_dose_dt = SmartDateTimeEdit()
        self.f_sample_collection_date = SmartDateEdit()

        def add_meta(row, col, label, widget):
            col_lay = QVBoxLayout()
            col_lay.setSpacing(7)
            col_lay.addWidget(small_label(label, color="#7E8DA3", size=10, bold=True))
            col_lay.addWidget(widget)
            meta_grid.addLayout(col_lay, row, col)

        meta_intro = QFrame()
        meta_intro.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F6FBFA, stop:1 #FBFEFF);
            border: none;
            border-radius: 22px;
        """)
        meta_intro_lay = QHBoxLayout(meta_intro)
        meta_intro_lay.setContentsMargins(20, 18, 20, 18)
        meta_intro_lay.setSpacing(16)

        meta_icon = QLabel()
        meta_icon.setFixedSize(48, 48)
        meta_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_icon.setPixmap(qta.icon("mdi6.flask-outline", color="#14B8A6").pixmap(22, 22))
        meta_icon.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #E8FBF4, stop:1 #D8F6EB);
            border-radius: 24px;
        """)
        meta_intro_lay.addWidget(meta_icon)

        meta_text = QVBoxLayout()
        meta_text.setSpacing(3)
        meta_title = QLabel("Dose and Sampling Setup")
        meta_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 15px; font-weight: 700;")
        meta_sub = QLabel("Configure requested drug details, dosing timestamp and collection timing")
        meta_sub.setStyleSheet("color: #73839A; font-size: 11px;")
        meta_text.addWidget(meta_title)
        meta_text.addWidget(meta_sub)
        meta_intro_lay.addLayout(meta_text)
        meta_intro_lay.addStretch()
        card.body().addWidget(meta_intro)

        meta_box = QFrame()
        meta_box.setStyleSheet("""
            background: transparent;
            border: none;
        """)
        meta_box_lay = QVBoxLayout(meta_box)
        meta_box_lay.setContentsMargins(2, 2, 2, 2)
        meta_box_lay.setSpacing(14)

        meta_head = QHBoxLayout()
        meta_head.setSpacing(10)
        meta_head_icon = QLabel()
        meta_head_icon.setFixedSize(28, 28)
        meta_head_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_head_icon.setPixmap(qta.icon("mdi6.pill", color="#14B8A6").pixmap(16, 16))
        meta_head_icon.setStyleSheet("background: #E8FBF4; border-radius: 14px;")
        meta_head.addWidget(meta_head_icon)
        meta_head_title = QLabel("Drug and Timing")
        meta_head_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        meta_head.addWidget(meta_head_title)
        meta_head.addStretch()
        meta_box_lay.addLayout(meta_head)

        add_meta(0, 0, "Requested Drug", self.f_drug)
        add_meta(0, 1, "MPA Preparation", self.f_preparation)
        add_meta(0, 2, "Dose of Requested Drug", self.f_dose)
        add_meta(0, 3, "Dose Date & Time", self.f_dose_dt)
        add_meta(1, 0, "Sample Collection Date", self.f_sample_collection_date)
        meta_box_lay.addLayout(meta_grid)
        card.body().addWidget(meta_box)

        # ── Top row: Trough + Duration side by side ──
        control_box = QFrame()
        control_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #FBFDFF, stop:1 #F7FAFE);
            border: none;
            border-radius: 20px;
        """)
        control_lay = QVBoxLayout(control_box)
        control_lay.setContentsMargins(18, 18, 18, 18)
        control_lay.setSpacing(14)

        control_head = QHBoxLayout()
        control_head.setSpacing(10)
        control_icon = QLabel()
        control_icon.setFixedSize(28, 28)
        control_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_icon.setPixmap(qta.icon("mdi6.chart-timeline-variant", color=BLUE).pixmap(16, 16))
        control_icon.setStyleSheet("background: #EAF2FF; border-radius: 14px;")
        control_head.addWidget(control_icon)
        control_title = QLabel("Sampling Controls")
        control_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        control_head.addWidget(control_title)
        control_head.addStretch()
        control_lay.addLayout(control_head)

        top_row = QHBoxLayout()
        top_row.setSpacing(32)

        # Trough input
        trough_col = QVBoxLayout(); trough_col.setSpacing(8)
        trough_col.addWidget(small_label("Trough (Pre-dose) Concentration (μg/mL)", color="#7E8DA3", size=10, bold=True))
        self.trough_edit = QLineEdit()
        self.trough_edit.setPlaceholderText("e.g. 2.93")
        self.trough_edit.setFixedWidth(200)
        self.trough_edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1px solid #DCE7F2;
                border-radius: 16px;
                padding: 13px 18px;
                font-size: 18px;
                font-weight: bold;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                border: 1px solid {BLUE};
            }}
        """)
        self.trough_edit.textChanged.connect(self._on_data_changed)
        trough_col.addWidget(self.trough_edit)
        top_row.addLayout(trough_col)

        # Duration toggles
        dur_col = QVBoxLayout(); dur_col.setSpacing(8)
        dur_col.addWidget(small_label("Sampling Duration (Hours)", color="#7E8DA3", size=10, bold=True))
        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        self.scheme_grp = QButtonGroup(self)
        self.scheme_btns = {}
        for n, lbl in [(4, "4h"), (6, "6h"), (10, "10h")]:
            btn = ToggleButton(lbl)
            if n == 4:
                btn.setChecked(True)
            self.scheme_grp.addButton(btn, n)
            self.scheme_btns[n] = btn
            btn_row.addWidget(btn)
        btn_row.addStretch()
        self.scheme_grp.idClicked.connect(self._on_scheme_changed)
        dur_col.addLayout(btn_row)

        # Helper text under buttons
        hint = QLabel("Time points are editable — tap any time to adjust")
        hint.setStyleSheet(f"color: {LABEL_CLR}; font-size: 11px;")
        dur_col.addWidget(hint)

        top_row.addLayout(dur_col)
        top_row.addStretch()
        control_lay.addLayout(top_row)
        card.body().addWidget(control_box)

        # ── Modern sample table ──
        table_col = QVBoxLayout(); table_col.setSpacing(8)
        table_col.addWidget(small_label("Sample Points", color="#7E8DA3", size=10, bold=True))
        self.sample_table = ModernSampleTable()
        self.sample_table.data_changed.connect(self._on_data_changed)
        table_col.addWidget(self.sample_table)
        card.body().addLayout(table_col)

        # Populate with default scheme
        self._populate_table(4)
        return card

    # ──────────────────────────────────────
    # Results card
    # ──────────────────────────────────────
    # ──────────────────────────────────────
    # Populate table
    # ──────────────────────────────────────
    def _populate_table(self, n):
        if not hasattr(self, 'sample_table'):
            return
        self._current_scheme = n
        times = TIME_SCHEMES.get(n, TIME_SCHEMES[4])
        self.sample_table.populate(times)
        self._live_plot()

    # ──────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────
    def _on_scheme_changed(self, n):
        self._populate_table(n)

    def _on_data_changed(self):
        self._update_action_buttons()
        self._debounce.start(400)   # debounce 400 ms for live plot

    def _live_plot(self):
        return

    # ──────────────────────────────────────
    # Read data from table
    # ──────────────────────────────────────
    def _read_table(self, skip_empty=False):
        """Return (times, concs) including trough at t=0."""
        trough_text = self.trough_edit.text().strip()
        times, concs = [], []

        if trough_text:
            try:
                times.append(0.0)
                concs.append(float(trough_text))
            except ValueError:
                if not skip_empty:
                    return None, None
        elif not skip_empty:
            return None, None

        if skip_empty:
            post_times, post_concs = self.sample_table.get_data()
        else:
            post_times, post_concs = self.sample_table.get_data_strict()
            if post_times is None:
                return None, None

        times.extend(post_times)
        concs.extend(post_concs)
        return times, concs

    def _load_saved_patients(self):
        if not PATIENTS_FILE.exists():
            self._saved_patients = []
            self._drafts = []
            return
        try:
            data = json.loads(PATIENTS_FILE.read_text())
            if isinstance(data, list):
                self._saved_patients = data
                self._drafts = []
            else:
                self._saved_patients = data.get("samples", [])
                self._drafts = data.get("drafts", [])
        except Exception:
            self._saved_patients = []
            self._drafts = []

    def _persist_saved_patients(self):
        PATIENTS_FILE.write_text(json.dumps({
            "samples": self._saved_patients,
            "drafts": self._drafts,
        }, indent=2))

    def _patient_payload(self):
        return {
            'name': self.f_name.text().strip() or 'N/A',
            'age': self.f_age.text().strip() or 'N/A',
            'sex': self.f_sex.currentText(),
            'weight': self.f_weight.text().strip() or 'N/A',
            'hosp_id': self.f_hosp_no.text().strip() or 'N/A',
            'ward': self.f_ward.text().strip() or 'N/A',
            'dept': self.f_dept.text().strip() or 'N/A',
            'drug': self.f_drug.text().strip() or 'MPA',
            'preparation': self.f_preparation.text().strip() or 'Mycept-5',
            'dose': self.f_dose.text().strip() or 'N/A',
            'dose_dt': self.f_dose_dt.dateTime().toString("dd.MM.yy 'at' hh:mmAP"),
            'sample_collection_date': self.f_sample_collection_date.date().toString("dd.MM.yy"),
            'diag': self.f_diag.text().strip() or 'N/A',
            'tx_date': self.f_tx_date.date().toString("dd.MM.yyyy"),
            'med': self.f_med.get_text() or 'N/A',
        }

    def _snapshot_payload(self):
        times, concs = self._read_table(skip_empty=True)
        data = {
            'id': datetime.now().strftime("%Y%m%d%H%M%S%f"),
            'saved_at': datetime.now().strftime("%d/%m/%Y"),
            'patient': self._patient_payload(),
            'scheme': getattr(self, '_current_scheme', 4),
            'trough': self.trough_edit.text().strip(),
            'sample_rows': self.sample_table.get_rows_payload(),
            'times': times,
            'concs': concs,
        }
        if hasattr(self, '_last_pk'):
            data['pk'] = self._last_pk
            data['interp'] = getattr(self, '_last_interp', 'N/A')
        return data

    def _has_any_concentration_input(self):
        if self.trough_edit.text().strip():
            return True
        return any(row.has_concentration() for row in self.sample_table._rows)

    def _can_generate_or_save(self):
        times, concs = self._read_table(skip_empty=False)
        return times is not None and len(times) >= 3

    def _update_action_buttons(self):
        enabled = self._can_generate_or_save()
        self.calc_btn.setEnabled(enabled)
        self.save_btn.setEnabled(enabled)
        self.calc_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)

    def _refresh_patients_list(self):
        if not hasattr(self, 'sample_list_card'):
            return
        def populate(card, items, edit_cb, delete_cb):
            rows_layout = card._rows_lay
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if not items:
                card.set_empty_visible(True)
            else:
                card.set_empty_visible(False)
                for snapshot in reversed(items):
                    row = PatientRow(snapshot)
                    row.edit_requested.connect(edit_cb)
                    row.delete_requested.connect(delete_cb)
                    rows_layout.addWidget(row)
                rows_layout.addStretch()

        populate(self.sample_list_card, self._saved_patients, self._load_saved_sample, self._delete_saved_patient)
        if hasattr(self, 'draft_list_card'):
            populate(self.draft_list_card, self._drafts, self._load_draft, self._delete_draft)
        self.patients_badge.setText(str(len(self._saved_patients)))

    def _save_current_patient(self):
        if not self._can_generate_or_save():
            QMessageBox.information(self, "Incomplete Data", "Complete the concentration values before saving to Sample List.")
            return
        snapshot = self._snapshot_payload()
        if getattr(self, '_active_record_source', None) == 'draft' and getattr(self, '_active_record_id', None):
            self._drafts = [p for p in self._drafts if p['id'] != self._active_record_id]
        self._saved_patients.append(snapshot)
        self._persist_saved_patients()
        self._refresh_patients_list()
        self._clear_form_state()
        self._switch_page(1)
        self._show_toast("Saved successfully", "Sample moved to Sample List.")

    def _save_draft(self):
        snapshot = self._snapshot_payload()
        snapshot.pop('pk', None)
        snapshot.pop('interp', None)
        if getattr(self, '_active_record_source', None) == 'draft' and getattr(self, '_active_record_id', None):
            self._drafts = [p for p in self._drafts if p['id'] != self._active_record_id]
        self._drafts.append(snapshot)
        self._persist_saved_patients()
        self._refresh_patients_list()
        self._clear_form_state()
        self._switch_page(2)
        self._show_toast("Draft saved successfully", "Sample moved to Draft List.")

    def _load_saved_sample(self, patient_id):
        snapshot = next((p for p in self._saved_patients if p['id'] == patient_id), None)
        if snapshot:
            self._load_snapshot(snapshot)

    def _load_draft(self, patient_id):
        snapshot = next((p for p in self._drafts if p['id'] == patient_id), None)
        if not snapshot:
            return
        self._load_snapshot(snapshot)

    def _load_snapshot(self, snapshot):
        self._active_record_id = snapshot.get('id')
        self._active_record_source = 'draft' if snapshot in self._drafts else 'sample'
        patient = snapshot.get('patient', {})
        self.f_name.setText(patient.get('name', '') if patient.get('name') != 'N/A' else '')
        self.f_age.setText(patient.get('age', '') if patient.get('age') != 'N/A' else '')
        self.f_weight.setText(patient.get('weight', '') if patient.get('weight') != 'N/A' else '')
        self.f_hosp_no.setText(patient.get('hosp_id', '') if patient.get('hosp_id') != 'N/A' else '')
        self.f_ward.setText(patient.get('ward', '') if patient.get('ward') != 'N/A' else '')
        self.f_dept.setText(patient.get('dept', '') if patient.get('dept') != 'N/A' else '')
        self.f_diag.setText(patient.get('diag', 'Post Rental Transplant') if patient.get('diag') != 'N/A' else 'Post Rental Transplant')
        self.f_drug.setText(patient.get('drug', 'MPA'))
        self.f_preparation.setText(patient.get('preparation', 'Mycept-5'))
        self.f_dose.setText(patient.get('dose', '540mg - 720mg') if patient.get('dose') != 'N/A' else '')
        tx_date = QDate.fromString(patient.get('tx_date', ''), "dd.MM.yyyy")
        self.f_tx_date.setDate(tx_date if tx_date.isValid() else QDate.currentDate())
        dose_dt = QDateTime.fromString(patient.get('dose_dt', ''), "dd.MM.yy 'at' hh:mmAP")
        if dose_dt.isValid():
            self.f_dose_dt.setDateTime(dose_dt)
        sample_dt = QDate.fromString(patient.get('sample_collection_date', ''), "dd.MM.yy")
        if sample_dt.isValid():
            self.f_sample_collection_date.setDate(sample_dt)

        self.f_med.clear_selection()
        meds = patient.get('med', '')
        if meds and meds != 'N/A':
            for med in [m.strip() for m in meds.split(',') if m.strip()]:
                self.f_med._add_tag(med)

        scheme = snapshot.get('scheme', 4)
        if scheme in self.scheme_btns:
            self.scheme_grp.button(scheme).setChecked(True)
        rows_payload = snapshot.get('sample_rows')
        if rows_payload:
            self._current_scheme = scheme
            self.sample_table.set_rows_payload(rows_payload)
            self.trough_edit.setText(snapshot.get('trough', ''))
        else:
            times = snapshot.get('times', [])
            concs = snapshot.get('concs', [])
            if times:
                if times[0] == 0 and concs:
                    self.trough_edit.setText("" if concs[0] is None else str(concs[0]))
                    self.sample_table.set_data(times[1:], concs[1:])
                else:
                    self.trough_edit.clear()
                    self.sample_table.set_data(times, concs)
            else:
                self.trough_edit.clear()
                self._populate_table(scheme)

        if snapshot.get('pk'):
            times = snapshot.get('times', [])
            concs = snapshot.get('concs', [])
            self._last_pk = snapshot['pk']
            self._last_times = times
            self._last_concs = concs
            self._last_interp = snapshot.get('interp', 'N/A')
        else:
            for attr in ['_last_pk', '_last_times', '_last_concs', '_last_interp']:
                if hasattr(self, attr):
                    delattr(self, attr)
        self._update_action_buttons()
        self._switch_page(0)

    def _delete_saved_patient(self, patient_id):
        self._saved_patients = [p for p in self._saved_patients if p['id'] != patient_id]
        self._persist_saved_patients()
        self._refresh_patients_list()

    def _delete_draft(self, patient_id):
        self._drafts = [p for p in self._drafts if p['id'] != patient_id]
        self._persist_saved_patients()
        self._refresh_patients_list()

    def _apply_results(self, pk, interp):
        if self._results_dialog is None:
            self._results_dialog = ResultsDialog(self, print_handler=self._print_report)
        self._results_dialog.apply_results(pk, interp)
        if hasattr(self, '_last_times') and hasattr(self, '_last_concs'):
            self._results_dialog.plot_data(self._last_times, self._last_concs, drug='MPA')
        self._results_dialog.show()
        self._results_dialog.raise_()
        self._results_dialog.activateWindow()

    # ──────────────────────────────────────
    # Calculate
    # ──────────────────────────────────────
    def _calculate(self):
        times, concs = self._read_table(skip_empty=False)

        if times is None or len(times) < 3:
            QMessageBox.warning(
                self, "Insufficient Data",
                "Please enter at least the trough + 2 post-dose concentrations."
            )
            return

        drug = self.f_drug.text().strip() or 'MPA'
        pk = calculate_auc_full(times, concs)

        # Interpretation (MPA default)
        interp, _ = interpret_result('MPA', pk['auc_0_12'])
        self._last_pk = pk
        self._last_times = times
        self._last_concs = concs
        self._last_interp = interp
        self._apply_results(pk, interp)

    # ──────────────────────────────────────
    # Print / PDF
    # ──────────────────────────────────────
    def _print_report(self):
        if not hasattr(self, '_last_pk'):
            return
        from report_print import build_report_html
        graph_uri = None
        if self._results_dialog is not None:
            buf = BytesIO()
            self._results_dialog.canvas.fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
            graph_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        html = build_report_html(
            patient=self._patient_payload(),
            pk=self._last_pk,
            interp=self._last_interp,
            times=self._last_times,
            concs=self._last_concs,
            graph_uri=graph_uri,
        )
        tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
        with tmp:
            tmp.write(html)
        webbrowser.open(Path(tmp.name).as_uri())

    # ──────────────────────────────────────
    # Reset
    # ──────────────────────────────────────
    def _clear_form_state(self):
        self._active_record_id = None
        self._active_record_source = None
        for edit in [self.f_name, self.f_age, self.f_weight, self.f_hosp_no,
                     self.f_ward, self.f_dept, self.f_drug, self.f_preparation, self.f_dose,
                     self.f_diag, self.trough_edit]:
            edit.clear()
        self.f_drug.setText("MPA")
        self.f_preparation.setText("Mycept-5")
        self.f_dose.setText("540mg - 720mg")
        self.f_diag.setText("Post Rental Transplant")
        self.f_med.clear_selection()
        self.f_tx_date.setDate(QDate.currentDate())
        self.f_dose_dt.setDateTime(QDateTime.currentDateTime())
        self.f_sample_collection_date.setDate(QDate.currentDate())
        self._populate_table(4)
        self.scheme_grp.button(4).setChecked(True)
        self._update_action_buttons()
        if self._results_dialog is not None:
            self._results_dialog.close()
        for attr in ['_last_pk', '_last_times', '_last_concs', '_last_interp']:
            if hasattr(self, attr):
                delattr(self, attr)

    def _reset(self):
        self._clear_form_state()
