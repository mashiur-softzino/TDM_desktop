"""
Activation Window - PyQt6 UI for license key entry
"""

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from core.app_paths import asset_path
from core.license_manager import LicenseManager


LICENSE_KEY_PATTERN = re.compile(
    r"^LIC-[A-Z0-9]{8}-[A-Z0-9]{8}-[A-Z0-9]{8}-[A-Z0-9]{8}$"
)


class ActivationWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, manager: LicenseManager, license_key: str):
        super().__init__()
        self.manager = manager
        self.license_key = license_key

    def run(self):
        ok, err = self.manager.activate(self.license_key)
        self.done.emit(ok, err)


class ActivationWindow(QDialog):
    def __init__(self, manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.worker: ActivationWorker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("TDM Report - License Activation")
        self.setFixedSize(560, 380)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet("""
            QDialog {
                background: #F4F8FD;
            }
            QFrame#hero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0A234F, stop:1 #123B7A);
                border-radius: 18px;
            }
            QLabel#eyebrow {
                color: #A9C4EB;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#heroTitle {
                color: white;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#heroSub {
                color: #D9E7FA;
                font-size: 12px;
            }
            QFrame#formCard {
                background: white;
                border: 1px solid #D7E3F4;
                border-radius: 16px;
            }
            QLabel#sectionTitle {
                color: #17345F;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#sectionSub {
                color: #617796;
                font-size: 12px;
            }
            QLabel#fieldLabel {
                color: #26466F;
                font-size: 13px;
                font-weight: 700;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(22, 20, 22, 20)
        hero_lay.setSpacing(16)

        logo_label = QLabel()
        logo_label.setFixedSize(62, 62)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = QPixmap(str(asset_path("softzino.png")))
        if not logo.isNull():
            logo_label.setPixmap(logo.scaled(
                54, 54,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        hero_lay.addWidget(logo_label)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(2)

        eyebrow = QLabel("TDM DESKTOP APPLICATION")
        eyebrow.setObjectName("eyebrow")
        hero_text.addWidget(eyebrow)

        title = QLabel("TDM Report")
        title.setObjectName("heroTitle")
        hero_text.addWidget(title)

        subtitle = QLabel("Therapeutic Drug Monitoring - License Activation")
        subtitle.setObjectName("heroSub")
        hero_text.addWidget(subtitle)

        hero_lay.addLayout(hero_text, 1)
        root.addWidget(hero)

        form_card = QFrame()
        form_card.setObjectName("formCard")
        form_lay = QVBoxLayout(form_card)
        form_lay.setContentsMargins(22, 20, 22, 20)
        form_lay.setSpacing(12)

        section_title = QLabel("Activate this device")
        section_title.setObjectName("sectionTitle")
        form_lay.addWidget(section_title)

        section_sub = QLabel(
            "Enter your Softzino-issued license key to activate TDM on this PC. "
            "If you need help, please contact the Softzino team for license or "
            "activation support."
        )
        section_sub.setObjectName("sectionSub")
        section_sub.setWordWrap(True)
        form_lay.addWidget(section_sub)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #E3ECF7;")
        form_lay.addWidget(divider)

        key_label = QLabel("License Key")
        key_label.setObjectName("fieldLabel")
        form_lay.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("LIC-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX")
        self.key_input.setFixedHeight(42)
        self.key_input.setStyleSheet("""
            QLineEdit {
                background: #F9FBFE;
                color: #17345F;
                font-size: 14px;
                padding: 6px 10px;
                border: 1px solid #BFD0E6;
                border-radius: 10px;
            }
            QLineEdit:focus {
                border: 1px solid #2F6FC2;
                background: white;
            }
        """)
        self.key_input.returnPressed.connect(self._on_activate)
        form_lay.addWidget(self.key_input)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #C0392B; font-size: 12px;")
        form_lay.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #D3DFF0;
                color: #1F3D66;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 10px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: #BECFE7;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        self.activate_btn = QPushButton("Activate License")
        self.activate_btn.setFixedHeight(40)
        self.activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #C78614, stop:1 #E0A22E);
                color: #102039;
                font-size: 14px;
                font-weight: 700;
                border: none;
                border-radius: 10px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #A96B08, stop:1 #C98918);
            }
            QPushButton:disabled {
                background: #D6DCE5;
                color: #6B7280;
            }
        """)
        self.activate_btn.clicked.connect(self._on_activate)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.activate_btn, 1)
        form_lay.addLayout(btn_row)

        root.addWidget(form_card)

    def _on_activate(self):
        key = self.key_input.text().strip().upper()
        self.key_input.setText(key)
        if not key:
            self.status_label.setText("Please enter a license key.")
            return
        if not LICENSE_KEY_PATTERN.fullmatch(key):
            self.status_label.setText("Please enter a valid license key.")
            return

        self.activate_btn.setEnabled(False)
        self.activate_btn.setText("Activating...")
        self.status_label.setText("")

        self.worker = ActivationWorker(self.manager, key)
        self.worker.done.connect(self._on_done)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_done(self, success: bool, error: str):
        self.activate_btn.setEnabled(True)
        self.activate_btn.setText("Activate License")

        if success:
            self.accept()
        else:
            self.status_label.setText(f"Error: {error}")

    def _on_worker_finished(self):
        if self.sender() is self.worker:
            self.worker = None

    def closeEvent(self, event):
        worker = self.worker
        if worker is not None:
            try:
                is_running = worker.isRunning()
            except RuntimeError:
                self.worker = None
                is_running = False

            if is_running:
                try:
                    worker.done.disconnect(self._on_done)
                except (TypeError, RuntimeError):
                    pass
                worker.quit()
                worker.wait(2000)
                self.worker = None
        super().closeEvent(event)
