import psycopg2

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget, QPushButton

from db_config import load_db_config, save_db_config
from ui_constants import BLUE, TEXT_CLR, small_label
from ui_widgets import AlertModal, Card


def build_settings_page(window):
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

    def make_field(placeholder, value="", password=False):
        field = QLineEdit(value)
        field.setPlaceholderText(placeholder)
        field.setStyleSheet(field_style)
        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    host_lbl = small_label("HOST", color="#111111", size=12, bold=True)
    window._db_host = make_field("e.g. localhost", cfg.get("host", "localhost"))
    host_col = QVBoxLayout()
    host_col.setSpacing(6)
    host_col.addWidget(host_lbl)
    host_col.addWidget(window._db_host)

    port_lbl = small_label("PORT", color="#111111", size=12, bold=True)
    window._db_port = make_field("e.g. 5432", cfg.get("port", "5432"))
    port_col = QVBoxLayout()
    port_col.setSpacing(6)
    port_col.addWidget(port_lbl)
    port_col.addWidget(window._db_port)

    db_lbl = small_label("DATABASE NAME", color="#111111", size=12, bold=True)
    window._db_name = make_field("e.g. tdm_db", cfg.get("database", "tdm_db"))
    db_col = QVBoxLayout()
    db_col.setSpacing(6)
    db_col.addWidget(db_lbl)
    db_col.addWidget(window._db_name)

    user_lbl = small_label("USERNAME", color="#111111", size=12, bold=True)
    window._db_user = make_field("e.g. postgres", cfg.get("username", "postgres"))
    user_col = QVBoxLayout()
    user_col.setSpacing(6)
    user_col.addWidget(user_lbl)
    user_col.addWidget(window._db_user)

    pass_lbl = small_label("PASSWORD", color="#111111", size=12, bold=True)
    window._db_pass = make_field("Enter password", cfg.get("password", ""), password=True)
    pass_col = QVBoxLayout()
    pass_col.setSpacing(6)
    pass_col.addWidget(pass_lbl)
    pass_col.addWidget(window._db_pass)

    grid.addLayout(host_col, 0, 0)
    grid.addLayout(port_col, 0, 1)
    grid.addLayout(db_col, 1, 0)
    grid.addLayout(user_col, 1, 1)
    grid.addLayout(pass_col, 2, 0)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(12)

    test_btn = QPushButton("Test Connection")
    test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    test_btn.setStyleSheet(
        """
        QPushButton {
            background: #EFF6FF; color: #2563EB;
            border: 1.5px solid #BFDBFE; border-radius: 12px;
            padding: 10px 20px; font-size: 13px; font-weight: bold;
        }
        QPushButton:hover { background: #DBEAFE; }
        """
    )

    save_btn = QPushButton("Save & Apply")
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn.setStyleSheet(
        """
        QPushButton {
            background: #166534; color: white;
            border: none; border-radius: 12px;
            padding: 10px 24px; font-size: 13px; font-weight: bold;
        }
        QPushButton:hover { background: #15803D; }
        """
    )

    def get_config():
        return {
            "host": window._db_host.text().strip(),
            "port": window._db_port.text().strip(),
            "database": window._db_name.text().strip(),
            "username": window._db_user.text().strip(),
            "password": window._db_pass.text(),
        }

    def test_connection():
        config = get_config()
        try:
            conn = psycopg2.connect(
                host=config["host"],
                port=int(config["port"]),
                dbname=config["database"],
                user=config["username"],
                password=config["password"] or None,
                connect_timeout=5,
            )
            conn.close()
            AlertModal(
                "Connection Successful",
                "Successfully connected to the database.",
                tone="success",
                parent=window,
            ).exec()
        except Exception as exc:
            AlertModal("Connection Failed", str(exc), tone="error", parent=window).exec()

    def save_and_reconnect():
        config = get_config()
        try:
            conn = psycopg2.connect(
                host=config["host"],
                port=int(config["port"]),
                dbname=config["database"],
                user=config["username"],
                password=config["password"] or None,
                connect_timeout=5,
            )
            conn.close()
        except Exception as exc:
            AlertModal("Save Failed", f"Cannot save - connection failed:\n{exc}", tone="error", parent=window).exec()
            return
        save_db_config(config)
        AlertModal(
            "Settings Saved",
            "Database settings saved and reconnected successfully.",
            tone="success",
            parent=window,
        ).exec()

    test_btn.clicked.connect(test_connection)
    save_btn.clicked.connect(save_and_reconnect)

    btn_row.addWidget(test_btn)
    btn_row.addWidget(save_btn)
    btn_row.addStretch()

    body = QVBoxLayout()
    body.setSpacing(16)
    body.addLayout(grid)
    body.addLayout(btn_row)

    card.body().addLayout(body)
    lay.addWidget(card)
    lay.addStretch()
    return page
