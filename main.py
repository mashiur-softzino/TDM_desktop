"""
TDM Report - Therapeutic Drug Monitoring Software
Entry point
"""

import os
import sys
import faulthandler
import ctypes
import threading
from datetime import datetime

if sys.stderr is not None:
    faulthandler.enable()
os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QIcon

from core.app_paths import asset_path


def _load_loggers():
    try:
        from core.app_logger import (
            log_startup,
            log_shutdown,
            log_license_activated,
            log_license_expired,
        )
        return log_startup, log_shutdown, log_license_activated, log_license_expired
    except Exception:
        def _noop(*_args, **_kwargs):
            return None
        return _noop, _noop, _noop, _noop


def _start_report_renderer_warmup():
    def warmup():
        try:
            from reports.report_print import build_report_html

            build_report_html(
                patient={
                    "name": "Warmup",
                    "age": "N/A",
                    "sex": "N/A",
                    "ref_by": "N/A",
                    "invoice_number": "N/A",
                    "invoice_date": "N/A",
                    "report_number": "N/A",
                    "delivery_date": "N/A",
                    "tx_date": "N/A",
                    "diag": "N/A",
                    "med": "N/A",
                    "drug": "MPA",
                    "preparation": "N/A",
                    "dose": "N/A",
                    "dose_dt": "N/A",
                    "sample_collection_date": "N/A",
                    "lab_no": "N/A",
                    "test": "Serum",
                },
                pk={
                    "auc_0_last": 30.0,
                    "auc_0_12": 30.0,
                    "auc_lss": None,
                    "lss_equation": "",
                    "lambda_z": None,
                    "t_half": None,
                    "r_squared": None,
                    "t_last": 1.0,
                    "c_trough": 2.0,
                    "c_last": 4.0,
                },
                interp="Normal",
                times=[0.0, 0.5, 1.0],
                concs=[2.0, 8.0, 4.0],
                print_config={"mode": "custom", "custom_top_gap_cm": 2.3},
            )
        except Exception:
            pass

    threading.Thread(target=warmup, name="report-renderer-warmup", daemon=True).start()


def _make_splash(app: QApplication) -> QSplashScreen:
    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0

    w, h = 520, 280
    px = QPixmap(int(w * dpr), int(h * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(QColor("#0A234F"))

    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, w, h, QColor("#0A234F"))
    painter.setBrush(QColor("#123B7A"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(-45, -15, 250, 180)
    painter.drawEllipse(330, 150, 210, 140)
    painter.setBrush(QColor(255, 255, 255, 18))
    painter.drawRoundedRect(24, 22, w - 48, h - 44, 26, 26)

    logo = QPixmap(str(asset_path("softzino.png")))
    if not logo.isNull():
        logo = logo.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation)
        logo_x = (w - logo.width()) // 2
        painter.drawPixmap(logo_x, 40, logo)

    title_font = QFont("Arial", 18, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(0, 122, w, 36, Qt.AlignmentFlag.AlignHCenter, "TDM Report")

    subtitle_font = QFont("Arial", 11)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#C8D8F2"))
    painter.drawText(0, 158, w, 24, Qt.AlignmentFlag.AlignHCenter, "Therapeutic Drug Monitoring")

    loading_font = QFont("Arial", 10)
    painter.setFont(loading_font)
    painter.setPen(QColor("#9DB7DD"))
    painter.drawText(0, 226, w, 24, Qt.AlignmentFlag.AlignHCenter, "Loading, please wait...")

    painter.end()

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)
    splash.setFixedSize(w, h)
    return splash


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Softzino.TDMReport"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app_icon = QIcon(str(asset_path("tdm_logo_icon.png")))
    if app_icon.isNull():
        app_icon = QIcon(str(asset_path("tdm_logo.png")))
    if app_icon.isNull():
        app_icon = QIcon(str(asset_path("tdm_logo.ico")))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    log_startup, log_shutdown, log_license_activated, log_license_expired = _load_loggers()

    from core.license_manager import LicenseManager

    lm = LicenseManager()
    if not lm.is_licensed():
        if lm.needs_clock_verification():
            splash.hide()
            message = QMessageBox()
            message.setIcon(QMessageBox.Icon.Warning)
            message.setWindowTitle("License Verification Required")
            message.setText("System clock change detected.")
            message.setInformativeText(lm.last_error())
            message.setStandardButtons(QMessageBox.StandardButton.Ok)
            message.exec()
            sys.exit(0)

        from ui.activation_window import ActivationWindow

        splash.hide()
        win = ActivationWindow(lm)
        if win.exec() != ActivationWindow.DialogCode.Accepted:
            sys.exit(0)
        splash.show()
        app.processEvents()

    lm.start_session()
    log_startup()
    info = lm.license_info()
    log_license_activated(info.get("license_key", ""), info.get("expires_at_local", ""))

    from core.database import create_database_backup, init_db
    from ui.ui_constants import DEFAULT_DURATION_OPTIONS

    while True:
        try:
            duration_options = init_db(DEFAULT_DURATION_OPTIONS)
            break
        except Exception:
            splash.hide()
            from ui.db_connection_dialog import DBConnectionDialog
            dlg = DBConnectionDialog()
            if dlg.exec() != DBConnectionDialog.DialogCode.Accepted:
                sys.exit(0)
            splash.show()
            app.processEvents()

    from app.tdm_report import TDMMainWindow, STYLE

    app.setStyleSheet(STYLE)

    window = TDMMainWindow(duration_options=duration_options, db_initialized=True)
    window.show()
    splash.finish(window)
    QTimer.singleShot(500, _start_report_renderer_warmup)

    expiry_popup_shown = False
    precise_expiry_timer = QTimer()
    precise_expiry_timer.setSingleShot(True)

    def handle_runtime_expiry():
        nonlocal expiry_popup_shown
        if expiry_popup_shown or not lm.has_expired():
            return

        expiry_popup_shown = True
        log_license_expired()
        lm._stop_heartbeat()
        precise_expiry_timer.stop()
        expiry_timer.stop()

        message = QMessageBox(window)
        message.setIcon(QMessageBox.Icon.Warning)
        license_error = lm.last_error()
        if license_error:
            message.setWindowTitle("License Verification Required")
            message.setText("License verification is required.")
            message.setInformativeText(license_error)
        else:
            message.setWindowTitle("License Expired")
            message.setText("Your license has expired.")
            message.setInformativeText(
                "Please extend your license or purchase a new license to continue using this software."
            )
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.exec()

        window.close()
        app.quit()

    def schedule_runtime_expiry_check():
        expires_at = lm.expires_at_local()
        if expires_at is None:
            return

        remaining_ms = max(
            0,
            int((expires_at - datetime.now().astimezone()).total_seconds() * 1000),
        )
        max_qtimer_ms = 2_147_483_647
        if remaining_ms <= max_qtimer_ms:
            precise_expiry_timer.start(remaining_ms)

    precise_expiry_timer.timeout.connect(handle_runtime_expiry)
    schedule_runtime_expiry_check()

    expiry_timer = QTimer()
    expiry_timer.setInterval(5000)
    expiry_timer.timeout.connect(handle_runtime_expiry)
    expiry_timer.start()

    backup_timer = QTimer()
    backup_timer.setInterval(30 * 60 * 1000)
    backup_timer.timeout.connect(lambda: create_database_backup("scheduled"))
    backup_timer.start()

    def cleanup_runtime_checks():
        precise_expiry_timer.stop()
        expiry_timer.stop()
        backup_timer.stop()
        create_database_backup("shutdown")
        lm._stop_heartbeat()
        log_shutdown()

    app.aboutToQuit.connect(cleanup_runtime_checks)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
