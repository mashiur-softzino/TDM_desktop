"""
Sampling-related UI classes: sample table rows, gradient chart, medication selector.
"""

from ui_constants import (
    BLUE, LABEL_CLR, TEXT_CLR, BORDER, RED,
)
from ui_widgets import Card, make_shadow, small_label, value_label, ToastMessage, ConfirmActionModal

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QDialog, QSizePolicy, QListWidget, QListWidgetItem,
    QApplication, QLayout,
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QEvent, QSize, QPoint, QRect,
)
from PyQt6.QtGui import QColor, QDoubleValidator
import qtawesome as qta
from database import load_medications, add_medication, update_medication, delete_medication
from calculations import canonical_drug_name


# Rainbow palette — one colour per row position (up to 10)
ROW_COLORS = [
    "#F44336", "#FF7043", "#FF9800", "#FFC107",
    "#8BC34A", "#26A69A", "#29B6F6", "#5C6BC0",
    "#AB47BC", "#EC407A",
]

DEFAULT_MEDICATIONS = [
    "Tacrolimus (TAC)", "Cyclosporine (CsA)", "Mycophenolate (MPA)",
    "Prednisolone", "Methylprednisolone", "Amlodipine", "Metoprolol",
    "Losartan", "Atorvastatin", "Rosuvastatin", "Furosemide",
    "Spironolactone", "Omeprazole", "Pantoprazole", "Insulin",
    "Glimepiride", "Metformin", "Febuxostat", "Allopurinol",
    "Cotrimoxazole", "Valganciclovir", "Fluconazole", "Omega-3",
    "Calcium + Vitamin D", "Sirolimus", "Everolimus", "Azathioprine",
    "Linagliptin", "Ostoref-D", "Shelcal",
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
                background: #FFFBF5;
                border: none;
                border-bottom: 1px solid {'transparent' if is_last else '#FDBA74'};
            }}
            QFrame#sampleRow:hover {{
                background: #FFF7ED;
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
                background: #FFEDD5;
                border: none;
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: bold;
                color: {TEXT_CLR};
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit:focus {{
                background: #FED7AA;
                color: #C2410C;
            }}
        """)
        row.addWidget(self.time_edit)

        unit = QLabel("h")
        unit.setFixedWidth(20)
        unit.setStyleSheet(f"color: {LABEL_CLR}; font-size: 12px; background: transparent;")
        row.addWidget(unit)

        row.addStretch()

        # Concentration input
        self.conc_edit = QLineEdit()
        self.conc_edit.setPlaceholderText("Enter value…")
        self.conc_edit.setMaximumWidth(200)
        self.conc_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conc_edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1px solid #FDBA74;
                border-radius: 12px;
                padding: 9px 16px;
                font-size: 14px;
                color: {TEXT_CLR};
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit:focus {{
                background: white;
                border: 1.5px solid #EA580C;
                color: {TEXT_CLR};
            }}
        """)
        self.conc_edit.setValidator(QDoubleValidator(0.0, 1000.0, 3))
        self.conc_edit.textChanged.connect(self.changed)
        self.time_edit.setValidator(QDoubleValidator(0.0, 100.0, 2))
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
                background: white;
                border: 2.5px solid #F97316;
                border-radius: 20px;
            }}
        """)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(3, 3, 3, 3)
        self._outer.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("sampleHdr")
        hdr.setStyleSheet(f"""
            QFrame#sampleHdr {{
                background: #FFF7ED;
                border: none;
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
                border-bottom: 2.5px solid #FDBA74;
            }}
        """)
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(18, 10, 18, 10)
        hdr_row.setSpacing(14)

        lbl_time = QLabel("TIME (H)")
        lbl_time.setFixedWidth(80)
        lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_time.setStyleSheet(
            f"color: {LABEL_CLR}; font-size: 11px; font-weight: bold;"
            "letter-spacing: 1px; background: transparent;"
        )
        
        lbl_conc = QLabel("CONC. (μg/mL)")
        lbl_conc.setFixedWidth(200)
        lbl_conc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_conc.setStyleSheet(
            f"color: {LABEL_CLR}; font-size: 11px; font-weight: bold;"
            "letter-spacing: 1px; background: transparent;"
        )
        
        hdr_row.addSpacing(18) # dot space
        hdr_row.addWidget(lbl_time)
        hdr_row.addSpacing(20) # unit space
        hdr_row.addStretch()
        hdr_row.addWidget(lbl_conc)
        self._outer.addWidget(hdr)

        # Rows container
        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._outer.addWidget(self._rows_widget)

        self._rows: list = []

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


# ─────────────────────────────────────────
# Gradient matplotlib canvas
# ─────────────────────────────────────────
class GradientCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        import matplotlib
        matplotlib.use('QtAgg')
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        self.fig = Figure(figsize=(8, 4), dpi=110, facecolor='white')
        self.ax = self.fig.add_subplot(111)
        self._canvas = FigureCanvas(self.fig)
        self._canvas.installEventFilter(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(360)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.88, bottom=0.20)
        self._draw_empty()

    def _scroll_parent(self, event):
        parent = self.parent()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parent()
        if parent is not None:
            bar = parent.verticalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return True
        return False

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_canvas", None) and event.type() == QEvent.Type.Wheel:
            if self._scroll_parent(event):
                return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if not self._scroll_parent(event):
            super().wheelEvent(event)

    def _draw_empty(self):
        self.ax.clear()
        self.ax.set_facecolor('white')
        self.ax.set_xlabel('Time (h)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_ylabel('Conc. (μg/mL)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_title('Concentration-Time Graph', fontsize=13,
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
        self._canvas.draw()

    def cleanup(self):
        try:
            self.ax.clear()
            self.fig.clear()
            self._canvas.close()
            self.close()
        except Exception:
            pass

    def plot(self, times, concs, drug='MPA'):
        import numpy as np
        from matplotlib.collections import LineCollection
        import matplotlib.pyplot as plt

        self.ax.clear()
        times = np.array(times, dtype=float)
        concs = np.array(concs, dtype=float)
        order = np.argsort(times)
        times = times[order]
        concs = concs[order]

        self.ax.set_facecolor('white')
        self.ax.grid(True, linestyle='--', color='#EEEEEE', alpha=0.9, zorder=0)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color(BORDER)
        self.ax.spines['bottom'].set_color(BORDER)
        self.ax.tick_params(colors='#9E9E9E', labelsize=10)

        t_fine = times
        c_fine = concs
        points = np.array([t_fine, c_fine]).T.reshape(-1, 1, 2)
        segs = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(t_fine[0], t_fine[-1] if t_fine[-1] != t_fine[0] else t_fine[0] + 1)
        lc = LineCollection(segs, cmap='rainbow', norm=norm, linewidth=2.8, zorder=3)
        lc.set_array(t_fine)
        self.ax.add_collection(lc)

        n_fill = 80
        t_segs = np.linspace(t_fine[0], t_fine[-1], n_fill + 1)
        for i in range(n_fill):
            ts = t_segs[i:i + 2]
            cs_seg = np.interp(ts, times, concs)
            col = plt.cm.rainbow(norm(t_segs[i]))
            self.ax.fill_between(ts, 0, cs_seg, color=col, alpha=0.18, zorder=1)

        dot_colors = plt.cm.rainbow(np.linspace(0, 1, len(times)))
        for t, c, col in zip(times, concs, dot_colors):
            self.ax.scatter(t, c, color=col, s=90, zorder=5,
                            edgecolors='white', linewidth=2)

        self.ax.annotate(
            'Trough', (times[0], concs[0]),
            xytext=(8, 12), textcoords='offset points',
            color=RED, fontsize=9, fontweight='bold',
            arrowprops=dict(arrowstyle='-', color=RED, lw=1)
        )

        conc_unit = '??g/mL' if canonical_drug_name(drug) == 'MPA' else 'ng/mL'
        self.ax.set_xlabel('Time (min)', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_ylabel(f'Conc. ({conc_unit})', fontsize=11, color='#9E9E9E', labelpad=8)
        self.ax.set_title('Concentration-Time Graph', fontsize=13,
                          fontweight='bold', color='#1A1A2E', pad=14)
        self.ax.set_xlim(left=0, right=times[-1])
        self.ax.set_xticks(times)
        self.ax.set_xticklabels([f"{int(t * 60)}" for t in times])
        self.ax.set_ylim(bottom=0)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.88, bottom=0.20)
        self._canvas.draw()



# ─────────────────────────────────────────
# Medication tag + modal
# ─────────────────────────────────────────
class MedTag(QFrame):
    """Single selected medication pill with × remove button."""
    removed = pyqtSignal(str)

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setObjectName("medTag")
        self.setStyleSheet(f"""
            QFrame#medTag {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #ECFBF4, stop:1 #E3F7EE);
                border-radius: 14px;
                border: 1px solid #CFECDD;
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(8)

        lbl = QLabel(name)
        lbl.setStyleSheet("color: #099268; font-size: 12px; font-weight: 700; background: transparent;")
        row.addWidget(lbl)

        btn = QPushButton("×")
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #D8F3E7;
                color: #0E9F6E;
                border: none;
                border-radius: 11px;
                font-size: 14px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{ background: #C7EEDC; }}
        """)
        btn.clicked.connect(lambda: self.removed.emit(self.name))
        row.addWidget(btn)


class FlowLayout(QLayout):
    """Small wrapping layout for medication tags inside a scroll area."""

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only=False):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


class MedAddModal(QDialog):
    """Modal to add or edit a medication."""
    def __init__(self, parent=None, title="Add Medication", action_label="Add Medication", initial_value=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(400)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background: white;
                border-radius: 20px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Top colored banner ──────────────────
        banner = QFrame()
        banner.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #16A34A, stop:1 #22C55E);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.pill", color="white").pixmap(22, 22))
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Add or update a medication in the list")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.75); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        lay.addWidget(banner)

        # ── Body ────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: white;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 20, 24, 20)
        body_lay.setSpacing(16)

        lbl = QLabel("Medication Name")
        lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {LABEL_CLR}; letter-spacing: 0.8px;")
        body_lay.addWidget(lbl)

        self.edit = QLineEdit()
        self.edit.setText(initial_value)
        self.edit.setPlaceholderText("e.g. Voriconazole")
        self.edit.setStyleSheet(f"""
            QLineEdit {{
                background: #F7FAFE;
                border: 1.5px solid {BORDER};
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 14px;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
        """)
        self.edit.returnPressed.connect(self.accept)
        body_lay.addWidget(self.edit)

        # ── Buttons ─────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #FEE2E2; color: #B91C1C;
                border: 1.5px solid #FCA5A5; border-radius: 10px;
                font-size: 13px; padding: 0 20px;
            }
            QPushButton:hover {
                background: #DC2626; color: white;
                border: 1.5px solid #B91C1C;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        add_btn = QPushButton(action_label)
        add_btn.setFixedHeight(40)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #16A34A; color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0 20px;
            }}
            QPushButton:hover {{ background: #15803D; }}
        """)
        add_btn.setDefault(True)
        add_btn.setAutoDefault(True)
        add_btn.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(add_btn)
        body_lay.addLayout(btn_row)

        lay.addWidget(body)

    def get_text(self):
        return self.edit.text().strip()


class MedicationOptionRow(QFrame):
    selected = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, name: str, accent: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 18, 4)
        row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setPixmap(qta.icon("mdi6.pill", color="#0E9F6E").pixmap(16, 16))
        icon_lbl.setStyleSheet("background: transparent;")
        row.addWidget(icon_lbl)

        self._label = QLabel(name)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._label.setStyleSheet(
            f"background: transparent; color: {'#1A73E8' if accent else TEXT_CLR}; font-size: 13px; padding: 8px 10px;"
        )
        row.addWidget(self._label, 1)

        edit_btn = QPushButton()
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setFixedSize(24, 24)
        edit_btn.setIcon(qta.icon("mdi6.pencil-outline", color="#64748B"))
        edit_btn.setIconSize(edit_btn.size() * 0.6)
        edit_btn.setStyleSheet("QPushButton { background: #F4F8FC; border: none; border-radius: 12px; }")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.name))
        row.addWidget(edit_btn)

        delete_btn = QPushButton()
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setIcon(qta.icon("mdi6.trash-can-outline", color=RED))
        delete_btn.setIconSize(delete_btn.size() * 0.6)
        delete_btn.setStyleSheet("QPushButton { background: #FFF1F2; border: none; border-radius: 12px; }")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.name))
        row.addWidget(delete_btn)

    def mousePressEvent(self, event):
        self.selected.emit(self.name)
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        parent = self.parent()
        while parent is not None and not isinstance(parent, QListWidget):
            parent = parent.parent()
        if parent is not None:
            bar = parent.verticalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)


class MedicationEmptyRow(QFrame):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setPixmap(qta.icon("mdi6.information-outline", color="#94A3B8").pixmap(16, 16))
        icon_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(icon_lbl)

        lbl = QLabel(message)
        lbl.setStyleSheet("background: transparent; color: #64748B; font-size: 13px;")
        lay.addWidget(lbl)

    def wheelEvent(self, event):
        parent = self.parent()
        while parent is not None and not isinstance(parent, QListWidget):
            parent = parent.parent()
        if parent is not None:
            bar = parent.verticalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)


class MedicationListWidget(QListWidget):
    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())
        event.accept()


class DrugSelector(QFrame):
    """
    Single-select drug picker — same pattern as MedicationSelector.
    Selected drug appears as text inside the search bar. No tag below.
    """
    currentTextChanged = pyqtSignal(str)
    DRUG_OPTIONS = ["MPA"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._selected = self.DRUG_OPTIONS[0]

        QApplication.instance().installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Search bar (also displays selected drug)
        search_wrap = QFrame()
        search_wrap.setObjectName("drugSearchWrap")
        search_wrap.setStyleSheet(f"""
            QFrame#drugSearchWrap {{
                background: white;
                border: 1px solid #DCE7F2;
                border-radius: 16px;
            }}
            QFrame#drugSearchWrap:focus-within {{
                border: 1px solid {BLUE};
            }}
        """)
        sw_lay = QHBoxLayout(search_wrap)
        sw_lay.setContentsMargins(14, 0, 14, 0)
        sw_lay.setSpacing(10)

        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi6.magnify", color=LABEL_CLR).pixmap(16, 16))
        search_icon.setFixedSize(16, 16)
        search_icon.setStyleSheet("background: transparent;")
        sw_lay.addWidget(search_icon)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search drug...")
        self._search.installEventFilter(self)
        self._search.textChanged.connect(self._on_search)
        sw_lay.addWidget(self._search, 1)
        outer.addWidget(search_wrap)

        self._apply_selected_style()

        # Floating dropdown (child of window, same as MedicationSelector)
        self._drop_frame = QFrame(self)
        self._drop_frame.setObjectName("drugInlineDrop")
        self._drop_frame.hide()
        self._drop_frame.setStyleSheet(f"""
            QFrame#drugInlineDrop {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        self._drop_frame.setGraphicsEffect(make_shadow(16, 6, 30))

        drop_lay = QVBoxLayout(self._drop_frame)
        drop_lay.setContentsMargins(6, 4, 6, 6)
        drop_lay.setSpacing(0)

        self._list = MedicationListWidget()
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none;
                font-size: 13px; color: {TEXT_CLR}; outline: none;
            }}
            QListWidget::item {{ padding: 9px 14px; border-radius: 8px; }}
            QListWidget::item:hover {{ background: #EBF5FF; color: {BLUE}; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 6px 2px 6px 0; }}
            QScrollBar::handle:vertical {{ background: #C9D8EA; border-radius: 4px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        drop_lay.addWidget(self._list)

    def _apply_selected_style(self):
        self._search.blockSignals(True)
        self._search.setText(self._selected)
        self._search.blockSignals(False)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                border: none; background: transparent;
                font-size: 14px; font-weight: 700;
                color: {BLUE}; padding: 12px 0;
            }}
        """)

    def _apply_search_style(self):
        self._search.setStyleSheet(f"""
            QLineEdit {{
                border: none; background: transparent;
                font-size: 14px; font-weight: 400;
                color: {TEXT_CLR}; padding: 12px 0;
            }}
        """)

    def _on_search(self, text: str):
        if text == self._selected:
            return
        self._apply_search_style()
        self._show_options(self._filtered_options(text))

    def _filtered_options(self, text: str = "") -> list:
        q = text.strip().lower()
        return [d for d in self.DRUG_OPTIONS if q in d.lower()] if q else list(self.DRUG_OPTIONS)

    def _show_options(self, items: list):
        host = self.window()
        if self._drop_frame.parentWidget() is not host:
            self._drop_frame.setParent(host)
            self._drop_frame.hide()

        frame_width = max(self._search.width() + 36, 260)
        row_width = frame_width - 22
        self._list.clear()

        if not items:
            item = QListWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._list.addItem(item)
            empty = MedicationEmptyRow("No drug found.", parent=self._list.viewport())
            empty.setFixedWidth(row_width)
            self._list.setItemWidget(item, empty)
            item.setSizeHint(empty.sizeHint())
        else:
            for drug in items:
                item = QListWidgetItem()
                item.setSizeHint(QSize(row_width, 42))
                self._list.addItem(item)
                row = self._make_option_row(drug, row_width)
                self._list.setItemWidget(item, row)

        rows = min(max(len(items), 1), 6)
        from PyQt6.QtCore import QPoint
        bottom_left = host.mapFromGlobal(self._search.mapToGlobal(QPoint(0, self._search.height())))
        available_below = max(70, host.height() - bottom_left.y() - 18)
        frame_height = min(rows * 42 + 10, available_below)
        self._list.setFixedHeight(max(42, frame_height - 10))
        self._drop_frame.setFixedSize(frame_width, frame_height)
        self._drop_frame.move(bottom_left)
        self._drop_frame.show()
        self._drop_frame.raise_()

    def _make_option_row(self, drug: str, width: int) -> QFrame:
        w = QFrame(self._list.viewport())
        w.setFixedWidth(width)
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(qta.icon("mdi6.pill", color="#0E9F6E").pixmap(16, 16))
        icon.setStyleSheet("background: #DCFCE7; border-radius: 14px;")
        lay.addWidget(icon)

        lbl = QLabel(drug)
        lbl.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; background: transparent;")
        lay.addWidget(lbl, 1)

        if drug == self._selected:
            tick = QLabel("✓")
            tick.setStyleSheet(f"color: {BLUE}; font-weight: bold; background: transparent;")
            lay.addWidget(tick)

        w.mousePressEvent = lambda _e, d=drug: self._select(d)
        return w

    def _select(self, drug: str):
        changed = drug != self._selected
        self._selected = drug
        self._hide_dropdown()
        self._apply_selected_style()
        if changed:
            self.currentTextChanged.emit(drug)

    def _hide_dropdown(self):
        self._drop_frame.hide()
        self._list.clear()

    def eventFilter(self, _obj, event) -> bool:
        search = getattr(self, "_search", None)
        if search is not None and _obj == search and event.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.MouseButtonPress,
        }:
            def _open():
                search.blockSignals(True)
                search.clear()
                search.blockSignals(False)
                self._apply_search_style()
                self._show_options(self.DRUG_OPTIONS)
            QTimer.singleShot(0, _open)
            return False
        if event.type() == QEvent.Type.Wheel and self._drop_frame.isVisible():
            obj_widget = _obj if isinstance(_obj, QWidget) else None
            if obj_widget is not None and (
                obj_widget is self._list
                or obj_widget is self._list.viewport()
                or self._drop_frame.isAncestorOf(obj_widget)
            ):
                bar = self._list.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                return True
            self._hide_dropdown()
            self._apply_selected_style()
            return False
        if event.type() == QEvent.Type.ApplicationDeactivate:
            self._hide_dropdown()
            self._apply_selected_style()
            return False
        if _obj == self.window() and event.type() in {
            QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Hide,
            QEvent.Type.WindowStateChange, QEvent.Type.WindowDeactivate,
        }:
            self._hide_dropdown()
            self._apply_selected_style()
            return False
        if event.type() == QEvent.Type.MouseButtonPress and self._drop_frame.isVisible():
            click_pos = event.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(click_pos)
            drop_local = self._drop_frame.mapFromGlobal(click_pos)
            if not self.rect().contains(local_pos) and not self._drop_frame.rect().contains(drop_local):
                self._hide_dropdown()
                self._apply_selected_style()
        return False

    def currentText(self) -> str:
        return self._selected

    def setCurrentText(self, text: str):
        if not text:
            return
        if text not in self.DRUG_OPTIONS:
            DrugSelector.DRUG_OPTIONS = list(dict.fromkeys(self.DRUG_OPTIONS + [text]))
        self._selected = text
        self._apply_selected_style()

    def setCurrentIndex(self, index: int):
        if 0 <= index < len(self.DRUG_OPTIONS):
            self._select(self.DRUG_OPTIONS[index])


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
    med_added = pyqtSignal(str)
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._all_meds = load_medications()
        self._selected: list = []

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
        search_wrap.setMaximumWidth(980)
        search_wrap.setStyleSheet(f"""
            QFrame#searchWrap {{
                background: white;
                border: 1px solid #DCE7F2;
                border-radius: 16px;
            }}
            QFrame#searchWrap:focus-within {{
                border: 1px solid #B9E5D1;
            }}
        """)
        sw_lay = QHBoxLayout(search_wrap)
        sw_lay.setContentsMargins(14, 0, 14, 0)
        sw_lay.setSpacing(10)

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
                font-size: 14px;
                color: {TEXT_CLR};
                padding: 12px 0;
            }}
        """)
        self._search.installEventFilter(self)
        self._search.textChanged.connect(self._on_search)
        sw_lay.addWidget(self._search, 1)

        ctrl.addWidget(search_wrap, 1)

        add_btn = QPushButton()
        add_btn.setFixedSize(48, 48)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add custom medication")
        add_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        add_btn.setIconSize(add_btn.size() * 0.52)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #0E9F6E; border: none; border-radius: 14px;
            }}
            QPushButton:hover {{ background: #0B8A60; }}
        """)
        add_btn.clicked.connect(self._open_modal)
        ctrl.addWidget(add_btn)
        ctrl.addStretch()

        outer.addLayout(ctrl)

        # ── Floating dropdown (overlay, not in layout) ──
        self._drop_frame = QFrame(self)
        self._drop_frame.setObjectName("inlineDrop")
        self._drop_frame.hide()
        self._drop_frame.setStyleSheet(f"""
            QFrame#inlineDrop {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        self._drop_frame.setGraphicsEffect(make_shadow(16, 6, 30))

        drop_lay = QVBoxLayout(self._drop_frame)
        drop_lay.setContentsMargins(6, 4, 6, 6)
        drop_lay.setSpacing(0)

        self._list = MedicationListWidget()
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
                background: #ECFBF4;
                color: #099268;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 6px 2px 6px 0;
            }}
            QScrollBar::handle:vertical {{
                background: #C9D8EA;
                border-radius: 4px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #B6CAE2;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        drop_lay.addWidget(self._list)

        outer.addSpacing(4)

        # ── Tags scroll ───────────────────────────
        self._tags_widget = QWidget()
        self._tags_widget.setStyleSheet("background: transparent;")
        self._tags_layout = FlowLayout(self._tags_widget, margin=0, spacing=6)

        self._tags_scroll = QScrollArea()
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tags_scroll.setFixedHeight(116)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tags_scroll.setWidget(self._tags_widget)
        self._tags_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 6px 2px 6px 4px;
            }
            QScrollBar::handle:vertical {
                background: #C9D8EA;
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #B6CAE2;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        outer.addWidget(self._tags_scroll)
        self._update_tags_visibility()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_tags_visibility)

    # ── Show all options when search field is clicked empty ──
    def _search_clicked(self, event):
        if not self._search.text().strip():
            self._show_options(self._all_meds)
        type(self._search).mousePressEvent(self._search, event)


    # ── Filter as user types ──────────────────────
    def _on_search(self, text: str):
        self._show_options(self._filtered_options(text))

    def _filtered_options(self, text: str = "") -> list:
        q = text.strip().lower()
        items = [m for m in self._all_meds if m not in self._selected]
        if not q:
            return items
        return [m for m in items if q in m.lower()]

    def _show_options(self, items: list):
        host = self.window()
        if self._drop_frame.parentWidget() is not host:
            self._drop_frame.setParent(host)
            self._drop_frame.hide()

        frame_width = max(self._search.width() + 36, 360)
        row_width = frame_width - 22

        self._list.clear()
        if not items:
            item = QListWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._list.addItem(item)
            row = MedicationEmptyRow("No medication found. Use + to add a new one.", parent=self._list.viewport())
            row.setFixedWidth(row_width)
            self._list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())
        else:
            for name in items:
                item = QListWidgetItem()
                item.setSizeHint(QSize(row_width, 42))
                self._list.addItem(item)
                row = MedicationOptionRow(name, parent=self._list.viewport())
                row.setFixedWidth(row_width)
                row.selected.connect(self._select_option)
                row.edit_requested.connect(self._edit_option)
                row.delete_requested.connect(self._delete_option)
                self._list.setItemWidget(item, row)
                item.setSizeHint(row.sizeHint())
        rows = min(max(len(items), 1), 7)

        # Position dropdown below the search bar inside the app window
        from PyQt6.QtCore import QPoint
        bottom_left = host.mapFromGlobal(self._search.mapToGlobal(QPoint(0, self._search.height())))
        available_below = max(70, host.height() - bottom_left.y() - 18)
        desired_list_height = max(rows, 1) * 42
        desired_frame_height = desired_list_height + 10
        frame_height = min(desired_frame_height, available_below)
        self._list.setFixedHeight(max(42, frame_height - 10))
        self._drop_frame.setFixedSize(frame_width, frame_height)
        self._drop_frame.move(bottom_left)
        self._drop_frame.show()
        self._drop_frame.raise_()

    def eventFilter(self, _obj: QObject, event: QEvent) -> bool:
        """Close dropdown when user clicks anywhere outside this widget."""
        search = getattr(self, "_search", None)

        if search is not None and _obj == search and event.type() == QEvent.Type.KeyPress:
            if self._drop_frame.isVisible():
                key = event.key()
                if key == Qt.Key.Key_Down:
                    curr = self._list.currentRow()
                    if curr < self._list.count() - 1:
                        self._list.setCurrentRow(curr + 1)
                    elif curr == -1 and self._list.count() > 0:
                        self._list.setCurrentRow(0)
                    return True
                elif key == Qt.Key.Key_Up:
                    curr = self._list.currentRow()
                    if curr > 0:
                        self._list.setCurrentRow(curr - 1)
                    return True
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    curr = self._list.currentRow()
                    if curr >= 0:
                        item = self._list.item(curr)
                        row = self._list.itemWidget(item)
                        if isinstance(row, MedicationOptionRow):
                            self._select_option(row.name)
                            return True
            if event.key() == Qt.Key.Key_Escape and self._drop_frame.isVisible():
                self._hide_dropdown()
                return True

        if search is not None and _obj == search and event.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.MouseButtonPress,
        }:
            QTimer.singleShot(0, lambda: self._show_options(self._filtered_options(search.text())))
            return False
        
        if event.type() == QEvent.Type.Wheel and self._drop_frame.isVisible():
            obj_widget = _obj if isinstance(_obj, QWidget) else None
            if obj_widget is not None and (
                obj_widget is self._list
                or obj_widget is self._list.viewport()
                or self._drop_frame.isAncestorOf(obj_widget)
            ):
                bar = self._list.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                return True
            self._hide_dropdown()
            return False
        
        if event.type() == QEvent.Type.ApplicationDeactivate:
            self._hide_dropdown()
            return False
            
        if _obj == self.window() and event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Hide,
            QEvent.Type.WindowStateChange,
            QEvent.Type.WindowDeactivate,
        }:
            self._hide_dropdown()
            return False
            
        if (event.type() == QEvent.Type.MouseButtonPress
                and self._drop_frame.isVisible()):
            click_pos = event.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(click_pos)
            drop_local = self._drop_frame.mapFromGlobal(click_pos)
            if not self.rect().contains(local_pos) and not self._drop_frame.rect().contains(drop_local):
                self._hide_dropdown()
        
        return super().eventFilter(_obj, event)

    def _hide_dropdown(self):
        self._drop_frame.hide()
        self._list.clear()

    # ── Item selected from list ───────────────────
    def _select_option(self, name: str):
        self._hide_dropdown()
        self._search.clear()
        self._add_tag(name)

    # ── + modal ───────────────────────────────────
    def _open_modal(self):
        self._hide_dropdown()
        dlg = MedAddModal(self, title="Add Medication", action_label="Add Medication")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.get_text().strip()
            if name:
                if not add_medication(name):
                    if hasattr(self.window(), "_show_toast"):
                        self.window()._show_toast("Already Exists", f'"{name}" is already in the medication list.', tone="warning")
                    return
                self._all_meds = load_medications()
                self._add_tag(name)
                self.med_added.emit(name)

    def _edit_option(self, old_name: str):
        dlg = MedAddModal(self, title="Edit Medication", action_label="Update", initial_value=old_name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name = dlg.get_text().strip()
            if new_name and new_name != old_name:
                if not update_medication(old_name, new_name):
                    if hasattr(self.window(), "_show_toast"):
                        self.window()._show_toast("Already Exists", f'"{new_name}" is already in the medication list.', tone="warning")
                    return
                self._all_meds = load_medications()
                if old_name in self._selected:
                    idx = self._selected.index(old_name)
                    self._selected[idx] = new_name
                    selected_now = list(self._selected)
                    self.clear_selection()
                    for med in selected_now:
                        self._add_tag(med)
                self.selection_changed.emit()
                self._show_options(self._filtered_options(self._search.text()))

    def _delete_option(self, name: str):
        dlg = ConfirmActionModal(
            "Delete Medication",
            f"Are you sure you want to delete medication '{name}'?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        delete_medication(name)
        self._all_meds = load_medications()
        if name in self._selected:
            self._remove_tag(name)
        self._show_options(self._filtered_options(self._search.text()))

        if hasattr(self.window(), "_show_toast"):
            self.window()._show_toast("Deleted Successfully", f"Medication '{name}' has been removed.")

    # ── Tag management ────────────────────────────
    def _add_tag(self, name: str):
        if not name or name in self._selected:
            return
        self._selected.append(name)
        tag = MedTag(name, self._tags_widget)
        tag.removed.connect(self._remove_tag)
        self._tags_layout.addWidget(tag)
        self._update_tags_visibility()
        self.selection_changed.emit()
        if self._drop_frame.isVisible():
            self._show_options(self._filtered_options(self._search.text()))

    def _remove_tag(self, name: str):
        if name in self._selected:
            self._selected.remove(name)
        for i in range(self._tags_layout.count()):
            w = self._tags_layout.itemAt(i)
            if w and isinstance(w.widget(), MedTag) and w.widget().name == name:
                w.widget().deleteLater()
                break
        self._update_tags_visibility()
        self.selection_changed.emit()
        if self._drop_frame.isVisible():
            self._show_options(self._filtered_options(self._search.text()))

    def select_med(self, name: str):
        """Public method to programmatically add a medication tag (e.g. when loading data)."""
        if name:
            self._add_tag(name)

    def get_medications(self) -> list:
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
        self._update_tags_visibility()

    def _update_tags_visibility(self):
        has_tags = bool(self._selected)
        # Keep _tags_scroll always visible so MedicationSelector height never changes
        # (hiding it causes the parent layout to reflow and shift other widgets)
        if not has_tags:
            self._tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._tags_widget.setMinimumSize(0, 0)
            return
        self._tags_layout.activate()
        viewport_width = max(240, self._tags_scroll.viewport().width())
        content_height = max(36, self._tags_layout.heightForWidth(viewport_width))
        self._tags_widget.setMinimumSize(viewport_width, content_height)
        self._tags_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if content_height > self._tags_scroll.viewport().height()
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._hide_dropdown()
