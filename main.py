"""
TDM Report — Therapeutic Drug Monitoring Software
Entry point
"""

import os
import sys
import faulthandler
from datetime import datetime
if sys.stderr is not None:
    faulthandler.enable()
os.environ.setdefault('QT_MAC_WANTS_LAYER', '1')

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont
from app_logger import log_startup, log_shutdown, log_license_activated, log_license_expired


def _make_splash(app: QApplication) -> QSplashScreen:
    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0

    w, h = 420, 220
    px = QPixmap(int(w * dpr), int(h * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(QColor("#0D2B6B"))

    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Logo image (top-centre) — sys._MEIPASS used when running as PyInstaller EXE
    _base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(_base, "SOFTZINO_LOGO.png")
    logo = QPixmap(logo_path)
    if not logo.isNull():
        logo = logo.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)
        lx = (w - logo.width()) // 2
        painter.drawPixmap(lx, 30, logo)

    # App name
    font = QFont("Arial", 16, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(0, 105, w, 28, Qt.AlignmentFlag.AlignHCenter, "TDM Report")

    # Subtitle
    font2 = QFont("Arial", 10)
    painter.setFont(font2)
    painter.setPen(QColor("#A0B4D0"))
    painter.drawText(0, 135, w, 20, Qt.AlignmentFlag.AlignHCenter,
                     "Therapeutic Drug Monitoring")

    # Loading text
    font3 = QFont("Arial", 9)
    painter.setFont(font3)
    painter.setPen(QColor("#6B8BAF"))
    painter.drawText(0, 185, w, 20, Qt.AlignmentFlag.AlignHCenter, "Loading, please wait…")

    painter.end()

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)
    splash.setFixedSize(w, h)
    return splash


def main():
    app = QApplication(sys.argv)

    # ── License check ──────────────────────────────
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
    # ───────────────────────────────────────────────

    # Show splash while heavy modules (matplotlib, scipy, numpy) load
    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    # Import deferred until after splash is visible — all heavy libraries load here
    from tdm_report import TDMMainWindow, STYLE
    from database import create_database_backup
    app.setStyleSheet(STYLE)

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
        # QTimer uses a 32-bit int (max ~24.8 days). For longer licenses,
        # skip the precise timer — expiry_timer (5-second polling) handles it.
        MAX_QTIMER_MS = 2_147_483_647
        if remaining_ms <= MAX_QTIMER_MS:
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


if __name__ == '__main__':
    main()
