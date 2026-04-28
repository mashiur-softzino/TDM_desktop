"""
TDM Report — Therapeutic Drug Monitoring
Main window only. All helper classes/constants are in ui_constants, ui_widgets,
ui_sampling, and ui_patients.
"""

import sys
import json  # kept for report_print compatibility
from app_logger import (
    log_report_generated, log_draft_saved,
    log_record_loaded, log_record_deleted, log_report_printed, log_error,
)
from database import (
    init_db, save_record, delete_record, load_all, migrate_from_json,
    load_duration_options, save_duration_options, load_medications,
    add_medication, update_medication, delete_medication,
)
import tempfile
import webbrowser
import base64
from io import BytesIO
from datetime import datetime
from pathlib import Path

from ui_constants import (BG, CARD_BG, BLUE, BLUE_DARK, NAVY, LABEL_CLR, TEXT_CLR,
                           BORDER, RED, GREEN, ORANGE, DEFAULT_DURATION_OPTIONS,
                           BASE_SAMPLE_TIMES, PATIENTS_FILE, STYLE,
                           sampling_times_for_duration, make_shadow, small_label, value_label)
from ui_widgets import (Card, ToggleButton, DurationEditModal, DurationChip,
                        NoWheelComboBox, SmartDateEdit, SmartDateTimeEdit,
                        MonthOnlyCalendar, IconCircle, StatBox, ToastMessage)
from ui_sampling import (ROW_COLORS, DEFAULT_MEDICATIONS, SampleRow, ModernSampleTable,
                         GradientCanvas, MedTag, MedAddModal, MedicationOptionRow,
                         MedicationEmptyRow, MedicationListWidget, MedicationSelector,
                         DrugSelector)
from ui_patients import ResultsDialog, PatientReportDialog, PatientRow, PatientsListCard

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
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QDate, QDateTime, QObject, QEvent, QSize, QRegularExpression, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush, QPen, QPalette, QIntValidator, QRegularExpressionValidator, QPixmap, QImage
import qtawesome as qta
from calculations import calculate_auc_full, calculate_lss_auc, interpret_result, THERAPEUTIC_RANGES, canonical_drug_name

class TDMMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TDM Report — Therapeutic Drug Monitoring")
        self.resize(980, 700)
        self._saved_patients = []
        self._drafts = []
        self._results_dialog = None
        self._reset_to_sample_list_on_result_close = False
        self._center_on_first_show = True
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._live_plot)
        init_db()
        self._global_duration_options = load_duration_options(DEFAULT_DURATION_OPTIONS)
        migrate_from_json(PATIENTS_FILE)
        self._setup_ui()
        # Defer heavy work (data load + sampling card build) to after window shows
        QTimer.singleShot(0, self._deferred_init)

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

        self._main_scroll = QScrollArea()
        scroll = self._main_scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("root")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(32, 16, 32, 32)
        body_layout.setSpacing(12)

        body_layout.addWidget(self._make_tabs())

        self.page_stack = QStackedWidget()
        self.page_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.page_stack.addWidget(self._build_report_page())
        self.page_stack.addWidget(self._build_patients_page())
        self.page_stack.addWidget(self._build_drafts_page())
        body_layout.addWidget(self.page_stack)
        body_layout.addStretch()

        scroll.setWidget(body)
        root_layout.addWidget(scroll, 1)
        root_layout.addWidget(self._make_footer())
        self._toast = ToastMessage(root)
        self._switch_page(0)
        self._update_action_buttons()
        self._position_toast()

    def showEvent(self, event):
        super().showEvent(event)
        if self._center_on_first_show:
            self._center_on_first_show = False
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                target_width = min(self.width(), max(920, available.width() - 80))
                target_height = min(self.height(), max(640, available.height() - 100))
                self.resize(target_width, target_height)
                frame = self.frameGeometry()
                frame.moveCenter(available.center())
                self.move(frame.topLeft())

    def _deferred_init(self):
        """Runs after the event loop starts (window already visible).
        Builds the heavy sampling card and loads patient/draft data."""
        card = self._make_sampling_card()
        self._sampling_card_container.layout().addWidget(card)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._update_action_buttons()

    def _build_report_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)

        flow_shell = QFrame()
        flow_shell.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F4F8FD, stop:1 #FBFDFF);
            border: none;
            border-radius: 20px;
        """)
        flow_lay = QHBoxLayout(flow_shell)
        flow_lay.setContentsMargins(18, 16, 18, 16)
        flow_lay.setSpacing(16)

        flow_text = QVBoxLayout()
        flow_text.setSpacing(2)
        flow_title = QLabel("Report Workflow")
        flow_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 14px; font-weight: 700;")
        flow_sub = QLabel("Complete patient details first, then move to sampling and results.")
        flow_sub.setStyleSheet("color: #73839A; font-size: 11px;")
        flow_text.addWidget(flow_title)
        flow_text.addWidget(flow_sub)
        flow_lay.addLayout(flow_text)
        flow_lay.addStretch()

        step_wrap = QFrame()
        step_wrap.setStyleSheet("background: #EAF0F7; border-radius: 18px;")
        step_wrap_lay = QHBoxLayout(step_wrap)
        step_wrap_lay.setContentsMargins(6, 6, 6, 6)
        step_wrap_lay.setSpacing(6)

        self.step_patient_btn = QPushButton("  Patient")
        self.step_patient_btn.setObjectName("stepBtn")
        self.step_patient_btn.setIcon(qta.icon("mdi6.account-outline", color="#6B7D95"))
        self.step_patient_btn.setCheckable(True)
        self.step_patient_btn.setChecked(True)
        self.step_patient_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.step_patient_btn.clicked.connect(lambda: self._switch_report_step(0))
        step_wrap_lay.addWidget(self.step_patient_btn)

        self.step_sampling_btn = QPushButton("  Sampling")
        self.step_sampling_btn.setObjectName("stepBtn")
        self.step_sampling_btn.setIcon(qta.icon("mdi6.flask-outline", color="#6B7D95"))
        self.step_sampling_btn.setCheckable(True)
        self.step_sampling_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.step_sampling_btn.clicked.connect(lambda: self._switch_report_step(1))
        step_wrap_lay.addWidget(self.step_sampling_btn)

        flow_lay.addWidget(step_wrap)
        lay.addWidget(flow_shell)

        self.report_step_stack = QStackedWidget()
        self.report_step_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        patient_step = QWidget()
        patient_step_lay = QVBoxLayout(patient_step)
        patient_step_lay.setContentsMargins(0, 0, 0, 0)
        patient_step_lay.setSpacing(16)
        patient_step_lay.addWidget(self._make_patient_card())

        patient_actions = QHBoxLayout()
        patient_actions.addStretch()
        next_btn = QPushButton("Continue to Sampling  →")
        next_btn.setFixedHeight(40)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #16A34A, stop:1 #22C55E);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 22px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #15803D, stop:1 #16A34A);
            }
        """)
        next_btn.clicked.connect(lambda: self._switch_report_step(1))
        patient_actions.addWidget(next_btn)
        patient_step_lay.addLayout(patient_actions)
        self.report_step_stack.addWidget(patient_step)

        sampling_step = QWidget()
        sampling_step_lay = QVBoxLayout(sampling_step)
        sampling_step_lay.setContentsMargins(0, 0, 0, 0)
        sampling_step_lay.setSpacing(16)
        # Sampling card is built lazily in _deferred_init after window shows
        self._sampling_card_container = QWidget()
        QVBoxLayout(self._sampling_card_container).setContentsMargins(0, 0, 0, 0)
        sampling_step_lay.addWidget(self._sampling_card_container)

        calc_row = QHBoxLayout()
        calc_row.setSpacing(12)

        back_btn = QPushButton("Back to Patient")
        back_btn.setObjectName("resetBtn")
        back_btn.setFixedHeight(40)
        back_btn.clicked.connect(lambda: self._switch_report_step(0))
        calc_row.addWidget(back_btn)

        calc_row.addStretch()

        self.calc_btn = QPushButton("Generate Report")
        self.calc_btn.setObjectName("calcBtn")
        self.calc_btn.setFixedHeight(40)
        self.calc_btn.setEnabled(False)
        self.calc_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.calc_btn.clicked.connect(self._calculate)
        calc_row.addWidget(self.calc_btn)

        self.draft_btn = QPushButton("Draft")
        self.draft_btn.setObjectName("printBtn")
        self.draft_btn.setFixedHeight(40)
        self.draft_btn.setEnabled(False)
        self.draft_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.draft_btn.clicked.connect(self._save_draft)
        calc_row.addWidget(self.draft_btn)

        sampling_step_lay.addLayout(calc_row)
        self.report_step_stack.addWidget(sampling_step)

        lay.addWidget(self.report_step_stack)
        self._switch_report_step(0)
        return page

    def _switch_report_step(self, index):
        if not hasattr(self, "report_step_stack"):
            return
        for i in range(self.report_step_stack.count()):
            w = self.report_step_stack.widget(i)
            sp = QSizePolicy.Policy.Expanding if i == index else QSizePolicy.Policy.Ignored
            w.setSizePolicy(sp, sp)
            w.updateGeometry()
        self.report_step_stack.setCurrentIndex(index)
        self.report_step_stack.updateGeometry()
        if hasattr(self, "step_patient_btn"):
            self.step_patient_btn.setChecked(index == 0)
        if hasattr(self, "step_sampling_btn"):
            self.step_sampling_btn.setChecked(index == 1)

    def _build_patients_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.sample_list_card = PatientsListCard("Sample List", "No saved samples yet.", action_width=150, row_type='sample')
        self.sample_list_card.search_changed.connect(lambda _: self._refresh_patients_list())
        lay.addWidget(self.sample_list_card)
        return page

    def _build_drafts_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.draft_list_card = PatientsListCard("Draft List", "No drafts yet.", action_width=84, row_type='draft')
        self.draft_list_card.search_changed.connect(lambda _: self._refresh_patients_list())
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
        self.report_tab_btn.setObjectName("mainTab")
        self.report_tab_btn.setIcon(qta.icon("mdi6.flask-outline", color="#718096"))
        self.report_tab_btn.clicked.connect(lambda: self._switch_page(0))
        shell_lay.addWidget(self.report_tab_btn)

        self.patients_tab_btn = QPushButton("Sample List")
        self.patients_tab_btn.setObjectName("mainTab")
        self.patients_tab_btn.setIcon(qta.icon("mdi6.format-list-bulleted-square", color="#718096"))
        self.patients_tab_btn.clicked.connect(lambda: self._switch_page(1))

        self.drafts_tab_btn = QPushButton("Draft List")
        self.drafts_tab_btn.setObjectName("mainTab")
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
            "background: #16A34A; color: white; border: 2px solid #DCFCE7; border-radius: 9px; font-size: 10px; font-weight: bold;"
        )

        self.drafts_badge = QLabel("0")
        self.drafts_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drafts_badge.setFixedSize(18, 18)
        self.drafts_badge.setStyleSheet(
            "background: #FBBF24; color: white; border: 2px solid #FFF7E8; border-radius: 9px; font-size: 10px; font-weight: bold;"
        )

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(8)
        badge_row.addWidget(self.patients_tab_btn)
        badge_row.addWidget(self.patients_badge)
        badge_row.addWidget(self.drafts_tab_btn)
        badge_row.addWidget(self.drafts_badge)
        badge_row.addStretch()

        container = QWidget()
        container.setLayout(badge_row)
        shell_lay.addWidget(container)

        row.addWidget(shell)
        row.addStretch()
        return wrap

    def _switch_page(self, index):
        for i in range(self.page_stack.count()):
            w = self.page_stack.widget(i)
            if i == index:
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            else:
                w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.page_stack.setCurrentIndex(index)
        self.report_tab_btn.setChecked(index == 0)
        self.patients_tab_btn.setChecked(index == 1)
        self.drafts_tab_btn.setChecked(index == 2)
        def tab_style(kind, active):
            palette = {
                'report': {
                    'bg': "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #EFF6FF, stop:1 #E0ECFF)",
                    'border': "#B9D2FF",
                    'color': "#123A73",
                    'hover': "#F3F8FF",
                },
                'sample': {
                    'bg': "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ECFDF5, stop:1 #DCFCE7)",
                    'border': "#86EFAC",
                    'color': "#166534",
                    'hover': "#F0FDF4",
                },
                'draft': {
                    'bg': "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFF7ED, stop:1 #FFEDD5)",
                    'border': "#FDBA74",
                    'color': "#9A3412",
                    'hover': "#FFF7ED",
                },
            }[kind]
            if active:
                return (
                    "QPushButton { "
                    f"background: {palette['bg']}; "
                    f"color: {palette['color']}; "
                    f"border: 1.5px solid {palette['border']}; "
                    "border-radius: 14px; "
                    "padding-top: 10px; "
                    "padding-bottom: 10px; "
                    "padding-left: 16px; "
                    "padding-right: 16px; "
                    "font-size: 14px; "
                    "font-weight: 800; "
                    "}"
                )
            return (
                "QPushButton { "
                "background: rgba(255,255,255,0.34); "
                "color: #64748B; "
                "border: 1px solid transparent; "
                "border-radius: 14px; "
                "padding-top: 10px; "
                "padding-bottom: 10px; "
                "padding-left: 16px; "
                "padding-right: 16px; "
                "font-size: 14px; "
                "font-weight: 700; "
                "}"
                "QPushButton:hover { "
                f"background: {palette['hover']}; "
                f"color: {palette['color']}; "
                f"border: 1px solid {palette['border']}; "
                "}"
            )
        self.report_tab_btn.setStyleSheet(tab_style('report', index == 0))
        self.patients_tab_btn.setStyleSheet(tab_style('sample', index == 1))
        self.drafts_tab_btn.setStyleSheet(tab_style('draft', index == 2))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def _position_toast(self):
        if not hasattr(self, '_toast'):
            return
        width = min(360, max(280, self.width() - 80))
        self._toast.setFixedWidth(width)
        self._toast.move(self.width() - width - 28, 84)

    def _show_toast(self, title, body, tone="success"):
        self._position_toast()
        self._toast.show_message(title, body, tone=tone)

    # ──────────────────────────────────────
    # Header
    # ──────────────────────────────────────
    def _make_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(72)
        hdr.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #052E16, stop:0.4 #166534, stop:0.6 #166534, stop:1 #052E16);
            border-bottom: 1px solid rgba(255,255,255,0.08);
        """)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(0)

        # ── Logo ─────────────────────────────────
        logo_wrap = QWidget()
        logo_wrap.setFixedSize(46, 46)
        logo_wrap.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #16A34A, stop:1 #15803D);
            border-radius: 13px;
            border: 1px solid rgba(255,255,255,0.2);
        """)
        logo_lay = QHBoxLayout(logo_wrap)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_icon = QLabel()
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon.setPixmap(qta.icon("mdi6.flask-outline", color="white").pixmap(22, 22))
        logo_icon.setStyleSheet("background: transparent;")
        logo_lay.addWidget(logo_icon)
        lay.addWidget(logo_wrap)
        lay.addSpacing(14)

        # ── Title ────────────────────────────────
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t1 = QLabel("TDM Report")
        t1.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 700; "
            "letter-spacing: 0.3px; background: transparent;"
        )
        t2 = QLabel("Therapeutic Drug Monitoring")
        t2.setStyleSheet(
            "color: rgba(255,255,255,0.45); font-size: 10px; "
            "letter-spacing: 0.5px; background: transparent;"
        )
        title_col.addWidget(t1)
        title_col.addWidget(t2)
        lay.addLayout(title_col)
        lay.addSpacing(20)

        # ── Badge chip ───────────────────────────
        badge = QLabel("AUC · PK · TDM")
        badge.setStyleSheet("""
            color: rgba(255,255,255,0.6);
            background: rgba(255,255,255,0.07);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 10px;
            padding: 4px 10px;
        """)
        lay.addWidget(badge)
        badge.hide()
        lay.addStretch()

        # ── New Patient button ────────────────────
        reset = QPushButton()
        reset.setFixedHeight(38)
        reset.setText("  New Patient")
        reset.setIcon(qta.icon("mdi6.plus", color="white"))
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #16A34A, stop:1 #22C55E);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                padding: 0 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #15803D, stop:1 #16A34A);
            }
        """)
        reset.setGraphicsEffect(make_shadow(12, 3, 60))
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)

        return hdr

    def _make_footer(self):
        ftr = QWidget()
        ftr.setFixedHeight(44)
        ftr.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #031B0F, stop:0.45 #0F5132, stop:1 #031B0F);
            border-top: 1px solid rgba(255,255,255,0.08);
        """)
        lay = QHBoxLayout(ftr)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)

        mark = QLabel()
        mark.setFixedSize(56, 28)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = Path(__file__).resolve().with_name("softzino_logo.png")
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if color.red() > 190 and color.green() > 190 and color.blue() > 190:
                        color.setAlpha(0)
                        image.setPixelColor(x, y, color)
            cleaned = QPixmap.fromImage(image)
            mark.setPixmap(cleaned.scaled(56, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        mark.setStyleSheet("background: transparent;")
        lay.addWidget(mark)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("SOFTZINO")
        brand.setStyleSheet(
            "color: #2D8CFF; font-size: 13px; font-weight: 800; letter-spacing: 0.35px; background: transparent;"
        )
        tagline = QLabel("Innovation that Differentiates")
        tagline.setStyleSheet(
            "color: rgba(191,219,254,0.88); font-size: 8px; font-style: italic; letter-spacing: 0.45px; background: transparent;"
        )
        brand_col.addWidget(brand)
        brand_col.addWidget(tagline)
        lay.addLayout(brand_col)
        lay.addStretch()

        copy = QLabel("Copyright © SOFTZINO. This software is developed and maintained by SOFTZINO.")
        copy.setWordWrap(True)
        copy.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        copy.setStyleSheet(
            "color: rgba(255,255,255,0.72); font-size: 9px; background: transparent;"
        )
        lay.addWidget(copy, 1)

        return ftr

    # ──────────────────────────────────────
    # Patient card
    # ──────────────────────────────────────
    def _make_patient_card(self):
        card = Card("Patient Information", "mdi6.account-outline", icon_color="#16A34A")

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
                padding: 13px 16px 13px 16px;
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
                width: 38px;
                background: #EEF5FF;
                border-top-right-radius: 16px;
                border-bottom-right-radius: 16px;
            }}
            QComboBox::down-arrow {{
                width: 14px;
                height: 14px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid #DCE7F2;
                border-radius: 14px;
                selection-background-color: #F3F8FF;
                selection-color: {TEXT_CLR};
                font-size: 13px;
                background: white;
                outline: 0;
                padding: 6px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 34px;
                padding: 6px 12px 6px 12px;
                border-radius: 10px;
                margin: 2px 4px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: #EEF5FF;
                color: #123A73;
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
        self.f_hosp_no.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,11}"), self))
        self.f_ward    = field("e.g. Ward 8")
        self.f_dept    = field("e.g. Neph-2")
        self.f_diag    = field("e.g. Post Renal Transplant")
        self.f_diag.setText("Post Renal Transplant")
        for edit in [self.f_name, self.f_age, self.f_weight, self.f_hosp_no, self.f_ward, self.f_dept, self.f_diag]:
            edit.textChanged.connect(self._on_data_changed)

        # Sex selector
        self.f_sex = NoWheelComboBox()
        self.f_sex.addItems(["Choose a sex", "Male", "Female", "Other"])
        self.f_sex.setStyleSheet(combo_style)
        self.f_sex.currentTextChanged.connect(self._on_data_changed)
        self.f_sex.setCurrentIndex(0)
        # Fixed-name file in system temp dir — overwritten on each run, never accumulates
        import tempfile, os
        _arrow_path = os.path.join(tempfile.gettempdir(), "tdm_report_arrow_down.png")
        qta.icon("mdi6.chevron-down", color="#6B8CAE").pixmap(14, 14).save(_arrow_path)
        _arrow_path = _arrow_path.replace("\\", "/")
        self.f_sex.setStyleSheet(combo_style + f"""
            QComboBox {{
                padding: 13px 42px 13px 16px;
            }}
            QComboBox::down-arrow {{ image: url("{_arrow_path}"); width: 14px; height: 14px; }}
        """)

        self.f_tx_date = SmartDateEdit()
        self.f_tx_date.dateChanged.connect(lambda *_: self._on_data_changed())


        # Medication selector
        self.f_med = MedicationSelector()
        self.f_med.med_added.connect(lambda name: self._show_toast("Medication added", f'"{name}" added to the list.'))
        self.f_med.selection_changed.connect(self._on_data_changed)

        def add_field(layout, row, col, label, widget, span=1):
            col_lbl = QVBoxLayout()
            col_lbl.setSpacing(7)
            if label == "Patient Name":
                lbl = QLabel('PATIENT NAME <span style="color:#E53935;">*</span>')
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setStyleSheet("color: #7E8DA3; font-size: 10px; font-weight: bold; letter-spacing: 0.8px;")
                col_lbl.addWidget(lbl)
            else:
                col_lbl.addWidget(small_label(label, color="#7E8DA3", size=10, bold=True))
            col_lbl.addWidget(widget)
            layout.addLayout(col_lbl, row, col, 1, span)


        demographics_box = QFrame()
        demographics_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F0FDF4, stop:1 #FAFFFE);
            border: none;
            border-radius: 22px;
        """)
        demographics_lay = QVBoxLayout(demographics_box)
        demographics_lay.setContentsMargins(18, 16, 18, 16)
        demographics_lay.setSpacing(14)

        demo_head = QHBoxLayout()
        demo_head.setSpacing(10)
        demo_icon = QLabel()
        demo_icon.setFixedSize(32, 32)
        demo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        demo_icon.setPixmap(qta.icon("mdi6.badge-account-outline", color="#16A34A").pixmap(20, 20))
        demo_icon.setStyleSheet("background: #DCFCE7; border-radius: 16px;")
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
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F6FEFB, stop:1 #FCFFFE);
            border: none;
            border-radius: 22px;
        """)
        clinical_lay = QVBoxLayout(clinical_box)
        clinical_lay.setContentsMargins(18, 16, 18, 16)
        clinical_lay.setSpacing(14)

        clinical_head = QHBoxLayout()
        clinical_head.setSpacing(10)
        clinical_icon = QLabel()
        clinical_icon.setFixedSize(32, 32)
        clinical_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clinical_icon.setPixmap(qta.icon("mdi6.heart-pulse", color="#14B8A6").pixmap(20, 20))
        clinical_icon.setStyleSheet("background: #E8FBF4; border-radius: 16px;")
        clinical_head.addWidget(clinical_icon)
        clinical_title = QLabel("Clinical Context")
        clinical_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        clinical_head.addWidget(clinical_title)
        clinical_head.addStretch()
        clinical_lay.addLayout(clinical_head)

        clinical_grid = QGridLayout()
        clinical_grid.setSpacing(16)
        clinical_grid.setHorizontalSpacing(20)
        clinical_grid.setColumnStretch(0, 1)
        clinical_grid.setColumnStretch(1, 1)

        date_col = QVBoxLayout()
        date_col.setSpacing(8)
        date_col.addWidget(small_label("Date of Transplant", color="#7E8DA3", size=10, bold=True))
        self.f_tx_date.setMaximumWidth(620)
        date_col.addWidget(self.f_tx_date, 0, Qt.AlignmentFlag.AlignTop)
        date_col.addStretch()
        clinical_grid.addLayout(date_col, 0, 0, Qt.AlignmentFlag.AlignTop)

        med_col = QVBoxLayout()
        med_col.setSpacing(8)
        med_col.addWidget(small_label("Medications", color="#7E8DA3", size=10, bold=True))
        self.f_med.setMaximumWidth(620)
        med_col.addWidget(self.f_med, 0, Qt.AlignmentFlag.AlignTop)
        med_col.addStretch()
        clinical_grid.addLayout(med_col, 0, 1, Qt.AlignmentFlag.AlignTop)

        clinical_lay.addLayout(clinical_grid)

        diagnosis_col = QVBoxLayout()
        diagnosis_col.setContentsMargins(0, -4, 0, 0)
        diagnosis_col.setSpacing(6)
        diagnosis_col.addWidget(small_label("Diagnosis", color="#7E8DA3", size=10, bold=True))
        self.f_diag.setMinimumWidth(400)
        self.f_diag.setMaximumWidth(400)
        self.f_diag.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        diag_wrap = QWidget()
        diag_wrap.setMinimumWidth(400)
        diag_wrap.setMaximumWidth(400)
        diag_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        diag_row = QHBoxLayout(diag_wrap)
        diag_row.setContentsMargins(0, 0, 0, 0)
        diag_row.setSpacing(0)
        diag_row.addWidget(self.f_diag)
        diagnosis_col.addWidget(diag_wrap, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        diagnosis_col.addStretch()
        clinical_grid.addLayout(diagnosis_col, 1, 0, Qt.AlignmentFlag.AlignTop)

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

        self.f_drug = DrugSelector()
        self.f_drug.currentTextChanged.connect(self._on_data_changed)

        self.f_preparation = field("e.g. Mycept-5")
        self.f_preparation.setText("Mycophenolate Mofetil (MMF)")
        self.f_dose = field("e.g. 540 mg - 720 mg")
        for edit in [self.f_preparation, self.f_dose]:
            edit.textChanged.connect(self._on_data_changed)
        self.f_dose_dt = SmartDateTimeEdit()
        self.f_dose_dt.dateTimeChanged.connect(lambda *_: self._on_data_changed())
        self.f_sample_collection_date = SmartDateEdit()
        self.f_sample_collection_date.dateChanged.connect(lambda *_: self._on_data_changed())

        def add_meta(row, col, label, widget, required=False):
            col_lay = QVBoxLayout()
            col_lay.setSpacing(7)
            if required:
                lbl = QLabel(f'{label.upper()} <span style="color:#E53935;">*</span>')
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setStyleSheet("color: #7E8DA3; font-size: 10px; font-weight: bold; letter-spacing: 0.8px;")
            else:
                lbl = small_label(label, color="#7E8DA3", size=10, bold=True)
            col_lay.addWidget(lbl)
            col_lay.addWidget(widget)
            meta_grid.addLayout(col_lay, row, col)

        meta_intro = QFrame()
        meta_intro.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F0FDF4, stop:0.6 #FBFEFF, stop:1 #F0FDF4);
            border: none;
            border-radius: 24px;
        """)
        meta_intro_lay = QHBoxLayout(meta_intro)
        meta_intro_lay.setContentsMargins(20, 18, 20, 18)
        meta_intro_lay.setSpacing(16)

        meta_icon = QLabel()
        meta_icon.setFixedSize(48, 48)
        meta_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_icon.setPixmap(qta.icon("mdi6.flask-outline", color="#16A34A").pixmap(22, 22))
        meta_icon.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #DCFCE7, stop:1 #BBF7D0);
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
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #F0FDF4, stop:1 #FBFEFF);
            border: none;
            border-radius: 22px;
        """)
        meta_box_lay = QVBoxLayout(meta_box)
        meta_box_lay.setContentsMargins(18, 16, 18, 16)
        meta_box_lay.setSpacing(14)

        meta_head = QHBoxLayout()
        meta_head.setSpacing(10)
        meta_head_icon = QLabel()
        meta_head_icon.setFixedSize(28, 28)
        meta_head_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_head_icon.setPixmap(qta.icon("mdi6.pill", color="#16A34A").pixmap(16, 16))
        meta_head_icon.setStyleSheet("background: #DCFCE7; border-radius: 14px;")
        meta_head.addWidget(meta_head_icon)
        meta_head_title = QLabel("Drug and Timing")
        meta_head_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        meta_head.addWidget(meta_head_title)
        meta_head.addStretch()
        meta_box_lay.addLayout(meta_head)

        add_meta(0, 0, "Requested Drug", self.f_drug, required=True)
        add_meta(0, 1, "Requested Drug Preparation", self.f_preparation, required=True)
        add_meta(0, 2, "Dose of Requested Drug", self.f_dose, required=True)
        add_meta(0, 3, "Dose Date & Time", self.f_dose_dt)
        add_meta(1, 0, "Sample Collection Date", self.f_sample_collection_date)
        meta_box_lay.addLayout(meta_grid)
        card.body().addWidget(meta_box)

        # ── Top row: Trough + Duration side by side ──
        control_box = QFrame()
        control_box.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #FFF7ED, stop:1 #FFFBF5);
            border: none;
            border-radius: 22px;
        """)
        control_lay = QVBoxLayout(control_box)
        control_lay.setContentsMargins(18, 18, 18, 18)
        control_lay.setSpacing(14)

        control_head = QHBoxLayout()
        control_head.setSpacing(10)
        control_icon = QLabel()
        control_icon.setFixedSize(32, 32)
        control_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_icon.setPixmap(qta.icon("mdi6.chart-timeline-variant", color="#EA580C").pixmap(20, 20))
        control_icon.setStyleSheet("background: #FFEDD5; border-radius: 16px;")
        control_head.addWidget(control_icon)
        control_title = QLabel("Sampling Controls")
        control_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
        control_head.addWidget(control_title)
        control_head.addStretch()

        # Mode toggle — Multi-point | Direct AUC
        self._sampling_mode = 'multi'
        toggle_shell = QFrame()
        toggle_shell.setStyleSheet("background: #EAF0F7; border-radius: 12px;")
        toggle_lay = QHBoxLayout(toggle_shell)
        toggle_lay.setContentsMargins(4, 4, 4, 4)
        toggle_lay.setSpacing(4)

        def _make_toggle_btn(text, mode):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none;
                    border-radius: 9px; font-size: 12px;
                    font-weight: 600; color: #64748B;
                    padding: 0 14px;
                }
                QPushButton:checked {
                    background: white; color: #EA580C;
                }
            """)
            btn.clicked.connect(lambda: self._switch_sampling_mode(mode))
            return btn

        self._toggle_multi = _make_toggle_btn("Multi-point", 'multi')
        self._toggle_direct = _make_toggle_btn("Direct AUC", 'direct')
        self._toggle_multi.setChecked(True)
        toggle_lay.addWidget(self._toggle_multi)
        toggle_lay.addWidget(self._toggle_direct)
        control_head.addWidget(toggle_shell)
        control_lay.addLayout(control_head)

        # Direct AUC input (hidden by default)
        self._direct_auc_box = QWidget()
        direct_lay = QVBoxLayout(self._direct_auc_box)
        direct_lay.setContentsMargins(0, 4, 0, 4)
        direct_lay.setSpacing(8)
        direct_lay.addWidget(small_label(
            "AUC₀₋₁₂ (mg·h/L) — enter known value directly",
            color="#7E8DA3", size=10, bold=True, uppercase=False
        ))
        self._direct_auc_edit = QLineEdit()
        self._direct_auc_edit.setPlaceholderText("e.g. 45.5")
        self._direct_auc_edit.setFixedWidth(220)
        self._direct_auc_edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1.5px solid #FDBA74;
                border-radius: 16px;
                padding: 13px 18px;
                font-size: 18px;
                font-weight: bold;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{ border: 2px solid #EA580C; }}
        """)
        self._direct_auc_edit.textChanged.connect(self._on_data_changed)
        direct_lay.addWidget(self._direct_auc_edit)
        self._direct_auc_box.hide()
        control_lay.addWidget(self._direct_auc_box)

        # Multi-point container
        self._multi_point_box = QWidget()
        multi_lay = QVBoxLayout(self._multi_point_box)
        multi_lay.setContentsMargins(0, 0, 0, 0)
        multi_lay.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(28)

        # Trough input
        trough_col = QVBoxLayout(); trough_col.setSpacing(8)
        trough_col.addWidget(small_label("Trough (Pre-dose) Concentration (µg/mL)", color="#7E8DA3", size=10, bold=True, uppercase=False))
        self.trough_edit = QLineEdit()
        self.trough_edit.setPlaceholderText("e.g. 2.93")
        self.trough_edit.setFixedWidth(200)
        self.trough_edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1.5px solid #FDBA74;
                border-radius: 16px;
                padding: 13px 18px;
                font-size: 18px;
                font-weight: bold;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                border: 2px solid #EA580C;
            }}
        """)
        self.trough_edit.textChanged.connect(self._on_data_changed)
        trough_col.addWidget(self.trough_edit)
        trough_col.addStretch()
        trough_shell = QWidget()
        trough_shell.setFixedWidth(360)
        trough_shell.setLayout(trough_col)
        top_row.addWidget(trough_shell, 0, Qt.AlignmentFlag.AlignTop)

        # Duration controls
        dur_col = QVBoxLayout(); dur_col.setSpacing(8)
        dur_col.setContentsMargins(0, 8, 0, 0)
        dur_col.addWidget(small_label("Number of Samples", color="#7E8DA3", size=10, bold=True))
        self._duration_wrap = QWidget()
        self._duration_row = QHBoxLayout(self._duration_wrap)
        self._duration_row.setContentsMargins(0, 0, 0, 0)
        self._duration_row.setSpacing(10)
        self._duration_scroll = QScrollArea()
        self._duration_scroll.setWidgetResizable(False)
        self._duration_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._duration_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._duration_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._duration_scroll.setWidget(self._duration_wrap)
        self._duration_scroll.setFixedSize(332, 76)
        self._duration_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:horizontal { background: transparent; height: 8px; margin: 4px 22px 0 0; }
            QScrollBar::handle:horizontal { background: #C9D8EA; border-radius: 4px; min-width: 32px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
        """)
        self._add_duration_btn = QPushButton()
        self._add_duration_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_duration_btn.setFixedSize(36, 36)
        self._add_duration_btn.setIcon(qta.icon("mdi6.plus", color="#EA580C"))
        self._add_duration_btn.setIconSize(self._add_duration_btn.size() * 0.52)
        self._add_duration_btn.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px dashed #FDBA74;
                border-radius: 18px;
            }
            QPushButton:hover {
                background: #FFF7ED;
                border: 1px solid #F97316;
            }
        """)
        self._add_duration_btn.clicked.connect(self._add_duration_option)
        self._duration_chips = {}
        self._duration_options = list(self._global_duration_options)
        initial_duration = self._duration_options[0] if self._duration_options else 4
        self._refresh_duration_controls(selected=initial_duration)
        duration_shell = QHBoxLayout()
        duration_shell.setContentsMargins(0, 0, 0, 0)
        duration_shell.setSpacing(10)
        duration_shell.addWidget(self._duration_scroll, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        duration_shell.addWidget(self._add_duration_btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        duration_shell.addStretch()
        dur_col.addLayout(duration_shell)

        # Helper text under buttons
        hint = QLabel("Time points are editable — tap any time to adjust")
        hint.setStyleSheet(f"color: {LABEL_CLR}; font-size: 11px;")
        dur_col.addWidget(hint)

        top_row.addLayout(dur_col, 1)
        top_row.addStretch()
        multi_lay.addLayout(top_row)
        # ── Modern sample table ──
        table_col = QVBoxLayout(); table_col.setSpacing(8)
        table_col.addWidget(small_label("Sample Points", color="#7E8DA3", size=10, bold=True))
        self.sample_table = ModernSampleTable()
        self.sample_table.data_changed.connect(self._on_data_changed)
        table_col.addWidget(self.sample_table)
        multi_lay.addLayout(table_col)

        control_lay.addWidget(self._multi_point_box)
        card.body().addWidget(control_box)

        # Populate with default scheme
        self._populate_table(initial_duration)
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
        if hasattr(self, '_current_scheme') and hasattr(self, '_scheme_rows_cache'):
            self._scheme_rows_cache[self._current_scheme] = self.sample_table.get_rows_payload()
        self._current_scheme = n
        if not hasattr(self, '_scheme_rows_cache'):
            self._scheme_rows_cache = {}
        rows_payload = self._scheme_rows_cache.get(n)
        if rows_payload:
            self.sample_table.set_rows_payload(rows_payload)
        else:
            self.sample_table.set_rows_payload(self._rows_payload_for_duration(n))
            self._scheme_rows_cache[n] = self.sample_table.get_rows_payload()
        self._refresh_duration_chip_selection()
        self._live_plot()

    def _rows_payload_for_duration(self, duration, source_rows=None):
        rows = source_rows or []
        payload = []
        for i, time_point in enumerate(sampling_times_for_duration(duration)):
            conc = rows[i].get("concentration", "") if i < len(rows) else ""
            payload.append({"time": str(time_point), "concentration": conc})
        return payload

    def _refresh_duration_controls(self, selected=None):
        while self._duration_row.count():
            item = self._duration_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._duration_chips = {}
        for duration in self._duration_options:
            chip = DurationChip(duration)
            chip.selected.connect(self._on_scheme_changed)
            chip.removed.connect(self._remove_duration_option)
            self._duration_chips[duration] = chip
            self._duration_row.addWidget(chip)
        self._duration_row.addStretch()
        content_width = max(332, len(self._duration_options) * 84 + max(0, len(self._duration_options) - 1) * 10)
        self._duration_wrap.resize(content_width, 60)
        self._duration_wrap.setMinimumSize(content_width, 60)
        policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded if len(self._duration_options) > 3 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self._duration_scroll.setHorizontalScrollBarPolicy(policy)
        self._duration_scroll.horizontalScrollBar().setValue(0)
        self._duration_scroll.updateGeometry()
        self._duration_wrap.updateGeometry()
        self._refresh_duration_chip_selection(selected)

    def _refresh_duration_chip_selection(self, selected=None):
        selected = self._current_scheme if selected is None else selected
        for duration, chip in self._duration_chips.items():
            chip.set_selected(duration == selected)

    def _set_duration_options(self, options, selected=None):
        cleaned = []
        for value in options:
            try:
                ivalue = int(value)
            except Exception:
                continue
            if ivalue > 0 and ivalue not in cleaned:
                cleaned.append(ivalue)
        self._duration_options = cleaned or list(DEFAULT_DURATION_OPTIONS)
        self._global_duration_options = list(self._duration_options)
        save_duration_options(self._global_duration_options)
        if selected is None or selected not in self._duration_options:
            selected = self._duration_options[0]
        self._refresh_duration_controls(selected=selected)

    def _switch_sampling_mode(self, mode: str):
        self._sampling_mode = mode
        is_direct = (mode == 'direct')
        self._direct_auc_box.setVisible(is_direct)
        self._multi_point_box.setVisible(not is_direct)
        self._on_data_changed()

    def _add_duration_option(self):
        dlg = DurationEditModal("Add Sampling Duration", "Save Duration", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = dlg.get_value()
        if not candidate:
            return
        if candidate in self._duration_options:
            self._show_toast("Already exists", f"{candidate}h is already in the list.")
            return
        self._duration_options.append(candidate)
        self._scheme_rows_cache[candidate] = self._rows_payload_for_duration(candidate)
        self._set_duration_options(self._duration_options, selected=candidate)
        self._populate_table(candidate)
        self._on_data_changed()
        self._show_toast("Duration added", f"{candidate}h sampling duration added.")

    def _remove_duration_option(self, duration):
        if len(self._duration_options) <= 1:
            self._show_toast("Cannot remove", "At least one sampling duration is required.", tone="warning")
            self._refresh_duration_controls(selected=self._current_scheme)
            return
        self._duration_options = [d for d in self._duration_options if d != duration]
        self._scheme_rows_cache.pop(duration, None)
        next_duration = self._current_scheme
        if duration == self._current_scheme or next_duration not in self._duration_options:
            next_duration = self._duration_options[0]
        self._set_duration_options(self._duration_options, selected=next_duration)
        self._populate_table(next_duration)
        self._on_data_changed()
        self._show_toast("Duration removed", f"{duration}h sampling duration removed.")

    # ──────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────
    def _on_scheme_changed(self, n):
        self._populate_table(n)
        self._on_data_changed()

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
        try:
            self._saved_patients, self._drafts = load_all()
        except Exception:
            self._saved_patients = []
            self._drafts = []

    def _patient_payload(self):
        return {
            'name': self.f_name.text().strip() or 'N/A',
            'age': self.f_age.text().strip() or 'N/A',
            'sex': '' if self.f_sex.currentText() == "Choose a sex" else self.f_sex.currentText(),
            'weight': self.f_weight.text().strip() or 'N/A',
            'hosp_id': self.f_hosp_no.text().strip() or 'N/A',
            'ward': self.f_ward.text().strip() or 'N/A',
            'dept': self.f_dept.text().strip() or 'N/A',
            'drug': self.f_drug.currentText().strip(),
            'preparation': self.f_preparation.text().strip(),
            'dose': self.f_dose.text().strip(),
            'dose_dt': self.f_dose_dt.dateTime().toString("dd.MM.yyyy 'at' hh:mmAP"),
            'sample_collection_date': self.f_sample_collection_date.date().toString("dd.MM.yyyy"),
            'diag': self.f_diag.text().strip() or 'N/A',
            'tx_date': self.f_tx_date.date().toString("dd.MM.yyyy"),
            'med': self.f_med.get_text() or 'N/A',
        }

    def _form_signature(self):
        return {
            'patient': self._patient_payload(),
            'sampling_mode': getattr(self, '_sampling_mode', 'multi'),
            'direct_auc': self._direct_auc_edit.text().strip() if hasattr(self, '_direct_auc_edit') else '',
            'scheme': getattr(self, '_current_scheme', 4),
            'duration_options': list(getattr(self, '_duration_options', DEFAULT_DURATION_OPTIONS)),
            'trough': self.trough_edit.text().strip(),
            'sample_rows': self.sample_table.get_rows_payload(),
        }

    def _snapshot_payload(self):
        mode = getattr(self, '_sampling_mode', 'multi')
        if mode == 'direct':
            times, concs = [], []
        else:
            times, concs = self._read_table(skip_empty=True)
        data = {
            'id': datetime.now().strftime("%Y%m%d%H%M%S%f"),
            'saved_at': datetime.now().strftime("%d/%m/%Y"),
            'report_path': '',
            'patient': self._patient_payload(),
            'sampling_mode': mode,
            'direct_auc': self._direct_auc_edit.text().strip() if hasattr(self, '_direct_auc_edit') else '',
            'scheme': getattr(self, '_current_scheme', 4),
            'duration_options': list(getattr(self, '_duration_options', DEFAULT_DURATION_OPTIONS)),
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

    def _has_required_sampling_fields(self):
        if not hasattr(self, 'f_drug'):
            return False
        if getattr(self, '_sampling_mode', 'multi') == 'direct':
            try:
                val = float(self._direct_auc_edit.text().strip())
                return val > 0
            except (ValueError, AttributeError):
                return False
        return all([
            self.f_drug.currentText().strip(),
            self.f_preparation.text().strip(),
            self.f_dose.text().strip(),
        ])

    def _can_generate_or_save(self):
        if not self.f_name.text().strip() or not self._has_required_sampling_fields():
            return False
        # Direct AUC mode only needs a valid AUC value (checked above)
        if getattr(self, '_sampling_mode', 'multi') == 'direct':
            return True
        times, concs = self._read_table(skip_empty=False)
        return times is not None and len(times) >= 3

    def _can_save_draft(self):
        return bool(self.f_name.text().strip())

    def _update_action_buttons(self):
        enabled = self._can_generate_or_save()
        draft_enabled = self._can_save_draft()
        is_editing_saved_sample = (
            getattr(self, '_active_record_source', None) == 'sample'
            and bool(getattr(self, '_active_record_id', None))
        )
        is_editing_draft = (
            getattr(self, '_active_record_source', None) == 'draft'
            and bool(getattr(self, '_active_record_id', None))
        )
        self.calc_btn.setText("Update Report" if is_editing_saved_sample else "Generate Report")
        if is_editing_saved_sample:
            enabled = enabled and self._form_signature() != getattr(self, '_loaded_form_signature', None)
        if is_editing_draft:
            draft_enabled = draft_enabled and self._form_signature() != getattr(self, '_loaded_form_signature', None)
        self.calc_btn.setEnabled(enabled)
        self.calc_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        self.draft_btn.setVisible(not is_editing_saved_sample)
        self.draft_btn.setEnabled(draft_enabled)
        self.draft_btn.setCursor(Qt.CursorShape.PointingHandCursor if draft_enabled else Qt.CursorShape.ForbiddenCursor)

    _LIST_PAGE_SIZE = 50

    def _refresh_patients_list(self):
        if not hasattr(self, 'sample_list_card'):
            return

        def matches_search(snapshot, query):
            if not query:
                return True
            p = snapshot.get('patient', {})
            return (
                query in (p.get('name') or '').lower() or
                query in (p.get('pid') or '').lower() or
                query in (p.get('hosp_id') or '').lower()
            )

        def populate(card, items, edit_cb, delete_cb, row_type='sample', view_cb=None, print_cb=None):
            query = card.search_text()
            filtered = [s for s in items if matches_search(s, query)]
            visible = list(reversed(filtered))

            rows_layout = card._rows_lay
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if not visible:
                card.set_empty_visible(True)
                return

            card.set_empty_visible(False)
            page = visible[:self._LIST_PAGE_SIZE]
            remaining = visible[self._LIST_PAGE_SIZE:]

            for snapshot in page:
                row = PatientRow(snapshot, row_type=row_type)
                row.edit_requested.connect(edit_cb)
                if view_cb is not None:
                    row.view_requested.connect(view_cb)
                if print_cb is not None:
                    row.print_requested.connect(print_cb)
                row.delete_requested.connect(delete_cb)
                rows_layout.addWidget(row)

            if remaining:
                def make_load_more(rest, rl, ec, dc, rt, vc, pc, btn_ref):
                    def _load():
                        btn_ref[0].deleteLater()
                        for snapshot in rest[:self._LIST_PAGE_SIZE]:
                            row = PatientRow(snapshot, row_type=rt)
                            row.edit_requested.connect(ec)
                            if vc is not None:
                                row.view_requested.connect(vc)
                            if pc is not None:
                                row.print_requested.connect(pc)
                            row.delete_requested.connect(dc)
                            rl.addWidget(row)
                        leftover = rest[self._LIST_PAGE_SIZE:]
                        if leftover:
                            new_btn = _make_load_more_btn(leftover, rl, ec, dc, rt, vc, pc)
                            rl.addWidget(new_btn)
                        else:
                            rl.addStretch()
                    return _load

                def _make_load_more_btn(rest, rl, ec, dc, rt, vc, pc):
                    btn = QPushButton(f"Load {min(len(rest), self._LIST_PAGE_SIZE)} more  ↓  ({len(rest)} remaining)")
                    btn.setFixedHeight(36)
                    btn.setStyleSheet("""
                        QPushButton {
                            background: #F0F4F8; color: #1A73E8;
                            border: 1px solid #D0DCF0; border-radius: 8px;
                            font-size: 13px; font-weight: 600;
                        }
                        QPushButton:hover { background: #E8F0FE; }
                    """)
                    btn_ref = [btn]
                    btn.clicked.connect(make_load_more(rest, rl, ec, dc, rt, vc, pc, btn_ref))
                    return btn

                rows_layout.addWidget(
                    _make_load_more_btn(remaining, rows_layout, edit_cb, delete_cb, row_type, view_cb, print_cb)
                )
            else:
                rows_layout.addStretch()

        populate(
            self.sample_list_card,
            self._saved_patients,
            self._load_saved_sample,
            self._delete_saved_patient,
            row_type='sample',
            view_cb=self._view_saved_sample_result,
            print_cb=self._print_saved_sample,
        )
        if hasattr(self, 'draft_list_card'):
            populate(self.draft_list_card, self._drafts, self._load_draft, self._delete_draft, row_type='draft')
        self.patients_badge.setText(str(len(self._saved_patients)))
        if hasattr(self, 'drafts_badge'):
            self.drafts_badge.setText(str(len(self._drafts)))

    def _save_draft(self):
        snapshot = self._snapshot_payload()
        snapshot.pop('pk', None)
        snapshot.pop('interp', None)
        if getattr(self, '_active_record_source', None) == 'draft' and getattr(self, '_active_record_id', None):
            delete_record(self._active_record_id)
        save_record(snapshot, 'draft')
        p = snapshot.get('patient', {})
        log_draft_saved(p.get('pid', 'N/A'), p.get('name', 'N/A'))
        self._load_saved_patients()
        self._refresh_patients_list()
        self._clear_form_state()
        self._switch_page(2)
        self._main_scroll.verticalScrollBar().setValue(0)
        self._show_toast("Draft saved successfully", "Sample moved to Draft List.")

    def _load_saved_sample(self, patient_id):
        snapshot = next((p for p in self._saved_patients if p['id'] == patient_id), None)
        if snapshot:
            p = snapshot.get('patient', {})
            log_record_loaded(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'), 'sample')
            self._load_snapshot(snapshot)

    def _view_saved_sample_result(self, patient_id):
        snapshot = next((p for p in self._saved_patients if p['id'] == patient_id), None)
        if snapshot:
            p = snapshot.get('patient', {})
            log_record_loaded(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'), 'view_result')
            self._show_snapshot_result(snapshot)

    def _print_saved_sample(self, patient_id):
        snapshot = next((p for p in self._saved_patients if p['id'] == patient_id), None)
        if snapshot:
            p = snapshot.get('patient', {})
            log_report_printed(p.get('pid', 'N/A'), p.get('name', 'N/A'))
            self._open_report_in_browser(snapshot)

    def _load_draft(self, patient_id):
        snapshot = next((p for p in self._drafts if p['id'] == patient_id), None)
        if not snapshot:
            return
        p = snapshot.get('patient', {})
        log_record_loaded(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'), 'draft')
        self._load_snapshot(snapshot)

    def _load_snapshot(self, snapshot):
        if hasattr(self, '_report_snapshot'):
            delattr(self, '_report_snapshot')
        self._active_record_id = snapshot.get('id')
        self._active_record_source = snapshot.get('record_type', 'sample')
        self._scheme_rows_cache = {}
        # Restore sampling mode (multi / direct)
        saved_mode = snapshot.get('sampling_mode', 'multi')
        self._switch_sampling_mode(saved_mode)
        if saved_mode == 'direct':
            self._toggle_direct.setChecked(True)
            self._direct_auc_edit.setText(snapshot.get('direct_auc', ''))
        else:
            self._toggle_multi.setChecked(True)
        self._set_duration_options(snapshot.get('duration_options', self._global_duration_options), selected=snapshot.get('scheme', 4))
        patient = snapshot.get('patient', {})
        self.f_name.setText(patient.get('name', '') if patient.get('name') != 'N/A' else '')
        self.f_age.setText(patient.get('age', '') if patient.get('age') != 'N/A' else '')
        self.f_weight.setText(patient.get('weight', '') if patient.get('weight') != 'N/A' else '')
        self.f_hosp_no.setText(patient.get('hosp_id', '') if patient.get('hosp_id') != 'N/A' else '')
        self.f_ward.setText(patient.get('ward', '') if patient.get('ward') != 'N/A' else '')
        self.f_dept.setText(patient.get('dept', '') if patient.get('dept') != 'N/A' else '')
        sex_value = patient.get('sex', '').strip()
        sex_index = self.f_sex.findText(sex_value) if sex_value else 0
        self.f_sex.setCurrentIndex(sex_index if sex_index >= 0 else 0)
        self.f_diag.setText(patient.get('diag', 'Post Renal Transplant') if patient.get('diag') != 'N/A' else 'Post Renal Transplant')
        self.f_drug.setCurrentText(patient.get('drug', 'MPA'))
        self.f_preparation.setText(patient.get('preparation', 'Mycophenolate Mofetil (MMF)'))
        self.f_dose.setText(patient.get('dose', '540mg - 720mg') if patient.get('dose') != 'N/A' else '')
        tx_date = QDate.fromString(patient.get('tx_date', ''), "dd.MM.yyyy")
        self.f_tx_date.setDate(tx_date if tx_date.isValid() else QDate.currentDate())
        dose_dt_text = patient.get('dose_dt', '')
        dose_dt = QDateTime.fromString(dose_dt_text, "dd.MM.yyyy 'at' hh:mmAP")
        if not dose_dt.isValid():
            dose_dt = QDateTime.fromString(dose_dt_text, "dd.MM.yy 'at' hh:mmAP")
        if dose_dt.isValid():
            self.f_dose_dt.setDateTime(dose_dt)
        sample_date_text = patient.get('sample_collection_date', '')
        sample_dt = QDate.fromString(sample_date_text, "dd.MM.yyyy")
        if not sample_dt.isValid():
            sample_dt = QDate.fromString(sample_date_text, "dd.MM.yy")
        if sample_dt.isValid():
            self.f_sample_collection_date.setDate(sample_dt)

        self.f_med.clear_selection()
        meds = patient.get('med', '')
        if meds and meds != 'N/A':
            for med in [m.strip() for m in meds.split(',') if m.strip()]:
                self.f_med._add_tag(med)

        scheme = snapshot.get('scheme', 4)
        rows_payload = snapshot.get('sample_rows')
        if rows_payload:
            self._current_scheme = scheme
            self.sample_table.set_rows_payload(rows_payload)
            self._scheme_rows_cache[scheme] = rows_payload
            self.trough_edit.setText(snapshot.get('trough', ''))
        else:
            times = snapshot.get('times', [])
            concs = snapshot.get('concs', [])
            if times:
                if times[0] == 0 and concs:
                    self.trough_edit.setText("" if concs[0] is None else str(concs[0]))
                    self.sample_table.set_data(times[1:], concs[1:])
                    self._scheme_rows_cache[scheme] = self.sample_table.get_rows_payload()
                else:
                    self.trough_edit.clear()
                    self.sample_table.set_data(times, concs)
                    self._scheme_rows_cache[scheme] = self.sample_table.get_rows_payload()
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
            self._last_drug = canonical_drug_name(patient.get('drug', 'MPA'))
        else:
            for attr in ['_last_pk', '_last_times', '_last_concs', '_last_interp', '_last_drug']:
                if hasattr(self, attr):
                    delattr(self, attr)
        self._loaded_form_signature = self._form_signature()
        self._update_action_buttons()
        self._switch_page(0)
        self._switch_report_step(1)

    def _delete_saved_patient(self, patient_id):
        snapshot = next((p for p in self._saved_patients if p['id'] == patient_id), None)
        if snapshot:
            p = snapshot.get('patient', {})
            log_record_deleted(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'))
        delete_record(patient_id)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._show_toast("Deleted successfully", "Sample removed from Sample List.")

    def _delete_draft(self, patient_id):
        snapshot = next((p for p in self._drafts if p['id'] == patient_id), None)
        if snapshot:
            p = snapshot.get('patient', {})
            log_record_deleted(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'))
        delete_record(patient_id)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._show_toast("Deleted successfully", "Draft removed from Draft List.")

    def _show_snapshot_result(self, snapshot):
        pk = snapshot.get('pk')
        if not pk:
            QMessageBox.information(self, "No Report Yet", "Generate a report for this sample first.")
            return
        self._reset_to_sample_list_on_result_close = False
        self._report_snapshot = snapshot
        self._last_pk = pk
        self._last_times = snapshot.get('times', [])
        self._last_concs = snapshot.get('concs', [])
        self._last_interp = snapshot.get('interp', 'N/A')
        self._last_drug = canonical_drug_name(snapshot.get('patient', {}).get('drug', 'MPA'))
        self._apply_results(pk, self._last_interp)

    def _capture_report_graph_uri(self):
        if self._results_dialog is None:
            return None
        buf = BytesIO()
        self._results_dialog.canvas.fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    def _save_report_file(self, snapshot, graph_uri=None):
        try:
            from report_print import build_report_html
            reports_dir = Path(__file__).resolve().with_name("generated_reports")
            reports_dir.mkdir(exist_ok=True)
            report_path = reports_dir / f"{snapshot['id']}.html"
            html = build_report_html(
                patient=snapshot.get('patient', {}),
                pk=snapshot.get('pk', {}),
                interp=snapshot.get('interp', 'N/A'),
                times=snapshot.get('times', []),
                concs=snapshot.get('concs', []),
                graph_uri=graph_uri,
            )
            report_path.write_text(html, encoding="utf-8")
            snapshot['report_path'] = str(report_path)
            return str(report_path)
        except Exception as e:
            log_error("_save_report_file", e)
            self._show_toast(
                "Report file not saved",
                "Result is saved to the database but the print file could not be written.",
                tone="error",
            )
            return None

    def _open_report_in_browser(self, snapshot):
        pk = snapshot.get('pk')
        if not pk:
            QMessageBox.information(self, "No Report Yet", "Generate a report for this sample first.")
            return
        report_path = snapshot.get('report_path')
        if not report_path or not Path(report_path).exists():
            QMessageBox.information(
                self,
                "Saved Report Not Found",
                "This sample does not have a previously saved print file yet. Please generate the report again once to save the exact print version.",
            )
            return
        webbrowser.open(Path(report_path).as_uri())

    def _apply_results(self, pk, interp):
        if self._results_dialog is None:
            self._results_dialog = ResultsDialog(self, print_handler=self._print_report)
            self._results_dialog.finished.connect(self._on_results_dialog_closed)
        _times = getattr(self, '_last_times', None)
        _concs = getattr(self, '_last_concs', None)
        self._results_dialog.apply_results(pk, interp, times=_times, concs=_concs)
        has_data = bool(_times and _concs)
        self._results_dialog.set_graph_visible(has_data)
        if has_data:
            drug_name = getattr(self, '_last_drug', 'MPA')
            self._results_dialog.plot_data(_times, _concs, drug=drug_name)
        self._results_dialog.show()
        self._results_dialog.raise_()
        self._results_dialog.activateWindow()

    def _on_results_dialog_closed(self, _result):
        if not getattr(self, '_reset_to_sample_list_on_result_close', False):
            return
        self._clear_form_state(close_results=False)
        if hasattr(self, '_report_snapshot'):
            delattr(self, '_report_snapshot')
        for attr in ['_last_pk', '_last_times', '_last_concs', '_last_interp', '_last_drug']:
            if hasattr(self, attr):
                delattr(self, attr)
        self._switch_page(1)
        if hasattr(self, '_main_scroll'):
            self._main_scroll.verticalScrollBar().setValue(0)
        self._reset_to_sample_list_on_result_close = False

    # ──────────────────────────────────────
    # Calculate
    # ──────────────────────────────────────
    def _calculate(self):
        if hasattr(self, '_report_snapshot'):
            delattr(self, '_report_snapshot')

        drug = canonical_drug_name(self.f_drug.currentText().strip() or 'MPA')

        # ── Direct AUC mode ───────────────────────────────────────────
        if getattr(self, '_sampling_mode', 'multi') == 'direct':
            try:
                auc_val = float(self._direct_auc_edit.text().strip())
                if auc_val <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Invalid Value",
                                    "Please enter a valid AUC value (mg·h/L).")
                return
            pk = {
                'auc_0_last': auc_val,
                'auc_0_12':   auc_val,
                'auc_lss':    auc_val,
                'lss_equation': 'Direct input (mg·h/L)',
                'lambda_z':   None,
                't_half':     None,
                'r_squared':  None,
                't_last':     0.0,
                'c_trough':   None,
                'c_last':     None,
            }
            interp, _ = interpret_result(drug, auc_val)
            self._last_pk    = pk
            self._last_times = []
            self._last_concs = []
            self._last_interp = interp
            self._last_drug  = drug
            p = self._patient_payload()
            log_report_generated(p.get('pid', 'N/A'), p.get('name', 'N/A'), drug, auc_val)
            self._apply_results(pk, interp)
            snapshot = self._snapshot_payload()
            existing_id = getattr(self, '_active_record_id', None)
            if existing_id:
                snapshot['id'] = existing_id
            # Save report file (no graph for direct AUC mode)
            saved_path = self._save_report_file(snapshot, graph_uri=None)
            snapshot['report_path'] = saved_path or ''
            if getattr(self, '_active_record_source', None) == 'draft' and existing_id:
                delete_record(existing_id)
            save_record(snapshot, 'sample')
            self._report_snapshot = snapshot
            self._active_record_id = snapshot['id']
            self._active_record_source = 'sample'
            self._loaded_form_signature = self._form_signature()
            self._load_saved_patients()
            self._refresh_patients_list()
            self._reset_to_sample_list_on_result_close = True
            return
        # ─────────────────────────────────────────────────────────────

        times, concs = self._read_table(skip_empty=False)

        if times is None or len(times) < 3:
            QMessageBox.warning(
                self, "Insufficient Data",
                "Please enter at least the trough + 2 post-dose concentrations."
            )
            return
        if any(b <= a for a, b in zip(times, times[1:])):
            QMessageBox.warning(
                self,
                "Invalid Sample Times",
                "Sample times must be strictly increasing without duplicates.",
            )
            return
        pk = calculate_auc_full(times, concs)

        # LSS estimate — only show when drug-specific equation matches (not generic ANY)
        lss = calculate_lss_auc(times, concs, cni=drug)
        if lss and drug.upper() in lss['equation_label'].upper():
            pk['auc_lss']       = lss['auc_lss']
            pk['lss_equation']  = lss['equation_label']
            pk['lss_r2']        = lss['r2']

        # Interpretation — use auc_lss when available (validated equation),
        # fall back to auc_0_12 (trapezoidal extrapolation) otherwise.
        interp_value = pk.get('auc_lss') if pk.get('auc_lss') is not None else pk['auc_0_12']
        interp, _ = interpret_result(drug, interp_value)
        self._last_pk = pk
        self._last_times = times
        self._last_concs = concs
        self._last_interp = interp
        self._last_drug = drug
        p = self._patient_payload()
        log_report_generated(
            p.get('pid', 'N/A'), p.get('name', 'N/A'),
            drug, pk.get('auc_0_12'),
        )
        self._apply_results(pk, interp)

        # Auto-save after generating report
        snapshot = self._snapshot_payload()
        existing_id = getattr(self, '_active_record_id', None)
        was_updating = getattr(self, '_active_record_source', None) == 'sample' and bool(existing_id)
        if existing_id:
            snapshot['id'] = existing_id  # reuse id to replace, not duplicate
        saved_path = self._save_report_file(
            snapshot,
            graph_uri=self._capture_report_graph_uri(),
        )
        snapshot['report_path'] = saved_path or ''
        if getattr(self, '_active_record_source', None) == 'draft' and existing_id:
            delete_record(existing_id)
        save_record(snapshot, 'sample')
        self._report_snapshot = snapshot
        self._active_record_id = snapshot['id']
        self._active_record_source = 'sample'
        self._loaded_form_signature = self._form_signature()
        self._load_saved_patients()
        self._refresh_patients_list()
        if self._results_dialog is not None:
            if was_updating:
                self._results_dialog.show_toast("Report updated", "Generated result has been updated successfully.")
            else:
                self._results_dialog.show_toast("Report generated", "Generated result has been saved successfully.")
        self._reset_to_sample_list_on_result_close = True

    # ──────────────────────────────────────
    # Print / PDF
    # ──────────────────────────────────────
    def _print_report(self):
        if not hasattr(self, '_last_pk'):
            return
        if hasattr(self, '_report_snapshot'):
            self._open_report_in_browser(self._report_snapshot)
            self._switch_page(1)
            if hasattr(self, '_main_scroll'):
                self._main_scroll.verticalScrollBar().setValue(0)
            return
        snapshot = self._snapshot_payload()
        existing_id = getattr(self, '_active_record_id', None)
        if existing_id:
            snapshot['id'] = existing_id
        report_path = self._save_report_file(
            snapshot,
            graph_uri=self._capture_report_graph_uri(),
        )
        webbrowser.open(Path(report_path).as_uri())
        self._switch_page(1)
        if hasattr(self, '_main_scroll'):
            self._main_scroll.verticalScrollBar().setValue(0)

    # ──────────────────────────────────────
    # Reset
    # ──────────────────────────────────────
    def _clear_form_state(self, close_results=True):
        self._active_record_id = None
        self._active_record_source = None
        self._loaded_form_signature = None
        self._reset_to_sample_list_on_result_close = False
        self._current_scheme = None
        self._scheme_rows_cache = {}
        default_duration = self._global_duration_options[0] if self._global_duration_options else 4
        self._set_duration_options(self._global_duration_options, selected=default_duration)
        # Reset sampling mode to multi-point
        self._switch_sampling_mode('multi')
        self._toggle_multi.setChecked(True)
        self._direct_auc_edit.clear()
        if close_results and hasattr(self, '_report_snapshot'):
            delattr(self, '_report_snapshot')
        for edit in [self.f_name, self.f_age, self.f_weight, self.f_hosp_no,
                     self.f_ward, self.f_dept, self.f_dose,
                     self.f_diag, self.trough_edit]:
            edit.clear()
        self.f_drug.setCurrentIndex(0)
        self.f_preparation.setText("Mycophenolate Mofetil (MMF)")
        self.f_diag.setText("Post Renal Transplant")
        self.f_sex.setCurrentIndex(0)
        self.f_med.clear_selection()
        self.f_tx_date.setDate(QDate.currentDate())
        self.f_dose_dt.setDateTime(QDateTime.currentDateTime())
        self.f_sample_collection_date.setDate(QDate.currentDate())
        self._populate_table(default_duration)
        self._scheme_rows_cache[default_duration] = self.sample_table.get_rows_payload()
        self._update_action_buttons()
        self._switch_report_step(0)
        if close_results and self._results_dialog is not None:
            self._results_dialog.close()
        if close_results:
            for attr in ['_last_pk', '_last_times', '_last_concs', '_last_interp', '_last_drug']:
                if hasattr(self, attr):
                    delattr(self, attr)

    def _reset(self):
        self._clear_form_state()
        self._switch_page(0)
        if hasattr(self, '_main_scroll'):
            self._main_scroll.verticalScrollBar().setValue(0)
