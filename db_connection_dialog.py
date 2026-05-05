"""
Database connection dialog — shown at startup when DB is unreachable.
"""

import psycopg2
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import qtawesome as qta

from db_config import load_db_config, save_db_config
from ui_constants import TEXT_CLR, BLUE


class DBConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Connection")
        self.setFixedWidth(480)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet("background: #FFFFFF;")
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(20)

        # Header
        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("mdi6.database-alert-outline", color="#DC2626").pixmap(28, 28))
        icon_lbl.setStyleSheet("background: transparent;")
        header_row.addWidget(icon_lbl)
        title = QLabel("Database Connection Required")
        title.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {TEXT_CLR};")
        header_row.addWidget(title)
        header_row.addStretch()
        lay.addLayout(header_row)

        subtitle = QLabel("Could not connect to the database. Please enter the connection details.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 13px; color: #64748B;")
        lay.addWidget(subtitle)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E2E8F0;")
        lay.addWidget(line)

        # Fields
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
            QLineEdit:focus { border-color: #3B82F6; background: white; }
            QLineEdit::placeholder { color: rgba(0,0,0,0.22); }
        """

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("font-size: 11px; font-weight: bold; color: #111111; letter-spacing: 0.8px;")
            return l

        def field(placeholder, value='', password=False):
            f = QLineEdit(value)
            f.setPlaceholderText(placeholder)
            f.setStyleSheet(field_style)
            if password:
                f.setEchoMode(QLineEdit.EchoMode.Password)
            return f

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setHorizontalSpacing(14)

        self._host = field("e.g. localhost", cfg.get('host', 'localhost'))
        self._port = field("e.g. 5432", cfg.get('port', '5432'))
        self._db   = field("e.g. tdm_db",  cfg.get('database', 'tdm_db'))
        self._user = field("e.g. postgres", cfg.get('username', 'postgres'))
        self._pass = field("Password",       cfg.get('password', ''), password=True)

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

        lay.addLayout(grid)

        # Status label
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 12px; padding: 2px 0;")
        lay.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedHeight(40)
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.setStyleSheet("""
            QPushButton {
                background: #166534; color: white;
                border: none; border-radius: 10px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #15803D; }
            QPushButton:disabled { background: #94A3B8; }
        """)
        self._connect_btn.clicked.connect(self._try_connect)

        exit_btn = QPushButton("Exit")
        exit_btn.setFixedHeight(40)
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setStyleSheet("""
            QPushButton {
                background: #F1F5F9; color: #475569;
                border: 1px solid #E2E8F0; border-radius: 10px;
                padding: 0 20px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #E2E8F0; }
        """)
        exit_btn.clicked.connect(self.reject)

        btn_row.addWidget(exit_btn)
        btn_row.addWidget(self._connect_btn)
        lay.addLayout(btn_row)

    def _try_connect(self):
        self._connect_btn.setEnabled(False)
        self._status.setText("Connecting...")
        self._status.setStyleSheet("font-size: 12px; color: #64748B; padding: 2px 0;")

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
            self._status.setText(f"✗ {e}")
            self._status.setStyleSheet("font-size: 12px; color: #DC2626; padding: 2px 0;")
            self._connect_btn.setEnabled(True)
