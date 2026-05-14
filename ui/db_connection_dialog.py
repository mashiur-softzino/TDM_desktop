"""
Database connection dialog — shown at startup when DB is unreachable.
"""

import psycopg2
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QGridLayout, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
import qtawesome as qta

from core.app_paths import asset_path
from core.db_config import load_db_config, save_db_config
from ui.ui_constants import TEXT_CLR, BLUE
from ui.ui_widgets import AlertModal


class DBConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TDM Report — Database Connection")
        self.setFixedWidth(520)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet("background: #FFFFFF;")
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Branded header ──────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0A234F, stop:1 #1A4A8A);
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(28, 0, 28, 0)
        h_lay.setSpacing(12)

        logo_px = QPixmap(str(asset_path("softzino.png")))
        logo_lbl = QLabel()
        logo_lbl.setStyleSheet("background: transparent;")
        if not logo_px.isNull():
            logo_lbl.setPixmap(logo_px.scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
        h_lay.addWidget(logo_lbl)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFixedHeight(32)
        divider.setStyleSheet("color: rgba(255,255,255,0.30);")
        h_lay.addWidget(divider)

        app_name = QLabel("TDM Report")
        app_name.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #FFFFFF; background: transparent;"
        )
        h_lay.addWidget(app_name)

        sub_name = QLabel("Therapeutic Drug Monitoring")
        sub_name.setStyleSheet("font-size: 11px; color: #9DB7DD; background: transparent; margin-top: 3px;")
        h_lay.addWidget(sub_name)
        h_lay.addStretch()

        lay.addWidget(header)

        # ── Alert strip ─────────────────────────────────────────────────────
        alert = QWidget()
        alert.setStyleSheet(
            "background: #FEF2F2; border-bottom: 1px solid #FECACA;"
        )
        alert_lay = QHBoxLayout(alert)
        alert_lay.setContentsMargins(28, 10, 28, 10)
        alert_lay.setSpacing(10)

        alert_icon = QLabel()
        alert_icon.setPixmap(
            qta.icon("mdi6.database-alert-outline", color="#DC2626").pixmap(20, 20)
        )
        alert_icon.setStyleSheet("background: transparent;")
        alert_lay.addWidget(alert_icon)

        alert_txt = QLabel(
            "Could not connect to the database. Please enter your connection details below."
        )
        alert_txt.setWordWrap(True)
        alert_txt.setStyleSheet(
            "font-size: 12px; color: #991B1B; background: transparent;"
        )
        alert_lay.addWidget(alert_txt, 1)
        lay.addWidget(alert)

        # ── Form body ────────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: #FFFFFF;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(28, 24, 28, 24)
        body_lay.setSpacing(20)

        cfg = load_db_config()
        field_style = """
            QLineEdit {
                background: #F8FAFC;
                border: 1.5px solid #E2E8F0;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 14px;
                color: #1E293B;
            }
            QLineEdit:focus { border-color: #3B82F6; background: #FFFFFF; }
            QLineEdit::placeholder { color: rgba(0,0,0,0.22); }
        """

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #111111; letter-spacing: 0.8px;"
            )
            return l

        def field(placeholder, value='', password=False):
            f = QLineEdit(value)
            f.setPlaceholderText(placeholder)
            f.setFixedHeight(42)
            f.setStyleSheet(field_style)
            if password:
                f.setEchoMode(QLineEdit.EchoMode.Password)
            return f

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setHorizontalSpacing(14)

        self._host = field("e.g. localhost", cfg.get('host', 'localhost'))
        self._port = field("e.g. 5432",      cfg.get('port', '5432'))
        self._db   = field("e.g. tdm_db",    cfg.get('database', 'tdm_db'))
        self._user = field("e.g. postgres",  cfg.get('username', 'postgres'))
        self._pass = field("Password",        cfg.get('password', ''), password=True)

        def add_field(row, col, label, widget):
            col_lay = QVBoxLayout()
            col_lay.setSpacing(5)
            col_lay.addWidget(lbl(label))
            col_lay.addWidget(widget)
            grid.addLayout(col_lay, row, col)

        add_field(0, 0, "HOST",          self._host)
        add_field(0, 1, "PORT",          self._port)
        add_field(1, 0, "DATABASE NAME", self._db)
        add_field(1, 1, "USERNAME",      self._user)
        add_field(2, 0, "PASSWORD",      self._pass)

        body_lay.addLayout(grid)

        # Thin divider before buttons
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("color: #E2E8F0;")
        body_lay.addWidget(div2)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        exit_btn = QPushButton("Exit Application")
        exit_btn.setFixedHeight(42)
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setStyleSheet("""
            QPushButton {
                background: #F1F5F9; color: #475569;
                border: 1.5px solid #E2E8F0; border-radius: 10px;
                padding: 0 20px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #E2E8F0; border-color: #CBD5E1; }
        """)
        exit_btn.clicked.connect(self.reject)

        self._connect_btn = QPushButton("  Connect to Database")
        self._connect_btn.setFixedHeight(42)
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.setIcon(qta.icon("mdi6.database-check-outline", color="white"))
        self._connect_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1565C0, stop:1 #1976D2);
                color: white;
                border: none; border-radius: 10px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1976D2, stop:1 #1E88E5);
            }
            QPushButton:disabled { background: #94A3B8; }
        """)
        self._connect_btn.clicked.connect(self._try_connect)

        btn_row.addWidget(exit_btn)
        btn_row.addWidget(self._connect_btn)
        body_lay.addLayout(btn_row)

        # Footer
        footer = QLabel("© Softzino Technologies · All rights reserved")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            "font-size: 10px; color: #94A3B8; margin-top: 2px; background: transparent;"
        )
        body_lay.addWidget(footer)

        lay.addWidget(body)

    def _try_connect(self):
        self._connect_btn.setEnabled(False)

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        host = self._host.text().strip()
        port = self._port.text().strip()
        db   = self._db.text().strip()
        user = self._user.text().strip()
        pwd  = self._pass.text()

        try:
            conn = psycopg2.connect(
                host=host,
                port=int(port),
                dbname=db,
                user=user,
                password=pwd or None,
                connect_timeout=5,
            )
            conn.close()
            save_db_config({
                'host': host, 'port': port,
                'database': db, 'username': user, 'password': pwd,
            })
            self.accept()
        except Exception as e:
            AlertModal("Connection Failed", str(e), tone="error", parent=self).exec()
            self._connect_btn.setEnabled(True)
