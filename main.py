"""
TDM Report - Therapeutic Drug Monitoring Software
Entry point
"""

import os
import sys
import faulthandler
from datetime import datetime

if sys.stderr is not None:
    faulthandler.enable()
os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont

from app_logger import log_startup, log_shutdown, log_license_activated, log_license_expired


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

    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(base_path, "softzino.png")
    logo = QPixmap(logo_path)
    if logo.isNull():
        logo = QPixmap(os.path.join(base_path, "SOFTZINO_LOGO.png"))
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
    app = QApplication(sys.argv)

    from license_manager import LicenseManager

    lm = LicenseManager()
    if not lm.is_licensed():
        from activation_window import ActivationWindow

        win = ActivationWindow(lm)
        if win.exec() != ActivationWindow.DialogCode.Accepted:
            sys.exit(0)

    lm.start_session()
    log_startup()
    info = lm.license_info()
    log_license_activated(info.get("license_key", ""), info.get("expires_at_local", ""))

    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    from tdm_report import TDMMainWindow, STYLE
    from database import create_database_backup, test_db_connection

    app.setStyleSheet(STYLE)

    # Check DB connection before opening main window
    if test_db_connection() is not None:
        splash.hide()
        from db_connection_dialog import DBConnectionDialog
        dlg = DBConnectionDialog()
        if dlg.exec() != DBConnectionDialog.DialogCode.Accepted:
            sys.exit(0)
        splash.show()
        app.processEvents()

    window = TDMMainWindow()
    window.show()
    splash.finish(window)

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
