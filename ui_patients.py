"""
Patient-related UI classes: results dialog, patient report dialog,
patient row widget, patients list card.
"""

from ui_constants import (
    BG, CARD_BG, BLUE, BLUE_DARK, NAVY, LABEL_CLR, TEXT_CLR,
    BORDER, RED, GREEN, ORANGE,
)
from ui_widgets import Card, StatBox, IconCircle, ToastMessage, make_shadow
from ui_sampling import GradientCanvas

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QDialog, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import qtawesome as qta
from calculations import interpret_result


class ResultsDialog(QDialog):
    def __init__(self, parent=None, print_handler=None):
        super().__init__(parent)
        self.setWindowTitle("Generated Result")
        self.resize(980, 700)
        self.setMinimumSize(920, 640)
        self.setModal(False)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")
        self._print_handler = print_handler
        self._center_on_show = True

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

        from PyQt6.QtWidgets import QGridLayout
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
        self.stat_lss = StatBox(
            "LSS AUC₀₋₁₂ (Estimated)", unit="mg·h/L",
            icon_name="mdi6.function-variant", icon_color="#7C3AED", icon_bg="#EDE9FE",
        )
        boxes = [
            self.stat_trough, self.stat_clast, self.stat_auc,
            self.stat_auc12, self.stat_interp, self.stat_thalf,
            self.stat_lss,
        ]
        for i, box in enumerate(boxes):
            grid.addWidget(box, i // 3, i % 3)
        self.results_card.body().addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.print_btn = QPushButton("Print / Export PDF")
        self.print_btn.setObjectName("printBtn")
        self.print_btn.setAutoDefault(False)
        self.print_btn.setDefault(False)
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
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        lay.addLayout(close_row)

        self._toast = ToastMessage(self)
        self._position_toast()

    def _on_print(self):
        if self._print_handler is not None:
            self._print_handler()
        self.close()

    def showEvent(self, event):
        super().showEvent(event)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            target_width = min(self.width(), max(920, available.width() - 80))
            target_height = min(self.height(), max(640, available.height() - 100))
            self.resize(target_width, target_height)
            if self._center_on_show:
                self._center_on_show = False
                frame = self.frameGeometry()
                frame.moveCenter(available.center())
                self.move(frame.topLeft())
        self._position_toast()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def _position_toast(self):
        if not hasattr(self, '_toast'):
            return
        width = min(360, max(280, self.width() - 56))
        self._toast.setFixedWidth(width)
        self._toast.move(self.width() - width - 24, 20)

    def show_toast(self, title, body, tone="success"):
        self._position_toast()
        self._toast.show_message(title, body, tone=tone)

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

        # Extrapolation % warning (>20% = unreliable per FDA standard)
        auc_last = pk.get('auc_0_last', 0)
        auc_12 = pk.get('auc_0_12', 0)
        if auc_12 and auc_12 > 0:
            extrap_pct = (auc_12 - auc_last) / auc_12 * 100
            if extrap_pct > 20:
                self.stat_auc12.set_warning(
                    f"⚠ Extrapolation {extrap_pct:.0f}% of total AUC (>20% — result may be unreliable)"
                )
            else:
                self.stat_auc12.set_warning(None)
        else:
            self.stat_auc12.set_warning(None)

        self.stat_thalf.set_label("Terminal  t½")
        self.stat_thalf.set_unit("hours")
        self.stat_thalf.set_value(fmt(pk['t_half'], 2) if pk['t_half'] else 'N/A')
        _, rng = interpret_result('MPA', pk['auc_0_12'])
        interp_color = {'Low': RED, 'High': RED, 'Therapeutic': GREEN}.get(interp, TEXT_CLR)
        self.stat_interp.set_label("Interpretation")
        self.stat_interp.set_unit(f"Therapeutic range: {rng[0]}–{rng[1]} mg·h/L")
        self.stat_interp.set_value(interp, color=interp_color)

        if pk.get('auc_lss') is not None:
            lss_val = pk['auc_lss']
            self.stat_lss.set_value(fmt(lss_val, 3))
            self.stat_lss.set_unit(pk.get('lss_equation', 'LSS estimate') + "  •  mg·h/L")
            self.stat_lss.setVisible(True)

            # LSS vs AUC₀₋₁₂ sanity check — >50% difference = unreliable
            if auc_12 and auc_12 > 0:
                lss_diff_pct = abs(lss_val - auc_12) / auc_12 * 100
                if lss_diff_pct > 50:
                    self.stat_lss.set_value(fmt(lss_val, 3), color=ORANGE)
                    self.stat_lss.set_warning(
                        f"⚠ LSS differs {lss_diff_pct:.0f}% from AUC₀₋₁₂ — result may be unreliable"
                    )
                else:
                    self.stat_lss.set_warning(None)
        else:
            self.stat_lss.setVisible(False)

    def plot_data(self, times, concs, drug='MPA'):
        self.canvas.plot(times, concs, drug=drug)


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
    view_requested = pyqtSignal(str)
    print_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, snapshot: dict, row_type: str = 'sample', parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.setObjectName("patientRow")

        if row_type == 'draft':
            accent   = "#FBBF24"
            bg       = "#FFFDF9"
            bg_hover = "#FFF7E7"
            border   = "#FDECC8"
            badge_bg = "#FFF7E8"
            badge_fg = "#B45309"
        else:
            accent   = "#22C55E"
            bg       = "#F7FFFB"
            bg_hover = "#DDFBEA"
            border   = "#CCF2DE"
            badge_bg = "#EAF2FF"
            badge_fg = BLUE

        self.setStyleSheet(f"""
            QFrame#patientRow {{
                background: {bg};
                border: 1px solid {border};
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            QFrame#patientRow:hover {{
                background: {bg_hover};
                border: 1px solid {border};
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            QLabel#cellValue {{
                font-size: 13px;
                color: {TEXT_CLR};
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#drugBadge {{
                background: {badge_bg};
                color: {badge_fg};
                border-radius: 12px;
                border: none;
                padding: 5px 12px;
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
        row.setContentsMargins(18, 10, 18, 10)
        row.setSpacing(12)

        def text_cell(text, stretch=2, object_name="cellValue", alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setStyleSheet("background: transparent; border: none;")
            lbl.setAlignment(alignment)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl, stretch)

        text_cell(snapshot.get('patient', {}).get('name', 'N/A'), stretch=3)
        if row_type == 'sample':
            text_cell(snapshot.get('patient', {}).get('pid', 'N/A'), stretch=3)

        drug = QLabel(snapshot.get('patient', {}).get('drug', 'N/A'))
        drug.setObjectName("drugBadge")
        drug.setStyleSheet("border: none;")
        drug.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(drug, 2)

        text_cell(snapshot.get('patient', {}).get('dose', 'N/A'), stretch=3)
        text_cell(snapshot.get('saved_at', 'N/A'), stretch=2, object_name="dateText")

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)

        def make_action_button(icon_name, icon_color, tooltip, bg, hover_bg):
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(qta.icon(icon_name, color=icon_color))
            btn.setToolTip(tooltip)
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(
                f"QPushButton {{ background: {bg}; border: none; border-radius: 15px; }}"
                f"QPushButton:hover {{ background: {hover_bg}; }}"
            )
            return btn

        if row_type == 'sample':
            view_btn = make_action_button("mdi6.eye-outline", BLUE, "View generated result", "#EEF5FF", "#DCEBFF")
            view_btn.clicked.connect(lambda: self.view_requested.emit(snapshot['id']))
            actions.addWidget(view_btn)

            print_btn = make_action_button("mdi6.printer-outline", "#0F766E", "Open browser print preview", "#ECFDF5", "#D1FAE5")
            print_btn.clicked.connect(lambda: self.print_requested.emit(snapshot['id']))
            actions.addWidget(print_btn)

        edit_btn = make_action_button("mdi6.pencil-outline", BLUE, "Open sample in editor", "#EEF5FF", "#DCEBFF")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(snapshot['id']))
        actions.addWidget(edit_btn)

        delete_btn = make_action_button("mdi6.trash-can-outline", RED, "Delete patient", "#FFF1F2", "#FFE1E5")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(snapshot['id']))
        actions.addWidget(delete_btn)

        actions_wrap = QWidget()
        actions_wrap.setObjectName("actionsWrap")
        actions_wrap.setLayout(actions)
        actions_wrap.setFixedWidth(150 if row_type == 'sample' else 84)
        row.addWidget(actions_wrap, 0, Qt.AlignmentFlag.AlignCenter)


class PatientsListCard(Card):
    search_changed = pyqtSignal(str)

    def __init__(self, title="Sample List", empty_text="No saved samples yet.", action_width=150, parent=None, row_type='sample'):
        super().__init__(title, "mdi6.format-list-bulleted-square", icon_color=BLUE, parent=parent)
        self.setGraphicsEffect(None)
        self._action_width = action_width
        self._row_type = row_type

        # ── Search bar (in header, right side) ──────────
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search...")
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 12px;
                color: {TEXT_CLR};
            }}
        """)
        self._search_edit.textChanged.connect(self.search_changed)

        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi6.magnify", color="#9BB0C8").pixmap(14, 14))
        search_icon.setStyleSheet("background: transparent;")

        search_wrap = QFrame()
        search_wrap.setFixedWidth(220)
        search_wrap.setFixedHeight(32)
        search_wrap.setObjectName("searchWrapList")
        search_wrap.setStyleSheet(f"""
            QFrame#searchWrapList {{
                background: #F4F8FC;
                border: 1.5px solid {BORDER};
                border-radius: 8px;
            }}
            QFrame#searchWrapList:focus-within {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
        """)
        sw_lay = QHBoxLayout(search_wrap)
        sw_lay.setContentsMargins(8, 4, 8, 4)
        sw_lay.setSpacing(6)
        sw_lay.addWidget(search_icon)
        sw_lay.addWidget(self._search_edit)

        if self._header_lay is not None:
            self._header_lay.addWidget(search_wrap)

        self._empty = QLabel(empty_text)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._empty.setStyleSheet(
            f"font-size: 13px; color: {LABEL_CLR}; background: #F8FBFF; "
            f"border: 1px dashed #D9E6F2; border-radius: 16px; padding: 20px 28px;"
        )

        self._table = QFrame()
        self._table.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F9FBFF, stop:1 #F3F8FE); "
            f"border: none; border-radius: 24px;"
        )
        self._table_lay = QVBoxLayout(self._table)
        self._table_lay.setContentsMargins(12, 12, 12, 12)
        self._table_lay.setSpacing(10)

        hdr = QFrame()
        hdr.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EEF4FB, stop:1 #F6F9FD); "
            "border: none; border-radius: 18px;"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 14)
        hdr_lay.setSpacing(10)
        header_columns = [
            ("NAME", 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("DRUG", 2, Qt.AlignmentFlag.AlignCenter),
            ("DOSE", 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("DATE", 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("ACTIONS", 0, Qt.AlignmentFlag.AlignCenter),
        ]
        if self._row_type == 'sample':
            header_columns.insert(1, ("PATIENT ID", 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        for text, stretch, alignment in header_columns:
            lbl = QLabel(text)
            lbl.setAlignment(alignment)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #6B7C93; "
                "letter-spacing: 1.1px; background: transparent;"
            )
            if text == "ACTIONS":
                lbl.setFixedWidth(self._action_width)
                hdr_lay.addWidget(lbl, 0, alignment)
            else:
                hdr_lay.addWidget(lbl, stretch)
        self._table_lay.addWidget(hdr)

        self._rows_host = QWidget()
        self._rows_host.setStyleSheet("background: transparent;")
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(2)
        self._table_lay.addWidget(self._rows_host)

        self.body().addWidget(self._empty)
        self.body().addWidget(self._table)

    def search_text(self) -> str:
        return self._search_edit.text().strip().lower()

    def set_empty_visible(self, visible: bool):
        self._empty.setVisible(visible)
        self._table.setVisible(not visible)
