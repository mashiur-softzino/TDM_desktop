"""
Patient-related UI classes: results dialog, patient report dialog,
patient row widget, patients list card.
"""

from ui.ui_constants import (
    BG, CARD_BG, BLUE, BLUE_DARK, NAVY, LABEL_CLR, TEXT_CLR,
    BORDER, RED, GREEN, ORANGE,
)
from ui.ui_widgets import Card, StatBox, IconCircle, ToastMessage, make_shadow
from ui.ui_sampling import GradientCanvas

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QDialog, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import qtawesome as qta
from core.calculations import interpret_result


class ResultsDialog(QDialog):
    def __init__(self, parent=None, print_handler=None):
        super().__init__(parent)
        self.setWindowTitle("Generated Result")
        self._normal_size = (980, 700)
        self._normal_min_size = (920, 640)
        self._compact_size = (820, 460)
        self._compact_min_size = (760, 420)
        self.resize(*self._normal_size)
        self.setMinimumSize(*self._normal_min_size)
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
        content_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        from PyQt6.QtWidgets import QGridLayout
        self.results_card = Card("Pharmacokinetic Results", "mdi6.chart-box-outline", icon_color=BLUE)
        self.results_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._results_grid = QGridLayout()
        self._results_grid.setSpacing(14)
        self._results_grid.setContentsMargins(0, 0, 0, 0)

        self.stat_trough = StatBox(
            "Trough Concentration", unit="μg/mL",
            icon_name="mdi6.water-outline", icon_color="#7C3AED", icon_bg="#EDE9FE",
        )
        self.stat_c05 = StatBox(
            "0.5 hr Concentration", unit="μg/mL",
            icon_name="mdi6.clock-outline", icon_color="#0891B2", icon_bg="#CFFAFE",
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
        self.stat_lss = StatBox(
            "LSS AUC₀₋₁₂ (Estimated)", unit="mg·h/L",
            icon_name="mdi6.function-variant", icon_color="#7C3AED", icon_bg="#EDE9FE",
        )
        boxes = [
            self.stat_trough, self.stat_c05,   self.stat_clast,
            self.stat_auc,    self.stat_auc12, self.stat_interp,
            self.stat_lss,
        ]
        self._result_boxes = boxes
        for box in self._result_boxes:
            box.setParent(self.results_card)
            box.hide()
        self._layout_result_boxes("auc")
        self.results_card.body().addLayout(self._results_grid)

        # Show All Points toggle
        self._show_all_expanded = False
        self._show_all_btn = QPushButton("Show All Points  ▾")
        self._show_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #F0F4F8; color: {BLUE};
                border: 1px solid #D0DCF0; border-radius: 8px;
                font-size: 12px; font-weight: 600;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ background: #E8F0FE; }}
        """)
        self._show_all_btn.setFixedHeight(32)
        self._show_all_btn.hide()
        self._show_all_btn.clicked.connect(self._toggle_all_points)

        show_all_row = QHBoxLayout()
        show_all_row.addStretch()
        show_all_row.addWidget(self._show_all_btn)
        self.results_card.body().addLayout(show_all_row)

        # Collapsible all-points panel
        self._all_points_frame = QFrame()
        self._all_points_frame.setStyleSheet(f"""
            QFrame {{
                background: #F8FAFC;
                border: 1px solid #E8ECF0;
                border-radius: 12px;
            }}
        """)
        self._all_points_grid = QGridLayout(self._all_points_frame)
        self._all_points_grid.setSpacing(10)
        self._all_points_grid.setContentsMargins(12, 12, 12, 12)
        self._all_points_frame.hide()
        self.results_card.body().addWidget(self._all_points_frame)

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

        self.graph_card = Card("Concentration-Time Graph", "mdi6.chart-line", icon_color=BLUE)
        self.canvas = None
        content_lay.addWidget(self.graph_card)
        self.graph_card.hide()  # Hidden by default, shown when data is available
        content_lay.addStretch(1)

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

    def shutdown(self):
        try:
            if hasattr(self, "canvas") and self.canvas is not None:
                self.canvas.cleanup()
                self.canvas.deleteLater()
                self.canvas = None
        except Exception:
            pass

    def show_toast(self, title, body, tone="success"):
        self._position_toast()
        self._toast.show_message(title, body, tone=tone)

    def _toggle_all_points(self):
        self._show_all_expanded = not self._show_all_expanded
        self._all_points_frame.setVisible(self._show_all_expanded)
        self._show_all_btn.setText(
            "Hide Points  ▴" if self._show_all_expanded else "Show All Points  ▾"
        )

    def _layout_result_boxes(self, mode="auc"):
        for box in getattr(self, "_result_boxes", []):
            self._results_grid.removeWidget(box)
            box.setVisible(False)

        for col in range(3):
            self._results_grid.setColumnMinimumWidth(col, 0)
            self._results_grid.setColumnStretch(col, 0)
        for row in range(3):
            self._results_grid.setRowMinimumHeight(row, 0)
            self._results_grid.setRowStretch(row, 0)

        if mode == "lss":
            column_stretches = (1, 1, 1)
            positions = [
                (self.stat_trough, 0, 0),
                (self.stat_c05, 0, 1),
                (self.stat_clast, 0, 2),
                (self.stat_lss, 1, 0),
                (self.stat_interp, 1, 1),
            ]
        elif mode == "direct":
            column_stretches = (1, 1, 0)
            positions = [
                (self.stat_auc12, 0, 0),
                (self.stat_interp, 0, 1),
            ]
        else:
            column_stretches = (1, 1, 1)
            positions = [
                (self.stat_trough, 0, 0),
                (self.stat_c05, 0, 1),
                (self.stat_clast, 0, 2),
                (self.stat_auc, 1, 0),
                (self.stat_auc12, 1, 1),
                (self.stat_interp, 1, 2),
            ]
        for col, stretch in enumerate(column_stretches):
            self._results_grid.setColumnStretch(col, stretch)
        for box, row, col in positions:
            self._results_grid.addWidget(box, row, col)
            box.setVisible(True)
        self._results_grid.invalidate()

    def apply_results(self, pk, interp, times=None, concs=None):
        def fmt_hour(v):
            return f"{int(v)}" if float(v).is_integer() else f"{v:.1f}"

        def fmt(v, d=3):
            return f"{v:.{d}f}" if v is not None else "N/A"

        direct_auc = not (times or concs)
        is_lss = (
            not direct_auc
            and pk.get('auc_lss') is not None
            and not str(pk.get('lss_equation', '')).lower().startswith('direct input')
        )
        result_mode = "direct" if direct_auc else ("lss" if is_lss else "auc")

        last_hr = fmt_hour(pk['t_last'])
        self.stat_trough.set_label("Trough Concentration")
        self.stat_trough.set_unit("μg/mL")
        self.stat_trough.set_value(fmt(pk['c_trough'], 2))

        first_post = next(((t, c) for t, c in zip(times or [], concs or []) if t > 0), None)
        if first_post is not None:
            first_time, first_conc = first_post
            self.stat_c05.set_label(f"{fmt_hour(first_time)} hr Concentration")
            self.stat_c05.set_unit("μg/mL")
            self.stat_c05.set_value(fmt(first_conc, 2))
            self.stat_c05.setVisible(True)
        else:
            self.stat_c05.setVisible(False)

        # Build "Show All" panel for post-dose points
        post = [(t, c) for t, c in zip(times or [], concs or []) if t > 0]
        while self._all_points_grid.count():
            item = self._all_points_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if len(post) > 2:
            self._show_all_btn.show()
            cols = 4
            for i, (t, c) in enumerate(post):
                tile = QFrame()
                tile.setStyleSheet(f"""
                    QFrame {{
                        background: white;
                        border: 1.5px solid #E8ECF0;
                        border-radius: 12px;
                    }}
                """)
                tile.setGraphicsEffect(make_shadow(8, 2, 12))
                tile_lay = QVBoxLayout(tile)
                tile_lay.setContentsMargins(12, 10, 12, 10)
                tile_lay.setSpacing(4)

                time_lbl = QLabel(f"{fmt_hour(t)} hr")
                time_lbl.setStyleSheet(
                    f"color: {BLUE}; font-size: 11px; font-weight: 700; "
                    "background: transparent; border: none; padding: 0;"
                )
                conc_lbl = QLabel(fmt(c, 2))
                conc_lbl.setStyleSheet(
                    f"color: {TEXT_CLR}; font-size: 18px; font-weight: 700; "
                    "background: transparent; border: none; padding: 0;"
                )
                unit_lbl = QLabel("μg/mL")
                unit_lbl.setStyleSheet(
                    "color: #9E9E9E; font-size: 10px; background: transparent; "
                    "border: none; padding: 0;"
                )

                tile_lay.addWidget(time_lbl)
                tile_lay.addWidget(conc_lbl)
                tile_lay.addWidget(unit_lbl)
                self._all_points_grid.addWidget(tile, i // cols, i % cols)
        else:
            self._show_all_btn.hide()
            self._all_points_frame.hide()
            self._show_all_expanded = False

        self.stat_clast.set_label("2 hr Concentration" if is_lss else f"{last_hr} hr Concentration")
        self.stat_clast.set_unit("μg/mL")
        self.stat_clast.set_value(fmt(pk['c_last'], 2))
        self.stat_auc.set_label(f"AUC (0 → {last_hr} hr)")
        self.stat_auc.set_unit("Observed exposure  •  mg·h/L")
        self.stat_auc.set_value(fmt(pk['auc_0_last'], 3))
        if direct_auc:
            self.stat_auc12.set_label("MPA AUC 0-12")
        else:
            self.stat_auc12.set_label(f"{last_hr} hour extrapolated to 12 hr MPA AUC")
        self.stat_auc12.set_unit("mg·h/L")
        self.stat_auc12.set_value(fmt(pk['auc_0_12'], 3))

        self.stat_auc12.set_warning(None)

        _, rng = interpret_result('MPA', pk['auc_0_12'])
        interp_color = {'Low': RED, 'High': RED, 'Therapeutic': GREEN}.get(interp, TEXT_CLR)
        self.stat_interp.set_label("Interpretation")
        self.stat_interp.set_unit(f"Therapeutic range: {rng[0]}–{rng[1]} mg·h/L")
        self.stat_interp.set_value(interp, color=interp_color)

        if is_lss:
            lss_val = pk['auc_lss']
            self.stat_lss.set_value(fmt(lss_val, 3))
            self.stat_lss.set_unit(pk.get('lss_equation', 'LSS estimate') + "  •  mg·h/L")

            self.stat_lss.set_warning(None)
        self._layout_result_boxes(result_mode)

    def plot_data(self, times, concs, drug='MPA'):
        if self.canvas is None:
            self.canvas = GradientCanvas(self.graph_card)
            self.graph_card.body().addWidget(self.canvas)
        self.canvas.plot(times, concs, drug=drug)

    def set_graph_visible(self, visible: bool):
        """Show or hide the graph card (hidden for Direct AUC / single-value mode)."""
        self.graph_card.setVisible(visible)
        if visible:
            self.setMinimumSize(*self._normal_min_size)
            if self.width() < self._normal_size[0] or self.height() < self._normal_size[1]:
                self.resize(*self._normal_size)
        else:
            self.setMinimumSize(*self._compact_min_size)
            self.resize(*self._compact_size)


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

        from reports.report_print import build_report_widget
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
    edit_requested = pyqtSignal(int)
    view_requested = pyqtSignal(int)
    print_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, snapshot: dict, row_type: str = 'sample', serial_no: int | None = None, parent=None):
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

        text_cell(str(serial_no or ""), stretch=1, alignment=Qt.AlignmentFlag.AlignCenter)
        if row_type == 'sample':
            text_cell(snapshot.get('patient', {}).get('pid', 'N/A'), stretch=4)
        text_cell(snapshot.get('patient', {}).get('name', 'N/A'), stretch=4)
        text_cell(snapshot.get('patient', {}).get('phone', 'N/A'), stretch=3)

        drug = QLabel(snapshot.get('patient', {}).get('drug', 'N/A'))
        drug.setObjectName("drugBadge")
        drug.setStyleSheet("border: none;")
        drug.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(drug, 2)

        collection_date = snapshot.get('patient', {}).get('sample_collection_date') or "N/A"
        text_cell(collection_date, stretch=3, object_name="dateText")

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
    page_changed = pyqtSignal()

    def __init__(self, title="Sample List", empty_text="No saved samples yet.", action_width=150, parent=None, row_type='sample'):
        super().__init__(title, "mdi6.format-list-bulleted-square", icon_color=BLUE, parent=parent)
        self.setGraphicsEffect(None)
        self._action_width = action_width
        self._row_type = row_type
        self._page_index = 0
        badge_bg = "#16A34A" if row_type == 'sample' else "#FBBF24"
        badge_border = "#DCFCE7" if row_type == 'sample' else "#FFF7E8"
        self._count_badge = QLabel("0")
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setFixedSize(24, 22)
        self._count_badge.setStyleSheet(
            f"background: {badge_bg}; color: white; border: 2px solid {badge_border}; "
            "border-radius: 11px; font-size: 11px; font-weight: bold;"
        )
        if self._header_lay is not None:
            self._header_lay.insertWidget(max(0, self._header_lay.count() - 1), self._count_badge)

        # ── Search bar (in header, right side) ──────────
        self._search_edit = QLineEdit()
        placeholder = "Search by name or phone number" if self._row_type == 'draft' else "Search by name or patient ID"
        self._search_edit.setPlaceholderText(placeholder)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 12px;
                color: {TEXT_CLR};
            }}
        """)
        self._search_edit.textChanged.connect(self._on_search_text_changed)

        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi6.magnify", color="#9BB0C8").pixmap(14, 14))
        search_icon.setStyleSheet("background: transparent;")

        self._clear_search_btn = QPushButton()
        self._clear_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_search_btn.setFixedSize(18, 18)
        self._clear_search_btn.setIcon(qta.icon("mdi6.close-circle", color="#94A3B8"))
        self._clear_search_btn.setIconSize(self._clear_search_btn.size() * 0.9)
        self._clear_search_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 9px; }
            QPushButton:hover { background: #E2E8F0; }
        """)
        self._clear_search_btn.clicked.connect(self.clear_search)
        self._clear_search_btn.hide()

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
        sw_lay.addWidget(self._clear_search_btn)

        if self._header_lay is not None:
            self._header_lay.addWidget(search_wrap)

        self._empty_text = empty_text
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
            ("SL NO", 1, Qt.AlignmentFlag.AlignCenter),
            ("NAME", 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("PHONE", 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("DRUG", 2, Qt.AlignmentFlag.AlignCenter),
            ("COLLECTION DATE", 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("ACTIONS", 0, Qt.AlignmentFlag.AlignCenter),
        ]
        if self._row_type == 'sample':
            header_columns.insert(1, ("PATIENT ID", 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
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

        self._pagination = QFrame()
        self._pagination.setObjectName("pagination")
        self._pagination.setStyleSheet(f"""
            QFrame#pagination {{
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
            }}
            QLabel#pageInfo {{
                color: {LABEL_CLR};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        self._pagination_lay = QHBoxLayout(self._pagination)
        self._pagination_lay.setContentsMargins(12, 8, 12, 8)
        self._pagination_lay.setSpacing(8)
        self._table_lay.addWidget(self._pagination)

        self.body().addWidget(self._empty)
        self.body().addWidget(self._table)

    def search_text(self) -> str:
        return self._search_edit.text().strip().lower()

    def _on_search_text_changed(self, text: str):
        self._page_index = 0
        self._clear_search_btn.setVisible(bool(text.strip()))
        self.search_changed.emit(text)

    def clear_search(self):
        self._search_edit.clear()

    def page_index(self) -> int:
        return self._page_index

    def set_page_index(self, page_index: int):
        self._page_index = max(0, page_index)
        self.page_changed.emit()

    def clamp_page_index(self, page_count: int):
        max_index = max(0, page_count - 1)
        if self._page_index > max_index:
            self._page_index = max_index

    def set_pagination(self, page_index: int, page_count: int, total_count: int, page_size: int):
        while self._pagination_lay.count():
            item = self._pagination_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if page_count <= 1:
            self._pagination.hide()
            return

        self._pagination.show()
        first_item = page_index * page_size + 1
        last_item = min(total_count, first_item + page_size - 1)
        info = QLabel(f"{first_item}-{last_item} of {total_count}")
        info.setObjectName("pageInfo")
        self._pagination_lay.addWidget(info)
        self._pagination_lay.addStretch()

        def make_btn(label, target=None, active=False, enabled=True, icon_name=None):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled and not active else Qt.CursorShape.ArrowCursor)
            btn.setEnabled(enabled)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(32)
            if icon_name:
                btn.setIcon(qta.icon(icon_name, color="#64748B" if enabled else "#CBD5E1"))
            if active:
                style = f"background: {BLUE}; color: white; border: 1px solid {BLUE};"
            else:
                style = "background: #F8FAFC; color: #334155; border: 1px solid #D8E2EF;"
            btn.setStyleSheet(f"""
                QPushButton {{
                    {style}
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    background: #E8F0FE;
                    color: {BLUE};
                    border: 1px solid #BBD3FF;
                }}
                QPushButton:disabled {{
                    background: #F1F5F9;
                    color: #94A3B8;
                    border: 1px solid #E2E8F0;
                }}
            """)
            if target is not None and not active:
                btn.clicked.connect(lambda: self.set_page_index(target))
            return btn

        self._pagination_lay.addWidget(make_btn("", page_index - 1, enabled=page_index > 0, icon_name="mdi6.chevron-left"))

        pages = []
        if page_count <= 5:
            pages = list(range(page_count))
        else:
            start = max(0, min(page_index - 2, page_count - 5))
            pages = list(range(start, start + 5))
        for page in pages:
            self._pagination_lay.addWidget(make_btn(str(page + 1), page, active=(page == page_index)))

        self._pagination_lay.addWidget(make_btn("", page_index + 1, enabled=page_index < page_count - 1, icon_name="mdi6.chevron-right"))

    def set_count(self, count: int):
        self._count_badge.setText(str(count))

    def set_empty_text(self, text: str | None = None):
        self._empty.setText(text or self._empty_text)

    def set_empty_visible(self, visible: bool):
        self._empty.setVisible(visible)
        self._table.setVisible(not visible)
        if visible:
            self._pagination.hide()

class SignatoryRow(QFrame):
    edit_requested = pyqtSignal(dict)
    status_changed = pyqtSignal(dict, bool)

    def __init__(self, signatory, serial_no=1):
        super().__init__()
        self.signatory = signatory
        self.setFixedHeight(68)
        self.setObjectName("doctorRow")
        
        accent   = "#8B5CF6" if signatory.get('type') == 'doctor' else "#0D9488" # Purple for Doctor, Teal for Tech
        bg       = "#FBFBFF" if signatory.get('type') == 'doctor' else "#F0FDFA"
        bg_hover = "#F5F3FF" if signatory.get('type') == 'doctor' else "#CCFBF1"
        border   = "#DDD6FE" if signatory.get('type') == 'doctor' else "#99F6E4"

        self.setStyleSheet(f"""
            QFrame#doctorRow {{
                background: {bg};
                border: 1px solid {border};
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            QFrame#doctorRow:hover {{
                background: {bg_hover};
                border: 1px solid {border};
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(10)

        # SL NO
        sl = QLabel(str(serial_no))
        sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(sl, 1, Qt.AlignmentFlag.AlignCenter)

        # Name & Type
        name_wrap = QWidget()
        name_wrap.setStyleSheet("background: transparent; border: none;")
        name_lay = QVBoxLayout(name_wrap)
        name_lay.setContentsMargins(0, 0, 0, 0)
        name_lay.setSpacing(2)
        
        name_lbl = QLabel(signatory.get('name', 'N/A'))
        name_lbl.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13.5px; font-weight: 700; background: transparent; border: none;")
        name_lay.addWidget(name_lbl)
        
        type_str = signatory.get('type', 'doctor').upper()
        type_badge = QLabel(type_str)
        type_badge.setFixedWidth(90)
        type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_badge.setStyleSheet(f"""
            background: {"#EDE9FE" if type_str == 'DOCTOR' else "#CCFBF1"}; 
            color: {"#6D28D9" if type_str == 'DOCTOR' else "#0F766E"}; 
            border-radius: 6px; font-size: 9px; font-weight: 800; padding: 2px 4px;
        """)
        name_lay.addWidget(type_badge)
        lay.addWidget(name_wrap, 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Phone
        phone = (signatory.get('phone') or '').strip()
        phone_lbl = QLabel(phone if phone else "N/A")
        phone_lbl.setStyleSheet(f"color: {BLUE if phone else '#94A3B8'}; font-size: 13px; font-weight: 600; background: transparent; border: none;")
        lay.addWidget(phone_lbl, 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Status
        is_active = signatory.get('is_active', True) is not False
        status_btn = QPushButton("Active" if is_active else "Inactive")
        status_btn.setCheckable(True)
        status_btn.setChecked(is_active)
        status_btn.setFixedSize(86, 32)
        status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        status_btn.setStyleSheet("""
            QPushButton {
                background: #FEE2E2;
                color: #B91C1C;
                border: 1px solid #FCA5A5;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 800;
            }
            QPushButton:checked {
                background: #DCFCE7;
                color: #15803D;
                border: 1px solid #86EFAC;
            }
            QPushButton:hover {
                border-color: #64748B;
            }
        """)

        def on_status_toggled(checked):
            status_btn.setText("Active" if checked else "Inactive")
            self.status_changed.emit(signatory, checked)

        status_btn.toggled.connect(on_status_toggled)
        lay.addWidget(status_btn, 0, Qt.AlignmentFlag.AlignCenter)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def make_act_btn(icon_name, color, bg, hover_bg, cb):
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(qta.icon(icon_name, color=color))
            btn.setStyleSheet(f"""
                QPushButton {{ background: {bg}; border: none; border-radius: 12px; }}
                QPushButton:hover {{ background: {hover_bg}; }}
            """)
            btn.clicked.connect(cb)
            return btn

        actions.addWidget(make_act_btn("mdi6.pencil-outline", BLUE, "#EFF6FF", "#DBEAFE", lambda: self.edit_requested.emit(signatory)))
        
        actions_widget = QWidget()
        actions_widget.setFixedWidth(64)
        actions_widget.setStyleSheet("background: transparent; border: none;")
        actions_widget_lay = QHBoxLayout(actions_widget)
        actions_widget_lay.setContentsMargins(0, 0, 0, 0)
        actions_widget_lay.addLayout(actions)
        lay.addWidget(actions_widget, 0, Qt.AlignmentFlag.AlignCenter)


class SignatoriesListCard(Card):
    search_changed = pyqtSignal(str)
    page_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__("Signatory List", "mdi6.account-group-outline", icon_color="#7C3AED", parent=parent)
        self._page_index = 0
        self.setGraphicsEffect(None)
        
        self._count_badge = QLabel("0")
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setFixedSize(24, 22)
        self._count_badge.setStyleSheet(
            "background: #8B5CF6; color: white; border: 2px solid #F5F3FF; "
            "border-radius: 11px; font-size: 11px; font-weight: bold;"
        )
        if self._header_lay is not None:
            # Insert after icon and title (index 2) but before stretch
            self._header_lay.insertWidget(2, self._count_badge)

        self._empty_text = "No signatories found."
        self._empty = QLabel(self._empty_text)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._empty.setStyleSheet(
            f"font-size: 13px; color: {LABEL_CLR}; background: #F8FBFF; "
            f"border: 1px dashed #D9E6F2; border-radius: 16px; padding: 20px 28px;"
        )

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by name or phone number")
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 12px;
                color: {TEXT_CLR};
            }}
        """)
        self._search_edit.textChanged.connect(self.search_changed.emit)

        search_wrap = QFrame()
        search_wrap.setFixedWidth(220)
        search_wrap.setFixedHeight(32)
        search_wrap.setObjectName("searchWrapListDoctor")
        search_wrap.setStyleSheet(f"""
            QFrame#searchWrapListDoctor {{
                background: #F4F8FC;
                border: 1.5px solid {BORDER};
                border-radius: 8px;
            }}
            QFrame#searchWrapListDoctor:focus-within {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
        """)
        sw_lay = QHBoxLayout(search_wrap)
        sw_lay.setContentsMargins(8, 4, 8, 4)
        sw_lay.setSpacing(6)
        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi6.magnify", color="#9BB0C8").pixmap(14, 14))
        sw_lay.addWidget(search_icon)
        sw_lay.addWidget(self._search_edit)
        if self._header_lay is not None:
            self._header_lay.addWidget(search_wrap)

        self._add_btn = QPushButton("Add New Signatory")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet("""
            QPushButton {
                background: #8B5CF6; color: white; border: none; border-radius: 8px;
                padding: 6px 14px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #7C3AED; }
        """)
        if self._header_lay is not None:
            self._header_lay.addSpacing(10)
            self._header_lay.addWidget(self._add_btn)

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
            ("SL NO", 1, Qt.AlignmentFlag.AlignCenter),
            ("NAME & TYPE", 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("PHONE", 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            ("STATUS", 0, Qt.AlignmentFlag.AlignCenter),
            ("ACTIONS", 0, Qt.AlignmentFlag.AlignCenter),
        ]
        for text, stretch, alignment in header_columns:
            lbl = QLabel(text)
            lbl.setAlignment(alignment)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #6B7C93; "
                "letter-spacing: 1.1px; background: transparent;"
            )
            if text in ("STATUS", "ACTIONS"):
                lbl.setFixedWidth(86 if text == "STATUS" else 64)
                hdr_lay.addWidget(lbl, 0, alignment)
            else:
                hdr_lay.addWidget(lbl, stretch)
        self._table_lay.addWidget(hdr)

        self._rows_host = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(6)
        self._table_lay.addWidget(self._rows_host)

        self._pagination = QFrame()
        self._pagination.setObjectName("paginationDoc")
        self._pagination.setStyleSheet(f"""
            QFrame#paginationDoc {{
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
            }}
            QLabel#pageInfoDoc {{
                color: {LABEL_CLR};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        self._pagination_lay = QHBoxLayout(self._pagination)
        self._pagination_lay.setContentsMargins(12, 8, 12, 8)
        self._pagination_lay.setSpacing(8)
        self._table_lay.addWidget(self._pagination)
        self._table_lay.addStretch()

        self.body().addWidget(self._empty)
        self.body().addWidget(self._table)

    def search_text(self):
        return self._search_edit.text().strip().lower()

    def page_index(self) -> int:
        return self._page_index

    def set_page_index(self, page_index: int):
        self._page_index = max(0, page_index)
        self.page_changed.emit()

    def clamp_page_index(self, page_count: int):
        max_index = max(0, page_count - 1)
        if self._page_index > max_index:
            self._page_index = max_index

    def set_pagination(self, page_index: int, page_count: int, total_count: int, page_size: int):
        while self._pagination_lay.count():
            item = self._pagination_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if page_count <= 1:
            self._pagination.hide()
            return

        self._pagination.show()
        first_item = page_index * page_size + 1
        last_item = min(total_count, first_item + page_size - 1)
        info = QLabel(f"{first_item}-{last_item} of {total_count}")
        info.setObjectName("pageInfoDoc")
        self._pagination_lay.addWidget(info)
        self._pagination_lay.addStretch()

        def make_btn(label, target=None, active=False, enabled=True, icon_name=None):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled and not active else Qt.CursorShape.ArrowCursor)
            btn.setEnabled(enabled)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(32)
            if icon_name:
                btn.setIcon(qta.icon(icon_name, color="#64748B" if enabled else "#CBD5E1"))
            if active:
                style = f"background: {BLUE}; color: white; border: 1px solid {BLUE};"
            else:
                style = "background: #F8FAFC; color: #334155; border: 1px solid #D8E2EF;"
            btn.setStyleSheet(f"""
                QPushButton {{
                    {style}
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    background: #E8F0FE;
                    color: {BLUE};
                    border: 1px solid #BBD3FF;
                }}
                QPushButton:disabled {{
                    background: #F1F5F9;
                    color: #94A3B8;
                    border: 1px solid #E2E8F0;
                }}
            """)
            if target is not None and not active:
                btn.clicked.connect(lambda: self.set_page_index(target))
            return btn

        self._pagination_lay.addWidget(make_btn("", page_index - 1, enabled=page_index > 0, icon_name="mdi6.chevron-left"))

        pages = []
        if page_count <= 5:
            pages = list(range(page_count))
        else:
            start = max(0, min(page_index - 2, page_count - 5))
            pages = list(range(start, start + 5))
        for page in pages:
            self._pagination_lay.addWidget(make_btn(str(page + 1), page, active=(page == page_index)))

        self._pagination_lay.addWidget(make_btn("", page_index + 1, enabled=page_index < page_count - 1, icon_name="mdi6.chevron-right"))

    def set_count(self, count):
        self._count_badge.setText(str(count))

    def set_empty_text(self, text=None):
        self._empty.setText(text or self._empty_text)

    def set_empty_visible(self, visible):
        self._empty.setVisible(visible)
        self._table.setVisible(not visible)
        if visible:
            self._pagination.hide()

    def clear_rows(self):
        while self._rows_lay.count():
            item = self._rows_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def add_row(self, row_widget):
        self._rows_lay.addWidget(row_widget)
