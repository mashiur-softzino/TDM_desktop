import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import QRegularExpression, Qt
from PyQt6.QtGui import QPixmap, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from app_paths import ensure_data_dirs
from database import (
    add_signatory,
    delete_signatory,
    is_signatory_phone_exists,
    load_signatories,
    update_signatory,
)
from tdm_validators import validate_signature_file, is_valid_phone
from ui_constants import BLUE, BORDER, TEXT_CLR, small_label
from ui_widgets import ConfirmActionModal, ToastMessage


class SignatoryManagementModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Signatories")
        self.setFixedWidth(550)
        self.setFixedHeight(600)
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog {
                background: white;
                border-radius: 20px;
            }
            """
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner = QFrame()
        banner.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #1E293B, stop:1 #334155);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            """
        )
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
        s = QLabel("Configure signatories and technologists for reports")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.7); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255,255,255,0.1); color: white;
                border: none; border-radius: 15px; font-size: 18px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
            """
        )
        close_btn.clicked.connect(self.reject)
        banner_lay.addWidget(close_btn)
        lay.addWidget(banner)

        body = QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(18)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(6)
        self.list_widget.setStyleSheet(
            f"""
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
            """
        )
        body.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        add_btn = QPushButton("Add New Signatory")
        add_btn.setFixedHeight(40)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            """
            QPushButton {
                background: #16A34A; color: white; border: none; border-radius: 10px;
                padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #15803D; }
            """
        )
        add_btn.clicked.connect(self._add_signatory)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(40)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(
            """
            QPushButton {
                background: #F1F5F9; color: #475569; border: 1.5px solid #E2E8F0;
                border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #E2E8F0; }
            """
        )
        edit_btn.clicked.connect(self._edit_signatory)

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            """
            QPushButton {
                background: #FEF2F2; color: #DC2626; border: 1.5px solid #FEE2E2;
                border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #DC2626; color: white; border-color: #B91C1C; }
            """
        )
        del_btn.clicked.connect(self._delete_signatory)

        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        body.addLayout(btn_row)

        wrapper = QFrame()
        wrapper.setLayout(body)
        lay.addWidget(wrapper)
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for signatory in reversed(load_signatories()):
            item = QListWidgetItem(f"{signatory['name']} ({signatory['designation'] or 'No designation'})")
            item.setData(Qt.ItemDataRole.UserRole, signatory)
            self.list_widget.addItem(item)

    def _add_signatory(self):
        dlg = SignatoryEditModal(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_list()

    def _edit_signatory(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        signatory = item.data(Qt.ItemDataRole.UserRole)
        dlg = SignatoryEditModal(signatory, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_list()

    def _delete_signatory(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        signatory = item.data(Qt.ItemDataRole.UserRole)
        dlg = ConfirmActionModal(
            "Delete Signatory",
            f"Are you sure you want to delete \"{signatory['name']}\" from the Signatory List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        delete_signatory(signatory['id'])
        self._refresh_list()


class SignatoryEditModal(QDialog):
    def __init__(self, signatory=None, parent=None):
        super().__init__(parent)
        self.signatory = signatory
        self.setWindowTitle("Add Signatory" if not signatory else "Edit Signatory")
        self.setFixedWidth(800)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: white; border-radius: 20px; }")

        self._toast = ToastMessage(self)
        self._toast.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner = QFrame()
        banner.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #7C3AED, stop:1 #8B5CF6);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            """
        )
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(
            qta.icon("mdi6.account-plus" if not signatory else "mdi6.account-edit", color="white").pixmap(22, 22)
        )
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        t = QLabel("Add New Signatory" if not signatory else "Edit Signatory Details")
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Enter signatory name, description, phone and signature")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.75); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        lay.addWidget(banner)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(32, 28, 32, 28)
        body_lay.setSpacing(20)

        row1 = QHBoxLayout()
        row1.setSpacing(24)

        name_sec = QVBoxLayout()
        name_sec.setSpacing(8)
        name_label = QHBoxLayout()
        name_label.setSpacing(4)
        name_label.addWidget(small_label("FULL NAME", color="#64748B", size=10, bold=True))
        name_req_star = QLabel("*")
        name_req_star.setStyleSheet("color: #DC2626; font-size: 14px; font-weight: bold; background: transparent;")
        name_label.addWidget(name_req_star)
        name_label.addStretch()
        name_sec.addLayout(name_label)
        self.name_edit = QLineEdit(signatory["name"] if signatory else "")
        self.name_edit.setPlaceholderText("e.g. Dr. John Doe")
        self.name_edit.setStyleSheet(self._input_style())
        name_sec.addWidget(self.name_edit)
        row1.addLayout(name_sec, 3)

        type_sec = QVBoxLayout()
        type_sec.setSpacing(8)
        type_sec.addWidget(small_label("SIGNATORY TYPE", color="#64748B", size=10, bold=True))
        arrow_path = os.path.join(tempfile.gettempdir(), "tdm_staff_arrow_down.png")
        qta.icon("mdi6.chevron-down", color="#64748B").pixmap(14, 14).save(arrow_path)
        arrow_path = arrow_path.replace("\\", "/")

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Doctor", "Technologist"])
        self.type_combo.setStyleSheet(self._input_style(arrow_path))
        if signatory and signatory.get("type"):
            self.type_combo.setCurrentText(signatory["type"].capitalize())
        type_sec.addWidget(self.type_combo)
        row1.addLayout(type_sec, 2)
        body_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(24)

        desc_sec = QVBoxLayout()
        desc_sec.setSpacing(8)
        desc_sec.addWidget(small_label("DESCRIPTION", color="#64748B", size=10, bold=True))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlainText(signatory["designation"] if signatory else "")
        self.desc_edit.setPlaceholderText("e.g. Degrees, Department...")
        self.desc_edit.setStyleSheet(self._input_style())
        self.desc_edit.setFixedHeight(120)
        desc_sec.addWidget(self.desc_edit)
        row2.addLayout(desc_sec, 4)

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

        self.phone_edit = QLineEdit(signatory.get("phone", "") if signatory else "")
        self.phone_edit.setPlaceholderText("e.g. 01XXXXXXXXX")
        self.phone_edit.setMaxLength(11)
        self.phone_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,11}"), self.phone_edit))
        self.phone_edit.setStyleSheet(self._input_style())
        phone_sec.addWidget(self.phone_edit)
        phone_sec.addStretch()
        row2.addLayout(phone_sec, 3)
        body_lay.addLayout(row2)

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
        self.sig_path = signatory["signature_path"] if signatory else None
        sig_box_lay.addWidget(self.sig_label)
        sig_row.addWidget(sig_box, 2)

        sig_actions = QVBoxLayout()
        sig_actions.setSpacing(10)

        upload_btn = QPushButton("Upload Signature")
        upload_btn.setFixedHeight(46)
        upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_btn.setIcon(qta.icon("mdi6.upload", color="#2563EB"))
        upload_btn.setStyleSheet(
            """
            QPushButton {
                background: #EFF6FF; color: #2563EB; border: 1.5px solid #BFDBFE;
                border-radius: 12px; padding: 8px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #DBEAFE; }
            """
        )
        upload_btn.clicked.connect(self._upload_sig)
        sig_actions.addWidget(upload_btn)

        self.remove_sig_btn = QPushButton("Remove Signature")
        self.remove_sig_btn.setFixedHeight(46)
        self.remove_sig_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_sig_btn.setIcon(qta.icon("mdi6.close", color="#DC2626"))
        self.remove_sig_btn.setStyleSheet(
            """
            QPushButton {
                background: #FEF2F2; color: #DC2626; border: 1.5px solid #FECACA;
                border-radius: 12px; padding: 8px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #FEE2E2; }
            """
        )
        self.remove_sig_btn.clicked.connect(self._remove_sig)
        self.remove_sig_btn.setVisible(bool(self.sig_path))
        sig_actions.addWidget(self.remove_sig_btn)
        sig_actions.addStretch()
        sig_row.addLayout(sig_actions, 1)
        self._update_sig_preview()

        sig_sec.addLayout(sig_row)
        sig_note = QLabel("Note: Upload PNG, JPG, JPEG, or BMP signature image up to 2 MB.")
        sig_note.setWordWrap(True)
        sig_note.setStyleSheet("color: #64748B; font-size: 11px; background: transparent;")
        sig_sec.addWidget(sig_note)
        body_lay.addLayout(sig_sec)

        body_lay.addSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(42)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background: #FEE2E2; color: #B91C1C;
                border: 1.5px solid #FCA5A5; border-radius: 10px;
                font-size: 13px; padding: 0 24px;
            }
            QPushButton:hover {
                background: #DC2626; color: white;
                border: 1.5px solid #B91C1C;
            }
            """
        )
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Details")
        save_btn.setFixedHeight(42)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            """
            QPushButton {
                background: #7C3AED; color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0 24px;
            }
            QPushButton:hover { background: #6D28D9; }
            """
        )
        save_btn.clicked.connect(self._save)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        body_lay.addLayout(btn_row)
        lay.addWidget(body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def _position_toast(self):
        width = min(380, max(320, self.width() - 48))
        self._toast.setFixedWidth(width)
        self._toast.move(self.width() - width - 24, 24)

    def _show_error(self, title, msg):
        self._position_toast()
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
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not file_path:
            return
        error = validate_signature_file(file_path)
        if error:
            self._show_error("File Error" if "read" in error.lower() else "File Too Large", error)
            return
        sig_dir = ensure_data_dirs() / "signatures"
        ext = Path(file_path).suffix
        dest_name = f"sig_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        dest_path = sig_dir / dest_name
        try:
            shutil.copy2(file_path, dest_path)
            self.sig_path = str(dest_path)
            self._update_sig_preview()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to copy signature: {exc}")

    def _remove_sig(self):
        self.sig_path = None
        self._update_sig_preview()

    def _update_sig_preview(self):
        if self.sig_path and Path(self.sig_path).exists():
            pix = QPixmap(self.sig_path)
            self.sig_label.setPixmap(
                pix.scaled(
                    self.sig_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.sig_label.setText("")
        else:
            self.sig_label.setPixmap(QPixmap())
            self.sig_label.setText("No Signature Uploaded")
        self.remove_sig_btn.setVisible(bool(self.sig_path))

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
        if not is_valid_phone(phone):
            self._show_error("Invalid Phone", "Please enter a valid 11-digit phone number.")
            return
        if is_signatory_phone_exists(phone, exclude_id=self.signatory["id"] if self.signatory else None):
            self._show_error("Duplicate Phone", "This phone number is already registered.")
            return

        if self.signatory:
            update_signatory(self.signatory["id"], name, desc, self.sig_path, type=type_str, phone=phone)
        else:
            add_signatory(name, desc, self.sig_path, type=type_str, phone=phone)
        self.accept()

