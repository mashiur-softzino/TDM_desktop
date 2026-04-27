"""
Activation Window — PyQt6 UI for license key entry
"""

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from license_manager import LicenseManager


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
        ok, err = self.manager.verify_key(self.license_key)
        if not ok:
            self.done.emit(False, err)
            return
        ok, err = self.manager.activate(self.license_key)
        self.done.emit(ok, err)


class ActivationWindow(QDialog):
    def __init__(self, manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.worker: ActivationWorker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("AUC Sampler — Activation")
        self.setFixedSize(480, 280)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(16)

        # Title
        title = QLabel("Software Activation")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # Subtitle
        sub = QLabel("Enter the license key provided by Softzino.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        root.addWidget(sub)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444444;")
        root.addWidget(line)

        # Key input
        key_label = QLabel("License Key")
        key_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        root.addWidget(key_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("LIC-XXXXXXXX-XXXXXXXX-XXXXXXXX")
        self.key_input.setFixedHeight(38)
        self.key_input.setStyleSheet(
            "font-size: 14px; padding: 4px 8px; "
            "border: 1px solid #555; border-radius: 4px;"
        )
        self.key_input.returnPressed.connect(self._on_activate)
        root.addWidget(self.key_input)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.activate_btn = QPushButton("Activate")
        self.activate_btn.setFixedHeight(38)
        self.activate_btn.setStyleSheet(
            "background-color: #f59e0b; color: black; font-weight: bold; "
            "font-size: 14px; border-radius: 4px;"
        )
        self.activate_btn.clicked.connect(self._on_activate)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(
            "background-color: #333; color: white; "
            "font-size: 14px; border-radius: 4px;"
        )
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.activate_btn)
        root.addLayout(btn_row)

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
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_done(self, success: bool, error: str):
        self.activate_btn.setEnabled(True)
        self.activate_btn.setText("Activate")

        if success:
            self.accept()
        else:
            self.status_label.setText(f"Error: {error}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.done.disconnect()
            self.worker.quit()
            self.worker.wait(2000)
        super().closeEvent(event)
