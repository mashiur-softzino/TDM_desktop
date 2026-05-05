"""
TDM Report — Therapeutic Drug Monitoring
Main window only. All helper classes/constants are in ui_constants, ui_widgets,
ui_sampling, and ui_patients.
"""

import sys
from app_logger import (
    log_report_generated, log_draft_saved,
    log_record_loaded, log_record_deleted, log_report_printed, log_error,
)
from database import (
    init_db, save_record, delete_record, load_all, migrate_from_json,
    load_duration_options, save_duration_options, load_medications,
    add_medication, update_medication, delete_medication,
    load_doctors, add_doctor, update_doctor, delete_doctor, get_doctor_by_id
)
import tempfile
import webbrowser
import base64
from io import BytesIO
from datetime import datetime
from pathlib import Path

from ui_constants import (BLUE, LABEL_CLR, TEXT_CLR, BORDER, RED,
                           DEFAULT_DURATION_OPTIONS,
                           BASE_SAMPLE_TIMES, PATIENTS_FILE, STYLE,
                           sampling_times_for_duration, make_shadow, small_label)
from ui_widgets import (Card, DurationEditModal, DurationChip,
                        NoWheelComboBox, SmartDateEdit, SmartDateTimeEdit,
                        ToastMessage, ConfirmActionModal)
from ui_sampling import ModernSampleTable, MedicationSelector
from ui_patients import ResultsDialog, PatientRow, PatientsListCard, DoctorRow, DoctorsListCard

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QMessageBox, QDialog, QComboBox,
    QSizePolicy, QGridLayout,
    QStackedWidget, QListWidget, QListWidgetItem, QDialogButtonBox, QFileDialog,
    QPlainTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QDate, QDateTime, QObject, QEvent, QSize, QRegularExpression, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush, QPen, QPalette, QIntValidator, QRegularExpressionValidator, QPixmap, QImage, QDoubleValidator
import qtawesome as qta
from calculations import calculate_auc_full, calculate_lss_auc, interpret_result, canonical_drug_name

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
        self.page_stack.addWidget(self._build_doctors_page())
        self.page_stack.addWidget(self._build_settings_page())
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
        patient_step_lay.addWidget(self._make_signature_card())

        patient_actions = QHBoxLayout()
        patient_actions.addStretch()
        self.draft_btn = QPushButton("Draft")
        self.draft_btn.setObjectName("printBtn")
        self.draft_btn.setFixedHeight(40)
        self.draft_btn.setEnabled(False)
        self.draft_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.draft_btn.clicked.connect(self._save_draft)
        patient_actions.addWidget(self.draft_btn)

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

        self.sampling_draft_btn = QPushButton("Draft")
        self.sampling_draft_btn.setObjectName("printBtn")
        self.sampling_draft_btn.setFixedHeight(40)
        self.sampling_draft_btn.setEnabled(False)
        self.sampling_draft_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.sampling_draft_btn.clicked.connect(self._save_draft)
        calc_row.addWidget(self.sampling_draft_btn)

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
        self.sample_list_card.page_changed.connect(self._refresh_patients_list)
        lay.addWidget(self.sample_list_card)
        return page

    def _build_drafts_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.draft_list_card = PatientsListCard("Draft List", "No drafts yet.", action_width=84, row_type='draft')
        self.draft_list_card.search_changed.connect(lambda _: self._refresh_patients_list())
        self.draft_list_card.page_changed.connect(self._refresh_patients_list)
        lay.addWidget(self.draft_list_card)
        return page

    def _build_doctors_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)
        self.doctor_list_card = DoctorsListCard()
        self.doctor_list_card.search_changed.connect(self._on_doctor_search_changed)
        self.doctor_list_card.page_changed.connect(lambda: self._refresh_doctors_list())
        self.doctor_list_card._add_btn.clicked.connect(self._add_doctor_from_list)
        lay.addWidget(self.doctor_list_card)
        return page

    def _on_doctor_search_changed(self, _):
        self.doctor_list_card._page_index = 0
        self._refresh_doctors_list()

    def _build_settings_page(self):
        from db_config import load_db_config, save_db_config
        import psycopg2

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)

        card = Card("Database Connection", "mdi6.database-cog-outline", icon_color="#334155")

        field_style = f"""
            QLineEdit {{
                background: #F7FAFE;
                border: 1.5px solid #D6E2EE;
                border-radius: 14px;
                padding: 12px 16px;
                font-size: 14px;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
            QLineEdit::placeholder {{
                color: rgba(0, 0, 0, 0.22);
            }}
        """

        cfg = load_db_config()

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setHorizontalSpacing(18)

        def make_field(placeholder, value='', password=False):
            f = QLineEdit(value)
            f.setPlaceholderText(placeholder)
            f.setStyleSheet(field_style)
            if password:
                f.setEchoMode(QLineEdit.EchoMode.Password)
            return f

        host_lbl = small_label("HOST", color="#111111", size=12, bold=True)
        self._db_host = make_field("e.g. localhost", cfg.get('host', 'localhost'))
        host_col = QVBoxLayout()
        host_col.setSpacing(6)
        host_col.addWidget(host_lbl)
        host_col.addWidget(self._db_host)

        port_lbl = small_label("PORT", color="#111111", size=12, bold=True)
        self._db_port = make_field("e.g. 5432", cfg.get('port', '5432'))
        port_col = QVBoxLayout()
        port_col.setSpacing(6)
        port_col.addWidget(port_lbl)
        port_col.addWidget(self._db_port)

        db_lbl = small_label("DATABASE NAME", color="#111111", size=12, bold=True)
        self._db_name = make_field("e.g. tdm_db", cfg.get('database', 'tdm_db'))
        db_col = QVBoxLayout()
        db_col.setSpacing(6)
        db_col.addWidget(db_lbl)
        db_col.addWidget(self._db_name)

        user_lbl = small_label("USERNAME", color="#111111", size=12, bold=True)
        self._db_user = make_field("e.g. postgres", cfg.get('username', 'postgres'))
        user_col = QVBoxLayout()
        user_col.setSpacing(6)
        user_col.addWidget(user_lbl)
        user_col.addWidget(self._db_user)

        pass_lbl = small_label("PASSWORD", color="#111111", size=12, bold=True)
        self._db_pass = make_field("Enter password", cfg.get('password', ''), password=True)
        pass_col = QVBoxLayout()
        pass_col.setSpacing(6)
        pass_col.addWidget(pass_lbl)
        pass_col.addWidget(self._db_pass)

        grid.addLayout(host_col, 0, 0)
        grid.addLayout(port_col, 0, 1)
        grid.addLayout(db_col,   1, 0)
        grid.addLayout(user_col, 1, 1)
        grid.addLayout(pass_col, 2, 0)

        self._db_status_lbl = QLabel("")
        self._db_status_lbl.setStyleSheet("font-size: 13px; padding: 4px 0;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        test_btn = QPushButton("Test Connection")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet("""
            QPushButton {
                background: #EFF6FF; color: #2563EB;
                border: 1.5px solid #BFDBFE; border-radius: 12px;
                padding: 10px 20px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #DBEAFE; }
        """)

        save_btn = QPushButton("Save & Apply")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #166534; color: white;
                border: none; border-radius: 12px;
                padding: 10px 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #15803D; }
        """)

        def _get_config():
            return {
                'host':     self._db_host.text().strip(),
                'port':     self._db_port.text().strip(),
                'database': self._db_name.text().strip(),
                'username': self._db_user.text().strip(),
                'password': self._db_pass.text(),
            }

        def _test_connection():
            c = _get_config()
            try:
                conn = psycopg2.connect(
                    host=c['host'], port=int(c['port']),
                    dbname=c['database'], user=c['username'],
                    password=c['password'] or None, connect_timeout=5,
                )
                conn.close()
                self._db_status_lbl.setText("✓ Connection successful")
                self._db_status_lbl.setStyleSheet("font-size: 13px; color: #166534; font-weight: bold; padding: 4px 0;")
            except Exception as e:
                self._db_status_lbl.setText(f"✗ Failed: {e}")
                self._db_status_lbl.setStyleSheet("font-size: 13px; color: #DC2626; padding: 4px 0;")

        def _save_and_reconnect():
            c = _get_config()
            try:
                conn = psycopg2.connect(
                    host=c['host'], port=int(c['port']),
                    dbname=c['database'], user=c['username'],
                    password=c['password'] or None, connect_timeout=5,
                )
                conn.close()
            except Exception as e:
                self._db_status_lbl.setText(f"✗ Cannot save — connection failed: {e}")
                self._db_status_lbl.setStyleSheet("font-size: 13px; color: #DC2626; padding: 4px 0;")
                return
            save_db_config(c)
            self._db_status_lbl.setText("✓ Saved & reconnected successfully")
            self._db_status_lbl.setStyleSheet("font-size: 13px; color: #166534; font-weight: bold; padding: 4px 0;")

        test_btn.clicked.connect(_test_connection)
        save_btn.clicked.connect(_save_and_reconnect)

        btn_row.addWidget(test_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()

        body = QVBoxLayout()
        body.setSpacing(16)
        body.addLayout(grid)
        body.addWidget(self._db_status_lbl)
        body.addLayout(btn_row)

        card.body().addLayout(body)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _add_doctor_from_list(self):
        dlg = DoctorEditModal(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_doctors_list()
            self._refresh_doctor_combos()

    _DOC_PAGE_SIZE = 10

    def _refresh_doctors_list(self):
        if not hasattr(self, 'doctor_list_card'): return
        self.doctor_list_card.clear_rows()
        doctors = load_doctors()
        query = self.doctor_list_card.search_text()
        filtered = [d for d in doctors if query in d['name'].lower() or query in (d.get('phone') or '').lower()]
        
        self.doctor_list_card.set_count(len(filtered))
        
        if not filtered:
            self.doctor_list_card.set_empty_text("No data found" if query else None)
            self.doctor_list_card.set_empty_visible(True)
            return
            
        self.doctor_list_card.set_empty_visible(False)
        
        visible = filtered
        page_count = max(1, (len(visible) + self._DOC_PAGE_SIZE - 1) // self._DOC_PAGE_SIZE)
        self.doctor_list_card.clamp_page_index(page_count)
        page_index = self.doctor_list_card.page_index()
        start = page_index * self._DOC_PAGE_SIZE
        page_items = visible[start:start + self._DOC_PAGE_SIZE]
        
        for i, doc in enumerate(page_items, start + 1):
            row = DoctorRow(doc, serial_no=i)
            row.edit_requested.connect(self._edit_doctor_from_list)
            row.delete_requested.connect(self._delete_doctor_from_list)
            self.doctor_list_card.add_row(row)
        
        self.doctor_list_card.set_pagination(page_index, page_count, len(visible), self._DOC_PAGE_SIZE)

    def _edit_doctor_from_list(self, doctor):
        dlg = DoctorEditModal(doctor, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_doctors_list()
            self._refresh_doctor_combos()

    def _delete_doctor_from_list(self, doctor):
        dlg = ConfirmActionModal(
            "Delete Signatory",
            f"Are you sure you want to delete \"{doctor['name']}\" from the Signatory List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from database import delete_doctor
        delete_doctor(doctor['id'])
        self._refresh_doctors_list()
        self._refresh_doctor_combos()

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

        self.doctors_tab_btn = QPushButton("Signatory List")
        self.doctors_tab_btn.setObjectName("mainTab")
        self.doctors_tab_btn.setIcon(qta.icon("mdi6.account-group-outline", color="#718096"))
        self.doctors_tab_btn.clicked.connect(lambda: self._switch_page(3))

        self.settings_tab_btn = QPushButton("Settings")
        self.settings_tab_btn.setObjectName("mainTab")
        self.settings_tab_btn.setIcon(qta.icon("mdi6.cog-outline", color="#718096"))
        self.settings_tab_btn.clicked.connect(lambda: self._switch_page(4))

        for btn in [self.report_tab_btn, self.patients_tab_btn, self.drafts_tab_btn,
                    self.doctors_tab_btn, self.settings_tab_btn]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFlat(True)
            btn.setMinimumWidth(122)

        shell_lay.addWidget(self.patients_tab_btn)
        shell_lay.addWidget(self.drafts_tab_btn)
        shell_lay.addWidget(self.doctors_tab_btn)
        shell_lay.addWidget(self.settings_tab_btn)

        row.addWidget(shell)
        row.addStretch()
        return wrap

    def _switch_page(self, index):
        if index == 1 and hasattr(self, 'sample_list_card'):
            self.sample_list_card.clear_search()
        elif index == 2 and hasattr(self, 'draft_list_card'):
            self.draft_list_card.clear_search()
        elif index == 3 and hasattr(self, 'doctor_list_card'):
            self.doctor_list_card._search_edit.clear()
            self._refresh_doctors_list()
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
        self.doctors_tab_btn.setChecked(index == 3)
        self.settings_tab_btn.setChecked(index == 4)
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
                'doctor': {
                    'bg': "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F5F3FF, stop:1 #EDE9FE)",
                    'border': "#C4B5FD",
                    'color': "#5B21B6",
                    'hover': "#F5F3FF",
                },
                'settings': {
                    'bg': "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F8FAFC, stop:1 #F1F5F9)",
                    'border': "#CBD5E1",
                    'color': "#334155",
                    'hover': "#F8FAFC",
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
        self.doctors_tab_btn.setStyleSheet(tab_style('doctor', index == 3))
        self.settings_tab_btn.setStyleSheet(tab_style('settings', index == 4))

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
        title_col = QHBoxLayout()
        title_col.setSpacing(0)
        t1 = QLabel("Therapeutic Drug Monitoring")
        t1.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 700; "
            "letter-spacing: 0.3px; background: transparent;"
        )
        title_col.addWidget(t1)
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
        mark.setFixedSize(118, 24)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        logo_path = logo_base / "softzino.png"
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
            mark.setPixmap(cleaned.scaled(118, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        mark.setStyleSheet("background: transparent;")
        lay.addWidget(mark)

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
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit:hover {{
                border: 1.5px solid #C3D6EA;
                background: white;
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BLUE};
                background: white;
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit::placeholder {{
                color: rgba(0, 0, 0, 0.22);
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
                selection-background-color: {BLUE};
                selection-color: white;
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

        self.f_name      = field("Enter patient name")
        self.f_age       = field("e.g. 45")
        self.f_name.setMaxLength(30)
        self.f_age.setMaxLength(3)
        self.f_age.setValidator(QIntValidator(0, 150, self))
        self.f_hosp_no     = field("Enter invoice number")
        self.f_invoice_date = SmartDateEdit(initial_date=QDate.currentDate())
        self.f_report_no   = field("Enter report number")
        self.f_referred_by = field("Enter referred by")
        self.f_delivery_date = SmartDateEdit(initial_date=QDate.currentDate())
        self.f_invoice_date.dateChanged.connect(lambda *_: self._on_data_changed())
        self.f_delivery_date.dateChanged.connect(lambda *_: self._on_data_changed())

        self.f_diag    = field("e.g. Post Renal Transplant")
        self.f_diag.setText("Post Renal Transplant")
        self.f_phone   = field("Enter phone number")
        self.f_phone.setMaxLength(11)
        self.f_phone.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,11}"), self.f_phone))
        for edit in [self.f_name, self.f_age, self.f_hosp_no, self.f_report_no, self.f_referred_by, self.f_diag, self.f_phone]:
            edit.textChanged.connect(self._on_data_changed)

        # Sex selector
        self.f_sex = NoWheelComboBox()
        self.f_sex.addItems(["Choose a gender", "Male", "Female", "Other"])
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
                lbl.setStyleSheet("color: #111111; font-size: 12px; font-weight: bold; letter-spacing: 0.8px;")
                col_lbl.addWidget(lbl)
            else:
                col_lbl.addWidget(small_label(label, color="#111111", size=12, bold=True))
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
        for col in range(4):
            demo_grid.setColumnStretch(col, 1)

        # Row 0: Patient Name | Age | Gender | Referred By
        add_field(demo_grid, 0, 0, "Patient Name", self.f_name)
        add_field(demo_grid, 0, 1, "Age (Years)", self.f_age)
        add_field(demo_grid, 0, 2, "Gender", self.f_sex)
        add_field(demo_grid, 0, 3, "Referred By", self.f_referred_by)

        # Row 1: Invoice Number | Invoice Date | Report Number | Delivery Date
        add_field(demo_grid, 1, 0, "Invoice Number", self.f_hosp_no)
        add_field(demo_grid, 1, 1, "Invoice Date", self.f_invoice_date)
        add_field(demo_grid, 1, 2, "Report Number", self.f_report_no)
        add_field(demo_grid, 1, 3, "Delivery Date", self.f_delivery_date)

        # Row 2: Phone Number
        add_field(demo_grid, 2, 0, "Phone Number", self.f_phone)

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

        # ── Two-column layout ──────────────────────────────────
        # Left col : DATE OF TRANSPLANT (top) + DIAGNOSIS (below) — never moves
        # Right col: MEDICATIONS — height is stable because _tags_scroll is always visible
        two_col = QHBoxLayout()
        two_col.setSpacing(20)
        two_col.setContentsMargins(0, 0, 0, 0)

        # Left column — Date of Transplant + Diagnosis, independent of medications
        left_col = QVBoxLayout()
        left_col.setSpacing(16)
        left_col.setContentsMargins(0, 0, 0, 0)

        date_section = QVBoxLayout()
        date_section.setSpacing(8)
        date_section.addWidget(small_label("Date of Transplant", color="#111111", size=12, bold=True))
        self.f_tx_date.setMinimumWidth(400)
        self.f_tx_date.setMaximumWidth(400)
        date_section.addWidget(self.f_tx_date)
        left_col.addLayout(date_section)

        diag_section = QVBoxLayout()
        diag_section.setSpacing(6)
        diag_section.addWidget(small_label("Diagnosis", color="#111111", size=12, bold=True))
        self.f_diag.setMinimumWidth(400)
        self.f_diag.setMaximumWidth(400)
        self.f_diag.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        diag_section.addWidget(self.f_diag)
        left_col.addLayout(diag_section)
        left_col.addStretch()

        two_col.addLayout(left_col)

        # Right column — Medications (height stable: _tags_scroll always visible)
        med_col = QVBoxLayout()
        med_col.setSpacing(8)
        med_col.setContentsMargins(0, 0, 0, 0)
        med_col.addWidget(small_label("Medications", color="#111111", size=12, bold=True))
        self.f_med.setMinimumWidth(400)
        self.f_med.setMaximumWidth(400)
        med_col.addWidget(self.f_med, 0, Qt.AlignmentFlag.AlignTop)
        med_col.addStretch()

        two_col.addLayout(med_col)
        two_col.addStretch(1)

        clinical_lay.addLayout(two_col)

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
                selection-background-color: {BLUE};
                selection-color: white;
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
                color: rgba(0, 0, 0, 0.22);
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

        self.f_drug = field("")
        self.f_drug.setText("MPA")
        self.f_drug.setReadOnly(True)

        self.f_preparation = field("e.g. Mycept-5")
        self.f_preparation.setText("Mycophenolate Mofetil")
        self.f_dose = field("e.g. 540 mg - 720 mg")
        self.f_dose.setMaxLength(50)
        for edit in [self.f_preparation, self.f_dose]:
            edit.textChanged.connect(self._on_data_changed)
        self.f_dose_dt = SmartDateTimeEdit()
        self.f_dose_dt.dateTimeChanged.connect(lambda *_: self._on_data_changed())
        self.f_dose_dt.dateTimeChanged.connect(lambda *_: self._update_action_buttons())
        self.f_sample_collection_date = SmartDateEdit(initial_date=QDate.currentDate())
        self.f_sample_collection_date.dateChanged.connect(lambda *_: self._on_data_changed())
        self.f_sample_collection_date.dateChanged.connect(self._update_tx_duration)
        self.f_tx_date.dateChanged.connect(self._update_tx_duration)

        self.f_tx_duration = field("Calculated automatically")
        self.f_tx_duration.setReadOnly(True)
        self.f_tx_duration.setPlaceholderText("Duration will appear here")

        def add_meta(row, col, label, widget, required=False):
            col_lay = QVBoxLayout()
            col_lay.setSpacing(7)
            if required:
                lbl = QLabel(f'{label.upper()} <span style="color:#E53935;">*</span>')
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setStyleSheet("color: #111111; font-size: 12px; font-weight: bold; letter-spacing: 0.8px;")
            else:
                lbl = small_label(label, color="#111111", size=12, bold=True)
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
        add_meta(0, 3, "Date & Time of Dose", self.f_dose_dt)
        add_meta(1, 0, "Sample Collection Date", self.f_sample_collection_date)
        add_meta(1, 1, "Time Duration (Post-Tx)", self.f_tx_duration)
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
            color="#111111", size=12, bold=True, uppercase=False
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
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit:focus {{ border: 2px solid #EA580C; }}
        """)
        self._direct_auc_edit.setValidator(QDoubleValidator(0.0, 1000.0, 2))
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
        trough_col.addWidget(small_label("Trough (Pre-dose) Concentration (µg/mL)", color="#111111", size=12, bold=True, uppercase=False))
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
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QLineEdit:focus {{
                border: 2px solid #EA580C;
            }}
        """)
        self.trough_edit.setValidator(QDoubleValidator(0.0, 1000.0, 3))
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
        dur_col.addWidget(small_label("Number of Samples", color="#111111", size=12, bold=True))
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
        table_col.addWidget(small_label("Sample Points", color="#111111", size=12, bold=True))
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
        dlg = DurationEditModal("Add Sample Points", "Save", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = dlg.get_value()
        if not candidate:
            self._show_toast("Invalid sample points", "Sample points must be between 2 and 12.", tone="warning")
            return
        if candidate in self._duration_options:
            self._show_toast("Already added", f"{candidate} sample points is already added", tone="warning")
            return
        self._duration_options.insert(0, candidate)
        self._scheme_rows_cache[candidate] = self._rows_payload_for_duration(candidate)
        self._set_duration_options(self._duration_options, selected=candidate)
        self._populate_table(candidate)
        self._on_data_changed()
        self._show_toast("Sample points added", f"{candidate} Sample points is added")


    # ──────────────────────────────────────
    # Doctor Signatures
    # ──────────────────────────────────────
    def _make_signature_card(self):
        card = Card("Signature Section", "mdi6.fountain-pen-tip", icon_color="#0F766E")
        lay = QVBoxLayout()
        lay.setSpacing(20)
        
        row = QHBoxLayout()
        row.setSpacing(16)

        import tempfile, os
        _arrow_path = os.path.join(tempfile.gettempdir(), "tdm_sig_arrow_down.png")
        qta.icon("mdi6.chevron-down", color="#166534").pixmap(14, 14).save(_arrow_path)
        _arrow_path = _arrow_path.replace("\\", "/")
        
        combo_style = f"""
            QComboBox {{
                background: #F0FDF4;
                border: 1.5px solid #BBF7D0;
                border-radius: 14px;
                padding: 10px 42px 10px 14px;
                font-size: 14px;
                color: #14532D;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 34px;
                border-top-right-radius: 14px;
                border-bottom-right-radius: 14px;
            }}
            QComboBox::down-arrow {{
                image: url("{_arrow_path}");
                width: 14px;
                height: 14px;
            }}
            QComboBox QAbstractItemView {{
                background: white;
                border: 1px solid #BBF7D0;
                selection-background-color: #DCFCE7;
                selection-color: #14532D;
                outline: none;
            }}
        """

        # Prepared By
        prep_col = QVBoxLayout()
        prep_col.setSpacing(6)
        prep_col.addWidget(small_label("PREPARED BY"))
        self.prep_by_combo = QComboBox()
        self.prep_by_combo.setStyleSheet(combo_style)
        self.prep_by_combo.currentIndexChanged.connect(lambda *_: self._on_data_changed())
        prep_col.addWidget(self.prep_by_combo)
        row.addLayout(prep_col, 1)
        
        # Checked By
        check_col = QVBoxLayout()
        check_col.setSpacing(6)
        check_col.addWidget(small_label("CHECKED BY / APPROVED BY"))
        self.checked_by_combo = QComboBox()
        self.checked_by_combo.setStyleSheet(combo_style)
        self.checked_by_combo.currentIndexChanged.connect(lambda *_: self._on_data_changed())
        check_col.addWidget(self.checked_by_combo)
        row.addLayout(check_col, 1)
        
        lay.addLayout(row)
        
        card.body().addLayout(lay)
        # Populate initially
        QTimer.singleShot(100, self._refresh_doctor_combos)
        return card

    def _refresh_doctor_combos(self, select_prep_id=None, select_check_id=None):
        doctors = load_doctors()
        self.prep_by_combo.clear()
        self.checked_by_combo.clear()
        
        self.prep_by_combo.addItem("Select Technologist...", 0)
        self.checked_by_combo.addItem("Select Doctor...", 0)
        
        for d in reversed(doctors):
            dtype = d.get('type', 'doctor')
            if dtype == 'technologist':
                self.prep_by_combo.addItem(d['name'], d['id'])
            else:
                self.checked_by_combo.addItem(d['name'], d['id'])
            
        if select_prep_id:
            idx = self.prep_by_combo.findData(select_prep_id)
            if idx >= 0: self.prep_by_combo.setCurrentIndex(idx)
        if select_check_id:
            idx = self.checked_by_combo.findData(select_check_id)
            if idx >= 0: self.checked_by_combo.setCurrentIndex(idx)

    def _manage_doctors(self):
        dlg = DoctorManagementModal(self)
        dlg.exec()
        self._refresh_doctor_combos()

    def _remove_duration_option(self, duration):
        if len(self._duration_options) <= 1:
            self._show_toast("Cannot remove", "At least one sampling duration is required.", tone="warning")
            self._refresh_duration_controls(selected=self._current_scheme)
            return
        dlg = ConfirmActionModal(
            "Delete Sample Points",
            f"Are you sure you want to delete {duration} sample points?",
            confirm_label="Yes",
            cancel_label="No",
            cancel_tone="danger",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
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
        self._show_toast("Sample points deleted", f"{duration} Sample points is deleted")

    # ──────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────
    def _on_scheme_changed(self, n):
        self._populate_table(n)
        self._on_data_changed()

    def _on_data_changed(self):
        self._update_action_buttons()
        self._debounce.start(400)   # debounce 400 ms for live plot

    def _update_tx_duration(self):
        tx_date = self.f_tx_date.date()
        sample_date = self.f_sample_collection_date.date()
        if not tx_date or not sample_date:
            self.f_tx_duration.setText("—")
            return
        
        days = tx_date.daysTo(sample_date)
        
        if days < 0:
            self.f_tx_duration.setText("Invalid Date (Tx > Sample)")
            return
            
        years = days // 365
        remaining_days = days % 365
        months = remaining_days // 30
        final_days = remaining_days % 30
        
        parts = []
        if years > 0: parts.append(f"{years} Year{'s' if years > 1 else ''}")
        if months > 0: parts.append(f"{months} Month{'s' if months > 1 else ''}")
        if final_days > 0 or not parts: parts.append(f"{final_days} Day{'s' if final_days != 1 else ''}")
        
        self.f_tx_duration.setText(", ".join(parts))

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
        d_inv = self.f_invoice_date.date()
        d_del = self.f_delivery_date.date()
        d_sam = self.f_sample_collection_date.date()
        d_tx  = self.f_tx_date.date()
        
        return {
            'name': self.f_name.text().strip() or 'N/A',
            'age': self.f_age.text().strip() or 'N/A',
            'sex': '' if self.f_sex.currentText() == "Choose a gender" else self.f_sex.currentText(),
            'invoice_date': self.f_invoice_date.date().toString("dd.MM.yyyy"),
            'invoice_number': self.f_hosp_no.text().strip() or 'N/A',
            'report_number': self.f_report_no.text().strip() or 'N/A',
            'dept': self.f_referred_by.text().strip() or 'N/A',
            'delivery_date': d_del.toString("dd.MM.yyyy") if d_del else 'N/A',
            'drug': self.f_drug.text().strip(),
            'preparation': self.f_preparation.text().strip(),
            'dose': self.f_dose.text().strip(),
            'dose_dt': self.f_dose_dt.dateTime().toString("dd.MM.yyyy 'at' hh:mmAP"),
            'sample_collection_date': d_sam.toString("dd.MM.yyyy") if d_sam else 'N/A',
            'diag': self.f_diag.text().strip() or 'N/A',
            'tx_date': d_tx.toString("dd.MM.yyyy") if d_tx else 'N/A',
            'med': self.f_med.get_text() or 'N/A',
            'phone': self.f_phone.text().strip() or 'N/A',
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
            'prepared_by_id': self.prep_by_combo.currentData() if hasattr(self, 'prep_by_combo') else None,
            'checked_by_id': self.checked_by_combo.currentData() if hasattr(self, 'checked_by_combo') else None,
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
            'prepared_by_id': self.prep_by_combo.currentData(),
            'checked_by_id': self.checked_by_combo.currentData(),
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
            self.f_drug.text().strip(),
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
        for button in [self.draft_btn, getattr(self, 'sampling_draft_btn', None)]:
            if button is None:
                continue
            button.setVisible(not is_editing_saved_sample)
            button.setEnabled(draft_enabled)
            button.setCursor(Qt.CursorShape.PointingHandCursor if draft_enabled else Qt.CursorShape.ForbiddenCursor)

    _LIST_PAGE_SIZE = 10

    def _reset_list_view(self, card):
        if card is None:
            return
        card.set_page_index(0)
        card.clear_search()

    def _refresh_patients_list(self):
        if not hasattr(self, 'sample_list_card'):
            return

        def sort_key(snapshot):
            snapshot_id = str(snapshot.get('id', '') or '')
            saved_at = str(snapshot.get('saved_at', '') or '')
            patient = snapshot.get('patient', {})
            invoice_number = str(patient.get('invoice_number') or patient.get('hosp_id') or '')
            created_dt = None
            if len(snapshot_id) >= 14 and snapshot_id[:14].isdigit():
                try:
                    created_dt = datetime.strptime(snapshot_id[:14], "%Y%m%d%H%M%S")
                except ValueError:
                    created_dt = None
            try:
                saved_dt = datetime.strptime(saved_at, "%d/%m/%Y")
            except ValueError:
                saved_dt = datetime.min
            return (created_dt or saved_dt, snapshot_id, invoice_number)

        def matches_search(snapshot, query):
            if not query:
                return True
            p = snapshot.get('patient', {})
            return (
                query in (p.get('name') or '').lower() or
                query in (p.get('pid') or '').lower() or
                query in (p.get('phone') or '').lower() or
                query in (p.get('invoice_number') or p.get('hosp_id') or '').lower()
            )

        def populate(card, items, edit_cb, delete_cb, row_type='sample', view_cb=None, print_cb=None):
            query = card.search_text()
            filtered = [s for s in items if matches_search(s, query)]
            visible = sorted(filtered, key=sort_key, reverse=True)

            rows_layout = card._rows_lay
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if not visible:
                card.set_empty_text("No data found" if query else None)
                card.set_empty_visible(True)
                return

            card.set_empty_text()
            card.set_empty_visible(False)
            page_count = (len(visible) + self._LIST_PAGE_SIZE - 1) // self._LIST_PAGE_SIZE
            card.clamp_page_index(page_count)
            page_index = card.page_index()
            start = page_index * self._LIST_PAGE_SIZE
            page = visible[start:start + self._LIST_PAGE_SIZE]
            remaining = []

            for offset, snapshot in enumerate(page, start=start + 1):
                row = PatientRow(snapshot, row_type=row_type, serial_no=offset)
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
            card.set_pagination(page_index, page_count, len(visible), self._LIST_PAGE_SIZE)

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
        self.sample_list_card.set_count(len(self._saved_patients))
        if hasattr(self, 'draft_list_card'):
            self.draft_list_card.set_count(len(self._drafts))

    def _save_draft(self):
        phone = self.f_phone.text().strip()
        if phone:
            if not phone.isdigit() or len(phone) != 11:
                self._show_toast("Invalid Phone", "Please enter a valid 11-digit phone number.", tone="warning")
                return
        snapshot = self._snapshot_payload()
        snapshot.pop('pk', None)
        snapshot.pop('interp', None)
        if getattr(self, '_active_record_source', None) == 'draft' and getattr(self, '_active_record_id', None):
            delete_record(self._active_record_id)
        save_record(snapshot, 'draft')
        p = snapshot.get('patient', {})
        log_draft_saved(p.get('pid', 'N/A'), p.get('name', 'N/A'))
        self._load_saved_patients()
        self._reset_list_view(getattr(self, 'draft_list_card', None))
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
        invoice_number = patient.get('invoice_number', patient.get('hosp_id', ''))
        report_number = patient.get('report_number', patient.get('ward', ''))
        self.f_hosp_no.setText(invoice_number if invoice_number != 'N/A' else '')
        self.f_report_no.setText(report_number if report_number != 'N/A' else '')
        self.f_referred_by.setText(patient.get('dept', '') if patient.get('dept') != 'N/A' else '')
        self.f_phone.setText(patient.get('phone', '') if patient.get('phone') != 'N/A' else '')

        invoice_date = QDate.fromString(patient.get('invoice_date', patient.get('weight', '')), "dd.MM.yyyy")
        if invoice_date.isValid():
            self.f_invoice_date.setDate(invoice_date)
        delivery_date = QDate.fromString(patient.get('delivery_date', ''), "dd.MM.yyyy")
        if delivery_date.isValid():
            self.f_delivery_date.setDate(delivery_date)

        sex_value = patient.get('sex', '').strip()
        sex_index = self.f_sex.findText(sex_value) if sex_value else 0
        self.f_sex.setCurrentIndex(sex_index if sex_index >= 0 else 0)
        self.f_diag.setText(patient.get('diag', 'Post Renal Transplant') if patient.get('diag') != 'N/A' else 'Post Renal Transplant')
        self.f_drug.setText(patient.get('drug', 'MPA') or 'MPA')
        self.f_preparation.setText(patient.get('preparation', 'Mycophenolate Mofetil (MMF)'))
        self.f_dose.setText(patient.get('dose', '540mg - 720mg') if patient.get('dose') != 'N/A' else '')
        tx_date = QDate.fromString(patient.get('tx_date', ''), "dd.MM.yyyy")
        self.f_tx_date.setDate(tx_date if tx_date.isValid() else None)
        self._update_tx_duration()
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
            for m in [m.strip() for m in meds.split(',') if m.strip()]:
                self.f_med.select_med(m)
        
        # Restore doctors
        prep_id = snapshot.get('prepared_by_id')
        check_id = snapshot.get('checked_by_id')
        self._refresh_doctor_combos(select_prep_id=prep_id, select_check_id=check_id)

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
        dlg = ConfirmActionModal(
            "Delete Sample",
            "Are you sure you want to delete this sample from the Sample List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if snapshot:
            p = snapshot.get('patient', {})
            log_record_deleted(patient_id, p.get('pid', 'N/A'), p.get('name', 'N/A'))
        delete_record(patient_id)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._show_toast("Deleted successfully", "Sample removed from Sample List.")

    def _delete_draft(self, patient_id):
        snapshot = next((p for p in self._drafts if p['id'] == patient_id), None)
        dlg = ConfirmActionModal(
            "Delete Draft",
            "Are you sure you want to delete this draft from the Draft List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
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
            from app_paths import reports_dir as get_reports_dir
            reports_dir = get_reports_dir()
            report_path = reports_dir / f"{snapshot['id']}.html"
            prep_id = snapshot.get('prepared_by_id')
            check_id = snapshot.get('checked_by_id')
            prepared_by = get_doctor_by_id(prep_id) if prep_id else None
            checked_by = get_doctor_by_id(check_id) if check_id else None

            html = build_report_html(
                patient=snapshot.get('patient', {}),
                pk=snapshot.get('pk', {}),
                interp=snapshot.get('interp', 'N/A'),
                times=snapshot.get('times', []),
                concs=snapshot.get('concs', []),
                prepared_by=prepared_by,
                checked_by=checked_by,
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
            # Re-generate it if missing
            from report_print import build_report_html
            prep_id = snapshot.get('prepared_by_id')
            check_id = snapshot.get('checked_by_id')
            prepared_by = get_doctor_by_id(prep_id) if prep_id else None
            checked_by = get_doctor_by_id(check_id) if check_id else None
            
            html = build_report_html(
                patient=snapshot.get('patient', {}),
                pk=snapshot.get('pk', {}),
                interp=snapshot.get('interp', 'N/A'),
                times=snapshot.get('times', []),
                concs=snapshot.get('concs', []),
                prepared_by=prepared_by,
                checked_by=checked_by,
                graph_uri=None # report_print will generate it from data
            )
            # Re-determine path if it was empty
            if not report_path:
                from app_paths import reports_dir
                report_path = str(reports_dir() / f"{snapshot['id']}.html")
                snapshot['report_path'] = report_path

            try:
                Path(report_path).write_text(html, encoding="utf-8")
            except Exception:
                pass
        
        if report_path and Path(report_path).exists():
            webbrowser.open(f"file://{Path(report_path).absolute()}")
        else:
            self._show_toast("Error", "Report file not found and could not be regenerated.", tone="error")

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
        # Phone validation
        phone = self.f_phone.text().strip()
        if phone:
            if not phone.isdigit() or len(phone) != 11:
                self._show_toast("Invalid Phone", "Please enter a valid 11-digit phone number.", tone="warning")
                return

        if hasattr(self, '_report_snapshot'):
            delattr(self, '_report_snapshot')

        drug = canonical_drug_name(self.f_drug.text().strip() or 'MPA')

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
            self._reset_list_view(getattr(self, 'sample_list_card', None))
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

        # LSS estimate — only use when EXACTLY 3 time points are provided
        # and they match the LSS equation requirements (C₀, C₀.₅, C₂).
        # When more points are available, trapezoidal AUC is more accurate.
        lss = None
        if len(times) == 3:
            rounded_times = set(round(t, 1) for t in times)
            if rounded_times == {0.0, 0.5, 2.0}:
                lss = calculate_lss_auc(times, concs, cni=drug)
        
        if lss and drug.upper() in lss['equation_label'].upper():
            pk['auc_lss']       = lss['auc_lss']
            pk['lss_equation']  = lss['equation_label']
            pk['lss_r2']        = lss['r2']

        # Interpretation — use auc_lss when available (exactly 3-point LSS),
        # fall back to auc_0_12 (trapezoidal extrapolation) for all other cases.
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
        self._reset_list_view(getattr(self, 'sample_list_card', None))
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
        for edit in [self.f_name, self.f_age, self.f_hosp_no, self.f_report_no, self.f_referred_by,
                     self.f_dose,
                     self.f_diag, self.trough_edit, self.f_phone]:
            edit.clear()
        self.f_drug.setText("MPA")
        self.f_preparation.setText("Mycophenolate Mofetil (MMF)")
        self.f_diag.setText("Post Renal Transplant")
        self.f_sex.setCurrentIndex(0)
        self.f_med.clear_selection()
        self.f_tx_date.setDate(None)
        self.f_invoice_date.setDate(QDate.currentDate())
        self.f_delivery_date.setDate(QDate.currentDate())
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


# ─────────────────────────────────────────────────────────────────────────────
# Helper Modals for Doctors
# ─────────────────────────────────────────────────────────────────────────────

class DoctorManagementModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Signatories")
        self.setFixedWidth(550)
        self.setFixedHeight(600)
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
                stop:0 #1E293B, stop:1 #334155);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.account-cog", color="white").pixmap(22, 22))
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.15); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        t = QLabel("Manage Signatories")
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Configure doctors and technologists for reports")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.7); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.1); color: white;
                border: none; border-radius: 15px; font-size: 18px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """)
        close_btn.clicked.connect(self.reject)
        banner_lay.addWidget(close_btn)
        
        lay.addWidget(banner)
        
        # ── Body ────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 24, 24, 24)
        body_lay.setSpacing(18)
        
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(6)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: #F8FAFC;
                border: 1.5px solid #E2E8F0;
                border-radius: 16px;
                padding: 10px;
                outline: none;
            }}
            QListWidget::item {{
                background: white;
                border: 1px solid #F1F5F9;
                border-radius: 12px;
                padding: 12px;
                color: {TEXT_CLR};
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background: #F1F5F9;
            }}
            QListWidget::item:selected {{
                background: #EFF6FF;
                border: 1.5px solid #3B82F6;
                color: #2563EB;
            }}
        """)
        body_lay.addWidget(self.list_widget)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        add_btn = QPushButton("Add New Signatory")
        add_btn.setFixedHeight(40)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: #16A34A; color: white; border: none; border-radius: 10px;
                padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #15803D; }
        """)
        add_btn.clicked.connect(self._add_doctor)
        
        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(40)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background: #F1F5F9; color: #475569; border: 1.5px solid #E2E8F0;
                border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #E2E8F0; }
        """)
        edit_btn.clicked.connect(self._edit_doctor)
        
        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background: #FEF2F2; color: #DC2626; border: 1.5px solid #FEE2E2;
                border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #DC2626; color: white; border-color: #B91C1C; }
        """)
        del_btn.clicked.connect(self._delete_doctor)
        
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        body_lay.addLayout(btn_row)
        
        lay.addWidget(body)
        
        self._refresh_list()
        
    def _refresh_list(self):
        self.list_widget.clear()
        doctors = load_doctors()
        for d in reversed(doctors):
            item = QListWidgetItem(f"{d['name']} ({d['designation'] or 'No designation'})")
            item.setData(Qt.ItemDataRole.UserRole, d)
            self.list_widget.addItem(item)
            
    def _add_doctor(self):
        dlg = DoctorEditModal(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_list()
            
    def _edit_doctor(self):
        item = self.list_widget.currentItem()
        if not item: return
        doctor = item.data(Qt.ItemDataRole.UserRole)
        dlg = DoctorEditModal(doctor, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_list()
            
    def _delete_doctor(self):
        item = self.list_widget.currentItem()
        if not item: return
        doctor = item.data(Qt.ItemDataRole.UserRole)
        dlg = ConfirmActionModal(
            "Delete Signatory",
            f"Are you sure you want to delete \"{doctor['name']}\" from the Signatory List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        delete_doctor(doctor['id'])
        self._refresh_list()

from ui_widgets import Card, make_shadow, small_label, value_label, ToastMessage, ConfirmActionModal

class DoctorEditModal(QDialog):
    def __init__(self, doctor=None, parent=None):
        super().__init__(parent)
        self.doctor = doctor
        self.setWindowTitle("Add Signatory" if not doctor else "Edit Signatory")
        self.setFixedWidth(800)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: white; border-radius: 20px; }")
        
        # Toast Message for validation
        self._toast = ToastMessage(self)
        self._toast.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        
        # ── Top colored banner ──────────────────
        banner = QFrame()
        banner.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #7C3AED, stop:1 #8B5CF6);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.account-plus" if not doctor else "mdi6.account-edit", color="white").pixmap(22, 22))
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        t = QLabel("Add New Signatory" if not doctor else "Edit Signatory Details")
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Enter signatory name, description, phone and signature")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.75); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        lay.addWidget(banner)

        # ── Body ────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(32, 28, 32, 28)
        body_lay.setSpacing(20)
        
        # Row 1: Name & Type
        row1 = QHBoxLayout()
        row1.setSpacing(24)

        # Name
        name_sec = QVBoxLayout()
        name_sec.setSpacing(8)
        name_sec.addWidget(small_label("FULL NAME", color="#64748B", size=10, bold=True))
        self.name_edit = QLineEdit(doctor['name'] if doctor else "")
        self.name_edit.setPlaceholderText("e.g. Dr. John Doe")
        self.name_edit.setStyleSheet(self._input_style())
        name_sec.addWidget(self.name_edit)
        row1.addLayout(name_sec, 3)

        # Type
        type_sec = QVBoxLayout()
        type_sec.setSpacing(8)
        type_sec.addWidget(small_label("SIGNATORY TYPE", color="#64748B", size=10, bold=True))
        
        import tempfile, os
        _arrow_path = os.path.join(tempfile.gettempdir(), "tdm_staff_arrow_down.png")
        qta.icon("mdi6.chevron-down", color="#64748B").pixmap(14, 14).save(_arrow_path)
        _arrow_path = _arrow_path.replace("\\", "/")
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Doctor", "Technologist"])
        self.type_combo.setStyleSheet(self._input_style(_arrow_path))
        if doctor and doctor.get('type'):
            self.type_combo.setCurrentText(doctor['type'].capitalize())
        type_sec.addWidget(self.type_combo)
        row1.addLayout(type_sec, 2)
        body_lay.addLayout(row1)
        
        # Row 2: Description & Phone
        row2 = QHBoxLayout()
        row2.setSpacing(24)

        # Description
        desc_sec = QVBoxLayout()
        desc_sec.setSpacing(8)
        desc_sec.addWidget(small_label("DESCRIPTION", color="#64748B", size=10, bold=True))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlainText(doctor['designation'] if doctor else "")
        self.desc_edit.setPlaceholderText("e.g. Degrees, Department...")
        self.desc_edit.setStyleSheet(self._input_style())
        self.desc_edit.setFixedHeight(120)
        desc_sec.addWidget(self.desc_edit)
        row2.addLayout(desc_sec, 4)

        # Phone Number
        phone_sec = QVBoxLayout()
        phone_sec.setSpacing(8)
        phone_label = QHBoxLayout()
        phone_label.setSpacing(4)
        phone_label.addWidget(small_label("PHONE NUMBER", color="#64748B", size=10, bold=True))
        req_star = QLabel("*")
        req_star.setStyleSheet("color: #DC2626; font-size: 14px; font-weight: bold; background: transparent;")
        phone_label.addWidget(req_star)
        phone_label.addStretch()
        phone_sec.addLayout(phone_label)
        
        self.phone_edit = QLineEdit(doctor.get('phone', '') if doctor else "")
        self.phone_edit.setPlaceholderText("e.g. 01XXXXXXXXX")
        self.phone_edit.setMaxLength(11)
        self.phone_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,11}"), self.phone_edit))
        self.phone_edit.setStyleSheet(self._input_style())
        phone_sec.addWidget(self.phone_edit)
        phone_sec.addStretch() # Push to top
        row2.addLayout(phone_sec, 3)
        
        body_lay.addLayout(row2)
        
        # Signature Section
        sig_sec = QVBoxLayout()
        sig_sec.setSpacing(10)
        sig_sec.addWidget(small_label("DIGITAL SIGNATURE", color="#64748B", size=10, bold=True))
        
        sig_row = QHBoxLayout()
        sig_row.setSpacing(16)

        sig_box = QFrame()
        sig_box.setStyleSheet("background: #F8FAFC; border: 1.5px dashed #CBD5E1; border-radius: 12px;")
        sig_box_lay = QVBoxLayout(sig_box)
        sig_box_lay.setContentsMargins(8, 8, 8, 8)
        
        self.sig_label = QLabel()
        self.sig_label.setFixedSize(280, 100)
        self.sig_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sig_label.setStyleSheet("background: transparent; color: #94A3B8; font-size: 11px;")
        self.sig_path = doctor['signature_path'] if doctor else None
        self._update_sig_preview()
        sig_box_lay.addWidget(self.sig_label)
        sig_row.addWidget(sig_box, 2)

        upload_btn = QPushButton("Upload Signature")
        upload_btn.setFixedHeight(100)
        upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_btn.setIcon(qta.icon("mdi6.upload", color="#2563EB"))
        upload_btn.setStyleSheet("""
            QPushButton {
                background: #EFF6FF; color: #2563EB; border: 1.5px solid #BFDBFE;
                border-radius: 12px; padding: 8px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #DBEAFE; }
        """)
        upload_btn.clicked.connect(self._upload_sig)
        sig_row.addWidget(upload_btn, 1)
        
        sig_sec.addLayout(sig_row)
        body_lay.addLayout(sig_sec)
        
        body_lay.addSpacing(10)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(42)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #FEE2E2; color: #B91C1C;
                border: 1.5px solid #FCA5A5; border-radius: 10px;
                font-size: 13px; padding: 0 24px;
            }
            QPushButton:hover {
                background: #DC2626; color: white;
                border: 1.5px solid #B91C1C;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Save Details")
        save_btn.setFixedHeight(42)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #7C3AED; color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0 24px;
            }
            QPushButton:hover { background: #6D28D9; }
        """)
        save_btn.clicked.connect(self._save)
        
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        body_lay.addLayout(btn_row)
        
        lay.addWidget(body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_toast'):
            width = 300
            self._toast.setFixedWidth(width)
            self._toast.move(self.width() - width - 24, 24)

    def _show_error(self, title, msg):
        self._toast.show_message(title, msg, tone="warning")

    def _input_style(self, arrow_path=None):
        style = f"""
            QLineEdit, QPlainTextEdit, QComboBox {{
                background: #F7FAFE;
                border: 1.5px solid {BORDER};
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 14px;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
                border-color: {BLUE};
                background: white;
            }}
            QComboBox {{
                padding-right: 40px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 34px;
                border-top-right-radius: 12px;
                border-bottom-right-radius: 12px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #64748B;
                margin-top: 2px;
            }}
        """
        if arrow_path:
            style += f"""
                QComboBox::down-arrow {{
                    image: url("{arrow_path}");
                    width: 14px;
                    height: 14px;
                    border: none;
                }}
            """
        
        style += f"""
            QComboBox QAbstractItemView {{
                background: white;
                border: 1px solid {BORDER};
                selection-background-color: #EFF6FF;
                selection-color: {BLUE};
                outline: none;
            }}
        """
        return style
        
    def _upload_sig(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Signature Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            # Copy to app signatures dir
            from app_paths import ensure_data_dirs
            import shutil
            sig_dir = ensure_data_dirs() / "signatures"
            ext = Path(file_path).suffix
            dest_name = f"sig_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            dest_path = sig_dir / dest_name
            try:
                shutil.copy2(file_path, dest_path)
                self.sig_path = str(dest_path)
                self._update_sig_preview()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to copy signature: {e}")
                
    def _update_sig_preview(self):
        if self.sig_path and Path(self.sig_path).exists():
            pix = QPixmap(self.sig_path)
            self.sig_label.setPixmap(pix.scaled(self.sig_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.sig_label.setText("No Signature Uploaded")
            
    def _save(self):
        name = self.name_edit.text().strip()
        desc = self.desc_edit.toPlainText().strip()
        type_str = self.type_combo.currentText().lower()
        phone = self.phone_edit.text().strip()
        
        if not name:
            self._show_error("Name Required", "Please enter signatory name.")
            return
            
        if not phone:
            self._show_error("Phone Required", "Please enter phone number.")
            return
            
        if not phone.isdigit() or len(phone) != 11:
            self._show_error("Invalid Phone", "Please enter a valid 11-digit phone number.")
            return

        # Uniqueness check
        from database import is_doctor_phone_exists
        if is_doctor_phone_exists(phone, exclude_id=self.doctor['id'] if self.doctor else None):
            self._show_error("Duplicate Phone", "This phone number is already registered.")
            return

        if self.doctor:
            update_doctor(self.doctor['id'], name, desc, self.sig_path, type=type_str, phone=phone)
        else:
            add_doctor(name, desc, self.sig_path, type=type_str, phone=phone)
        self.accept()
