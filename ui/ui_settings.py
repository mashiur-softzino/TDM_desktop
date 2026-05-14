import psycopg2
import qtawesome as qta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialog,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.database import load_report_print_config, save_report_print_config
from core.db_config import load_db_config, save_db_config
from ui.ui_constants import BLUE, TEXT_CLR, small_label
from ui.ui_widgets import AlertModal, Card, ConfirmActionModal


def _field_style():
    return f"""
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


def _make_field(placeholder, value="", password=False):
    field = QLineEdit(value)
    field.setPlaceholderText(placeholder)
    field.setStyleSheet(_field_style())
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


def _labeled_field(label, field):
    col = QVBoxLayout()
    col.setSpacing(6)
    col.addWidget(small_label(label, color="#111111", size=12, bold=True))
    col.addWidget(field)
    return col


def _option_button(title, subtitle):
    card = QFrame()
    card.setCursor(Qt.CursorShape.PointingHandCursor)
    card.setFixedHeight(58)
    card.setProperty("active", False)
    card.setStyleSheet("""
        QFrame {
            background: #FFFFFF;
            border: 1.5px solid #D8E2EF;
            border-radius: 12px;
        }
        QFrame[active="true"] {
            background: #EAF6FB;
            border-color: #0E7490;
        }
        QLabel {
            background: transparent;
            border: none;
        }
    """)

    lay = QHBoxLayout(card)
    lay.setContentsMargins(10, 7, 14, 7)
    lay.setSpacing(10)

    dot = QLabel()
    dot.setFixedSize(17, 17)
    dot.setProperty("active", False)
    dot.setStyleSheet("""
        QLabel {
            background: #FFFFFF;
            border: 1.5px solid #94A3B8;
            border-radius: 8px;
        }
        QLabel[active="true"] {
            background: #0E7490;
            border: 1.5px solid #0E7490;
        }
    """)
    lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

    text_lay = QVBoxLayout()
    text_lay.setSpacing(1)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 700;")
    subtitle_lbl = QLabel(subtitle)
    subtitle_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 400;")
    text_lay.addWidget(title_lbl)
    text_lay.addWidget(subtitle_lbl)
    lay.addLayout(text_lay)
    lay.addStretch()

    return {"card": card, "dot": dot, "title": title_lbl, "subtitle": subtitle_lbl}


def _refresh_option_button(option, active: bool):
    option["card"].setProperty("active", active)
    option["dot"].setProperty("active", active)
    option["title"].setStyleSheet(
        f"color: {'#0E7490' if active else '#1E293B'}; font-size: 13px; font-weight: 700;"
    )
    option["subtitle"].setStyleSheet("color: #64748B; font-size: 11px; font-weight: 400;")
    for widget in (option["card"], option["dot"]):
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _build_database_config_tab(window):
    card = Card("Database Config", "mdi6.database-cog-outline", icon_color="#334155")
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    card.body().setAlignment(Qt.AlignmentFlag.AlignTop)
    cfg = load_db_config()

    window._db_host = _make_field("e.g. localhost", cfg.get("host", "localhost"))
    window._db_port = _make_field("e.g. 5432", cfg.get("port", "5432"))
    window._db_name = _make_field("e.g. tdm_db", cfg.get("database", "tdm_db"))
    window._db_user = _make_field("e.g. postgres", cfg.get("username", "postgres"))
    window._db_pass = _make_field("Enter password", cfg.get("password", ""), password=True)

    grid = QGridLayout()
    grid.setSpacing(14)
    grid.setHorizontalSpacing(18)
    grid.addLayout(_labeled_field("HOST", window._db_host), 0, 0)
    grid.addLayout(_labeled_field("PORT", window._db_port), 0, 1)
    grid.addLayout(_labeled_field("DATABASE NAME", window._db_name), 1, 0)
    grid.addLayout(_labeled_field("USERNAME", window._db_user), 1, 1)
    grid.addLayout(_labeled_field("PASSWORD", window._db_pass), 2, 0)

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
            AlertModal("Connection Successful", "Successfully connected to the database.", tone="success", parent=window).exec()
        except Exception as exc:
            AlertModal("Connection Failed", str(exc), tone="error", parent=window).exec()

    def save_and_reconnect():
        confirm = ConfirmActionModal(
            "Save Database Config",
            "Do you want to save and apply these database settings?",
            confirm_label="Yes",
            cancel_label="No",
            parent=window,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

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
        if hasattr(window, "_show_toast"):
            window._show_toast("Settings saved", "Database settings saved and applied successfully.")
        else:
            AlertModal("Settings Saved", "Database settings saved and applied successfully.", tone="success", parent=window).exec()

    test_btn.clicked.connect(test_connection)
    save_btn.clicked.connect(save_and_reconnect)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(12)
    btn_row.addWidget(test_btn)
    btn_row.addWidget(save_btn)
    btn_row.addStretch()

    body = QVBoxLayout()
    body.setSpacing(16)
    body.addLayout(grid)
    body.addLayout(btn_row)
    card.body().addLayout(body)
    return card


def _build_report_config_tab(window):
    card = Card("Report Config", "mdi6.file-cog-outline", icon_color="#0E7490")
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    card.body().setAlignment(Qt.AlignmentFlag.AlignTop)
    try:
        config = load_report_print_config()
    except Exception:
        config = {"mode": "custom", "custom_top_gap_cm": 2.3}

    custom_btn = _option_button("Custom Print", "Top gap selected manually")
    normal_btn = _option_button("Normal Print", "Without any extra top gap")
    buttons = {
        "custom": custom_btn,
        "normal": normal_btn,
    }

    custom_gap = QDoubleSpinBox()
    custom_gap.setRange(0.0, 10.0)
    custom_gap.setDecimals(1)
    custom_gap.setSingleStep(0.1)
    custom_gap.setSuffix(" cm")
    custom_gap.setValue(float(config.get("custom_top_gap_cm", 2.3)))
    custom_gap.setFixedHeight(46)
    custom_gap.setFixedWidth(130)
    custom_gap.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    custom_gap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    custom_gap.lineEdit().setReadOnly(True)
    custom_gap.lineEdit().setFocusPolicy(Qt.FocusPolicy.NoFocus)
    custom_gap.setStyleSheet(f"""
        QDoubleSpinBox {{
            background: #FFFFFF;
            border: 1.5px solid #D6E2EE;
            border-radius: 12px;
            padding: 8px 14px;
            font-size: 14px;
            color: {TEXT_CLR};
        }}
        QDoubleSpinBox:focus {{
            border: 1.5px solid #0E7490;
            background: white;
        }}
        QDoubleSpinBox:disabled {{
            color: #94A3B8;
            background: #F8FAFC;
        }}
    """)

    stepper = QFrame()
    stepper.setFixedSize(38, 46)
    stepper.setStyleSheet("""
        QFrame {
            background: #F8FBFE;
            border: 1.5px solid #D6E2EE;
            border-radius: 12px;
        }
        QToolButton {
            background: transparent;
            border: none;
            border-radius: 8px;
        }
        QToolButton:hover {
            background: #EAF6FB;
        }
        QToolButton:pressed {
            background: #DDF1F7;
        }
    """)
    stepper_lay = QVBoxLayout(stepper)
    stepper_lay.setContentsMargins(3, 3, 3, 3)
    stepper_lay.setSpacing(1)
    up_btn = QToolButton()
    down_btn = QToolButton()
    for btn, icon_name in ((up_btn, "mdi6.chevron-up"), (down_btn, "mdi6.chevron-down")):
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(30, 19)
        btn.setIcon(qta.icon(icon_name, color="#0E7490"))
        btn.setIconSize(btn.size())
    def change_gap(step):
        custom_gap.setValue(custom_gap.value() + (custom_gap.singleStep() * step))
        custom_gap.lineEdit().deselect()

    up_btn.clicked.connect(lambda: change_gap(1))
    down_btn.clicked.connect(lambda: change_gap(-1))
    stepper_lay.addWidget(up_btn)
    stepper_lay.addWidget(down_btn)

    gap_control = QHBoxLayout()
    gap_control.setSpacing(6)
    gap_control.addWidget(custom_gap)
    gap_control.addWidget(stepper)

    option_grid = QGridLayout()
    option_grid.setHorizontalSpacing(12)
    option_grid.setVerticalSpacing(10)
    option_grid.addWidget(custom_btn["card"], 0, 0)
    option_grid.addWidget(normal_btn["card"], 0, 1)
    option_grid.setColumnStretch(0, 1)
    option_grid.setColumnStretch(1, 1)

    gap_panel = QFrame()
    gap_panel.setFixedHeight(68)
    gap_panel.setStyleSheet("""
        QFrame {
            background: #F8FBFE;
            border: 1px solid #E0EAF5;
            border-radius: 12px;
        }
        QFrame[active="true"] {
            background: #F0F9FC;
            border: 1.5px solid #0E7490;
        }
        QLabel {
            background: transparent;
            border: none;
        }
    """)
    gap_lay = QHBoxLayout(gap_panel)
    gap_lay.setContentsMargins(14, 10, 14, 10)
    gap_lay.setSpacing(14)
    gap_title = QLabel("Top Gap")
    gap_title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700;")
    gap_note = QLabel("Used when Custom Print is selected")
    gap_note.setStyleSheet("color: #64748B; font-size: 11px;")
    gap_text = QVBoxLayout()
    gap_text.setSpacing(2)
    gap_text.addWidget(gap_title)
    gap_text.addWidget(gap_note)
    gap_lay.addLayout(gap_text)
    gap_lay.addStretch()
    gap_lay.addLayout(gap_control)

    current_mode = config.get("mode", "custom")
    selected_mode = {"value": current_mode if current_mode in buttons else "custom"}

    def set_mode(mode):
        selected_mode["value"] = mode
        for key, option in buttons.items():
            _refresh_option_button(option, key == mode)
        custom_active = mode == "custom"
        custom_gap.setEnabled(custom_active)
        up_btn.setEnabled(custom_active)
        down_btn.setEnabled(custom_active)
        stepper.setEnabled(custom_active)
        gap_panel.setProperty("active", custom_active)
        gap_panel.style().unpolish(gap_panel)
        gap_panel.style().polish(gap_panel)

    for mode, option in buttons.items():
        for widget in option.values():
            widget.mousePressEvent = lambda event, mode=mode: set_mode(mode)
    set_mode(selected_mode["value"])

    save_btn = QPushButton("Save Report Config")
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn.setStyleSheet("""
        QPushButton {
            background: #0E7490; color: white;
            border: none; border-radius: 12px;
            padding: 10px 22px; font-size: 13px; font-weight: bold;
        }
        QPushButton:hover { background: #155E75; }
    """)

    def save_report_config():
        confirm = ConfirmActionModal(
            "Save Report Config",
            "Do you want to save these report print settings?",
            confirm_label="Yes",
            cancel_label="No",
            parent=window,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            save_report_print_config({
                "mode": selected_mode["value"],
                "custom_top_gap_cm": custom_gap.value(),
            })
        except Exception as exc:
            AlertModal("Save Failed", str(exc), tone="error", parent=window).exec()
            return
        if hasattr(window, "_show_toast"):
            window._show_toast("Settings saved", "Report print settings updated successfully.")

    save_btn.clicked.connect(save_report_config)

    btn_row = QHBoxLayout()
    btn_row.addWidget(save_btn)
    btn_row.addStretch()

    body = QVBoxLayout()
    body.setSpacing(12)
    body.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
    body.addLayout(option_grid)
    body.addWidget(gap_panel)
    body.addLayout(btn_row)
    card.body().addLayout(body)
    return card


def build_settings_page(window):
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(20)

    shell = QFrame()
    shell.setStyleSheet("""
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #F4F8FD, stop:1 #FBFDFF);
        border: none;
        border-radius: 20px;
    """)
    shell_lay = QHBoxLayout(shell)
    shell_lay.setContentsMargins(18, 16, 18, 16)
    shell_lay.setSpacing(16)

    title_col = QVBoxLayout()
    title_col.setSpacing(2)
    title = QLabel("Settings")
    title.setStyleSheet(f"color: {TEXT_CLR}; font-size: 14px; font-weight: 700;")
    subtitle = QLabel("Configure database connection and report printing.")
    subtitle.setStyleSheet("color: #73839A; font-size: 11px;")
    title_col.addWidget(title)
    title_col.addWidget(subtitle)
    shell_lay.addLayout(title_col)
    shell_lay.addStretch()

    tab_wrap = QFrame()
    tab_wrap.setStyleSheet("background: #EAF0F7; border-radius: 18px;")
    tab_lay = QHBoxLayout(tab_wrap)
    tab_lay.setContentsMargins(6, 6, 6, 6)
    tab_lay.setSpacing(6)

    db_btn = QPushButton("  Database Config")
    report_btn = QPushButton("  Report Config")
    for btn, icon_name in [(db_btn, "mdi6.database-cog-outline"), (report_btn, "mdi6.file-cog-outline")]:
        btn.setObjectName("stepBtn")
        btn.setIcon(qta.icon(icon_name, color="#6B7D95"))
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tab_lay.addWidget(btn)

    shell_lay.addWidget(tab_wrap)
    lay.addWidget(shell)

    stack = QStackedWidget()
    stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    stack.addWidget(_build_database_config_tab(window))
    stack.addWidget(_build_report_config_tab(window))
    lay.addWidget(stack)
    lay.addStretch()

    def switch_tab(index):
        stack.setCurrentIndex(index)
        db_btn.setChecked(index == 0)
        report_btn.setChecked(index == 1)
        db_btn.setIcon(qta.icon("mdi6.database-cog-outline", color="#1E88E5" if index == 0 else "#6B7D95"))
        report_btn.setIcon(qta.icon("mdi6.file-cog-outline", color="#1E88E5" if index == 1 else "#6B7D95"))

    db_btn.clicked.connect(lambda: switch_tab(0))
    report_btn.clicked.connect(lambda: switch_tab(1))
    switch_tab(0)
    return page
