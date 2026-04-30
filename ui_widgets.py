"""
Reusable UI widget classes for the TDM Report application.
"""

from ui_constants import (
    BG, CARD_BG, BLUE, BLUE_DARK, NAVY, LABEL_CLR, TEXT_CLR,
    BORDER, RED, GREEN, ORANGE, make_shadow, small_label, value_label,
)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QScrollArea, QPushButton,
    QComboBox, QDialog, QSizePolicy,
    QGraphicsDropShadowEffect, QCalendarWidget,
    QToolButton, QTimeEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QDate, QDateTime, QPoint, QEvent,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPalette, QIntValidator,
)
import qtawesome as qta


# ─────────────────────────────────────────
# Card widget
# ─────────────────────────────────────────
class Card(QFrame):
    def __init__(self, title='', icon='', icon_color=BLUE, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {CARD_BG};
                border-radius: 16px;
                border: none;
            }}
        """)
        self.setGraphicsEffect(make_shadow(8, 2, 15))

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 14, 20, 14)
        self._layout.setSpacing(10)

        self._header_lay = None
        if title:
            header = QHBoxLayout()
            header.setSpacing(10)
            if icon:
                icon_lbl = QLabel()
                icon_lbl.setFixedSize(26, 26)
                icon_lbl.setPixmap(qta.icon(icon, color=icon_color).pixmap(22, 22))
                icon_lbl.setStyleSheet("background: transparent;")
                header.addWidget(icon_lbl)
            t = QLabel(title)
            t.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {TEXT_CLR};"
            )
            header.addWidget(t)
            header.addStretch()
            self._header_lay = header
            self._layout.addLayout(header)

    def body(self):
        return self._layout


# ─────────────────────────────────────────
# Toggle button group (4h / 6h / 10h)
# ─────────────────────────────────────────
class ToggleButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setMinimumWidth(72)
        self._update_style()
        self.toggled.connect(self._update_style)

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #EA580C, stop:1 #F97316);
                    color: white;
                    border: none;
                    border-radius: 14px;
                    font-size: 14px;
                    font-weight: bold;
                    padding-left: 18px;
                    padding-right: 18px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #FFF7ED;
                    color: #9A3412;
                    border: 1px solid #FDBA74;
                    border-radius: 14px;
                    font-size: 14px;
                    padding-left: 18px;
                    padding-right: 18px;
                }
                QPushButton:hover {
                    background: #FFEDD5;
                    border: 1px solid #F97316;
                }
            """)


class DurationEditModal(QDialog):
    def __init__(self, title: str, action_label: str, initial_value: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(380)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: white; border-radius: 20px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner = QFrame()
        banner.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #EA580C, stop:1 #F97316);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.timer-edit-outline", color="white").pixmap(22, 22))
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Enter the number of sample points")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.75); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        lay.addWidget(banner)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 20, 24, 20)
        body_lay.setSpacing(16)
        lbl = QLabel("Sample Points")
        lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {LABEL_CLR}; letter-spacing: 0.8px;")
        body_lay.addWidget(lbl)

        self.edit = QLineEdit(initial_value)
        self.edit.setMaxLength(2)
        self.edit.setPlaceholderText("e.g. 5")
        self.edit.setStyleSheet(f"""
            QLineEdit {{
                background: #F7FAFE;
                border: 1.5px solid {BORDER};
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 14px;
                color: {TEXT_CLR};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BLUE};
                background: white;
            }}
        """)
        self.edit.returnPressed.connect(self.accept)
        self.edit.installEventFilter(self)
        body_lay.addWidget(self.edit)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: white; color: {LABEL_CLR};
                border: 1.5px solid {BORDER}; border-radius: 10px;
                font-size: 13px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: #F4F8FC; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton(action_label)
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #EA580C; color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0 20px;
            }
            QPushButton:hover { background: #C2410C; }
        """)
        save_btn.setDefault(True)
        save_btn.setAutoDefault(True)
        save_btn.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        body_lay.addLayout(btn_row)
        lay.addWidget(body)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept()
                return True
        return super().eventFilter(obj, event)

    def accept(self):
        text = self.edit.text().strip()
        if not text.isdigit() or not (2 <= int(text) <= 12):
            self.edit.setFocus()
            parent = self.parent()
            window = parent.window() if parent is not None else self.window()
            if hasattr(window, "_show_toast"):
                window._show_toast("Invalid sample points", "Sample points must be between 2 and 12.", tone="warning")
            return
        super().accept()

    def get_value(self):
        text = self.edit.text().strip()
        if not text.isdigit() or not (1 <= int(text) <= 12):
            return None
        return int(text)


class ConfirmActionModal(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Yes",
        cancel_label: str = "No",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(380)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: white; border-radius: 20px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner = QFrame()
        banner.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #DC2626, stop:1 #F97316);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(24, 20, 24, 20)
        banner_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon("mdi6.alert-outline", color="white").pixmap(22, 22))
        icon_lbl.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 20px;")
        banner_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
        s = QLabel("Please confirm this action")
        s.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.75); background: transparent;")
        title_col.addWidget(t)
        title_col.addWidget(s)
        banner_lay.addLayout(title_col)
        banner_lay.addStretch()
        lay.addWidget(banner)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 20, 24, 20)
        body_lay.setSpacing(16)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"font-size: 13px; color: {TEXT_CLR}; line-height: 1.35;")
        body_lay.addWidget(msg)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton(cancel_label)
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: white; color: {LABEL_CLR};
                border: 1.5px solid {BORDER}; border-radius: 10px;
                font-size: 13px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: #F4F8FC; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton(confirm_label)
        confirm_btn.setFixedHeight(40)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #DC2626; color: white;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: bold; padding: 0 20px;
            }
            QPushButton:hover { background: #B91C1C; }
        """)
        confirm_btn.setDefault(True)
        confirm_btn.setAutoDefault(True)
        confirm_btn.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        body_lay.addLayout(btn_row)
        lay.addWidget(body)


class DurationChip(QWidget):
    selected = pyqtSignal(int)
    removed = pyqtSignal(int)

    def __init__(self, duration: int, parent=None):
        super().__init__(parent)
        self._duration = int(duration)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(84, 58)

        self._chip = QFrame(self)
        self._chip.setObjectName("durationChipBody")
        self._chip.setGeometry(0, 10, 74, 48)

        self._label = QLabel(f"{self._duration}pts", self._chip)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setGeometry(0, 10, 74, 28)
        self._label.setStyleSheet("background: transparent; font-size: 14px; font-weight: 700;")

        self._close_btn = QPushButton(self)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.move(62, 0)
        self._close_btn.setIcon(qta.icon("mdi6.close", color="#94A3B8"))
        self._close_btn.setIconSize(self._close_btn.size() * 0.65)
        self._close_btn.setStyleSheet("QPushButton { background: white; border: 1px solid #E2E8F0; border-radius: 10px; }")
        self._close_btn.clicked.connect(lambda: self.removed.emit(self._duration))

        self.set_selected(False)

    @property
    def duration(self):
        return self._duration

    def set_selected(self, selected: bool):
        if selected:
            self._chip.setStyleSheet("""
                QFrame#durationChipBody {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EA580C, stop:1 #F97316);
                    border: none;
                    border-radius: 16px;
                }
            """)
            self._label.setStyleSheet("background: transparent; font-size: 14px; font-weight: 700; color: white;")
        else:
            self._chip.setStyleSheet("""
                QFrame#durationChipBody {
                    background: white;
                    border: 1.5px solid #FDBA74;
                    border-radius: 16px;
                }
            """)
            self._label.setStyleSheet("background: transparent; font-size: 14px; font-weight: 700; color: #9A3412;")

    def mousePressEvent(self, event):
        self.selected.emit(self._duration)
        super().mousePressEvent(event)


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


# ─────────────────────────────────────────
# Result stat widget
# ─────────────────────────────────────────
from PyQt6.QtCore import QRect

class IconCircle(QWidget):
    """Rounded square with a qtawesome vector icon inside."""
    def __init__(self, icon_name: str, icon_color: str, bg_color: str, size=44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._bg = QColor(bg_color)
        self._icon = qta.icon(icon_name, color=icon_color)
        self._icon_size = size - 18

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setBrush(QBrush(self._bg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 13, 13)
        icon_rect = QRect(
            (self.width() - self._icon_size) // 2,
            (self.height() - self._icon_size) // 2,
            self._icon_size,
            self._icon_size,
        )
        self._icon.paint(p, icon_rect, Qt.AlignmentFlag.AlignCenter)


class StatBox(QFrame):
    """
    Modern dashboard stat card — vector icon + bold value + label.
    Layout (vertical):
        [icon circle]   ···
        value  (bold)
        label  (gray)
        unit   (lighter)
    """
    def __init__(self, label, value='—', unit='',
                 icon_name='mdi6.circle-outline',
                 icon_color='#7C3AED', icon_bg='#EDE9FE',
                 value_color=TEXT_CLR, parent=None):
        super().__init__(parent)
        self.setObjectName("statBox")
        self._default_value_color = value_color
        self._lifted = False
        self._rest_pos = None
        self._hover_anim = QPropertyAnimation(self, b"pos", self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumWidth(130)
        self.setStyleSheet("""
            QFrame#statBox {
                background: white;
                border-radius: 12px;
                border: 1.5px solid transparent;
            }
            QFrame#statBox:hover {
                background: #FFF7ED;
                border: 1.5px solid #FDBA74;
            }
        """)
        self.setGraphicsEffect(make_shadow(12, 3, 15))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(0)

        # ── Top row: icon circle + dots menu ─────
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(IconCircle(icon_name, icon_color, icon_bg, size=32))
        self._heading = QLabel(label)
        self._heading.setWordWrap(True)
        self._heading.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #111111; background: transparent;"
        )
        top.addWidget(self._heading, 1)
        top.addStretch()
        outer.addLayout(top)

        outer.addSpacing(8)

        # ── Bold value ────────────────────────────
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {value_color};"
            "background: transparent; letter-spacing: -0.5px;"
        )
        self._val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self._val)

        outer.addSpacing(2)

        # ── Label ─────────────────────────────────
        self._lbl = QLabel(label)
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(
            "font-size: 11px; color: #111111; background: transparent;"
        )
        outer.addWidget(self._lbl)

        # ── Unit ──────────────────────────────────
        if unit:
            self._unit = QLabel(unit)
            self._unit.setStyleSheet(
                "font-size: 9px; color: #111111; background: transparent;"
            )
            outer.addWidget(self._unit)
        else:
            self._unit = None

        self._warn = QLabel()
        self._warn.setWordWrap(True)
        self._warn.setStyleSheet(
            "font-size: 10px; color: #D97706; background: #FEF3C7;"
            "border-radius: 4px; padding: 2px 6px;"
        )
        self._warn.hide()
        outer.addSpacing(4)
        outer.addWidget(self._warn)

    def set_warning(self, text):
        if text:
            self._warn.setText(text)
            self._warn.show()
        else:
            self._warn.hide()

    def set_value(self, val, color=None):
        self._val.setText(val)
        c = color or self._default_value_color
        self._val.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {c};"
            "background: transparent; letter-spacing: -0.5px;"
        )

    def set_label(self, text):
        self._heading.setText(text)
        self._lbl.setText(text)

    def set_unit(self, text):
        if self._unit is None:
            self._unit = QLabel()
            self._unit.setStyleSheet(
                "font-size: 10px; color: #B0BEC5; background: transparent;"
            )
            self.layout().addWidget(self._unit)
        self._unit.setText(text)

    def enterEvent(self, event):
        if not self._lifted:
            self._rest_pos = self.pos()
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self.pos())
            self._hover_anim.setEndValue(self._rest_pos + QPoint(0, -4))
            self._hover_anim.start()
            self.setGraphicsEffect(make_shadow(18, 8, 28))
            self._lifted = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._lifted:
            target = self._rest_pos if self._rest_pos is not None else self.pos() + QPoint(0, 4)
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self.pos())
            self._hover_anim.setEndValue(target)
            self._hover_anim.start()
            self.setGraphicsEffect(make_shadow(12, 3, 15))
            self._lifted = False
        super().leaveEvent(event)


class MonthOnlyCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        year, month = self.yearShown(), self.monthShown()
        self._page_year = year
        self._page_month = month
        self.currentPageChanged.connect(self._on_page_changed)

    def _on_page_changed(self, year, month):
        self._page_year = year
        self._page_month = month
        view = self.findChild(QWidget, "qt_calendar_calendarview")
        if view is not None:
            view.update()
        self.update()

    def paintCell(self, painter, rect, date):
        if date.year() != self._page_year or date.month() != self._page_month:
            painter.save()
            painter.fillRect(rect, QColor("white"))
            painter.restore()
            return
        super().paintCell(painter, rect, date)


class SmartDateEdit(QWidget):
    dateChanged = pyqtSignal(QDate)

    def __init__(self, parent=None, initial_date=None, placeholder="Please select date"):
        super().__init__(parent)
        self._date = initial_date
        self._placeholder = placeholder
        self.setStyleSheet("background: transparent;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._shell = QFrame()
        self._shell.setObjectName("smartDateShell")
        self._shell.setStyleSheet(f"""
            QFrame#smartDateShell {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 16px;
            }}
            QFrame#smartDateShell:hover {{
                border: 1.5px solid #D8E6F5;
            }}
        """)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(16, 0, 0, 0)
        shell_lay.setSpacing(0)

        self._text = QLineEdit()
        self._text.setReadOnly(True)
        self._text.setFrame(False)
        self._text.setPlaceholderText(self._placeholder)
        if self._date:
            self._text.setText(self._date.toString("dd  MMM  yyyy"))
        else:
            self._text.setText("")
        self._text.setStyleSheet(
            f"background: transparent; color: {TEXT_CLR}; border: none; "
            "font-size: 13px; font-weight: 600; padding: 12px 0;"
        )
        shell_lay.addWidget(self._text, 1)

        self._btn = QPushButton()
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedSize(48, 46)
        self._btn.setIcon(qta.icon("mdi6.calendar-month-outline", color=BLUE))
        self._btn.setIconSize(self._btn.size() * 0.42)
        self._btn.setStyleSheet(
            "QPushButton { background: #F4F8FD; border: none; border-left: 1px solid #E8EEF5; "
            "border-top-right-radius: 16px; border-bottom-right-radius: 16px; }"
            "QPushButton:hover { background: #ECF4FF; }"
        )
        self._btn.clicked.connect(self._show_popup)
        shell_lay.addWidget(self._btn)
        outer.addWidget(self._shell)

        self._popup = None  # created lazily on first open
        self._calendar = None

    def _build_popup(self):
        self._popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        pop_lay = QVBoxLayout(self._popup)
        pop_lay.setContentsMargins(0, 8, 0, 0)
        pop_lay.setSpacing(0)

        card = QFrame()
        card.setMinimumSize(296, 304)
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #DDE7F0;
                border-radius: 22px;
            }}
            QCalendarWidget {{
                background: transparent;
                border: none;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: transparent;
                border: none;
                border-bottom: 1px solid #EDF2F7;
                min-height: 48px;
            }}
            QCalendarWidget QToolButton {{
                color: {TEXT_CLR};
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
                subcontrol-position: center;
            }}
            QCalendarWidget QToolButton:hover {{
                background: #EEF5FF;
                color: {BLUE};
            }}
            QCalendarWidget QMenu {{
                background: white;
                border: 1px solid #DCE6F0;
                padding: 6px;
            }}
            QCalendarWidget QSpinBox {{
                background: transparent;
                border: none;
                color: {TEXT_CLR};
                font-size: 14px;
                font-weight: 700;
            }}
            QCalendarWidget QHeaderView::section {{
                background: transparent;
                color: #8A97A8;
                border: none;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 0 10px 0;
            }}
            QCalendarWidget QTableView {{
                background: white;
                border: none;
                outline: 0;
                selection-background-color: {BLUE};
                selection-color: white;
                alternate-background-color: white;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: {TEXT_CLR};
                background: white;
                font-size: 13px;
                selection-background-color: {BLUE};
                selection-color: white;
                outline: 0;
                show-decoration-selected: 1;
            }}
            QCalendarWidget QAbstractItemView::item:hover {{
                background: #EAF3FF;
                color: {BLUE};
                border-radius: 8px;
            }}
        """)
        card.setGraphicsEffect(make_shadow(22, 8, 35))
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 8)
        card_lay.setSpacing(4)

        self._calendar = MonthOnlyCalendar()
        self._calendar.setMinimumSize(300, 244)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.setGridVisible(False)
        self._calendar.setSelectedDate(self._date if self._date else QDate.currentDate())
        self._calendar.setDateEditEnabled(False)
        self._calendar.setNavigationBarVisible(True)
        self._calendar.clicked.connect(self._on_date_selected)
        cal_palette = self._calendar.palette()
        cal_palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        cal_palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        cal_palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_CLR))
        self._calendar.setPalette(cal_palette)
        card_lay.addWidget(self._calendar)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        today_btn = QPushButton("Today")
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.setFixedHeight(32)
        today_btn.setStyleSheet(
            f"QPushButton {{ background: #EEF5FF; color: {BLUE}; border: none; border-radius: 10px; "
            f"padding: 6px 12px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #E2EEFF; }}"
        )
        today_btn.clicked.connect(lambda: self._on_date_selected(QDate.currentDate()))
        footer.addWidget(today_btn)
        footer.addStretch()
        card_lay.addLayout(footer)

        pop_lay.addWidget(card)
        self._style_calendar_nav()
        self._fix_calendar_viewport()

    def _style_calendar_nav(self):
        calendar = self._calendar
        prev_btn = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        month_btn = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
        year_btn = calendar.findChild(QToolButton, "qt_calendar_yearbutton")

        if prev_btn is not None:
            prev_btn.setText("")
            prev_btn.setIcon(qta.icon("mdi6.chevron-left", color=BLUE))
            prev_btn.setIconSize(prev_btn.sizeHint() * 0.55)
        if next_btn is not None:
            next_btn.setText("")
            next_btn.setIcon(qta.icon("mdi6.chevron-right", color=BLUE))
            next_btn.setIconSize(next_btn.sizeHint() * 0.55)
        for btn in [month_btn, year_btn]:
            if btn is not None:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _fix_calendar_viewport(self):
        view = self._calendar.findChild(QWidget, "qt_calendar_calendarview")
        if view is None:
            return
        view.setAutoFillBackground(True)
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        palette.setColor(QPalette.ColorRole.Window, QColor("white"))
        palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_CLR))
        view.setPalette(palette)
        view.setStyleSheet(
            f"background: white; color: {TEXT_CLR}; border: none; "
            f"selection-background-color: {BLUE}; selection-color: white;"
        )

    def _show_popup(self):
        if self._popup is None:
            self._build_popup()
        self._calendar.setSelectedDate(self._date if self._date else QDate.currentDate())
        self._popup.adjustSize()
        screen = self.screen() or __import__('PyQt6.QtWidgets', fromlist=['QApplication']).QApplication.primaryScreen()
        pos = self.mapToGlobal(self.rect().bottomLeft())
        x = pos.x()
        y = pos.y() + 6
        if screen is not None:
            available = screen.availableGeometry()
            popup_w = min(self._popup.width(), max(280, available.width() - 24))
            popup_h = min(self._popup.height(), max(240, available.height() - 24))
            self._popup.resize(popup_w, popup_h)
            x = min(max(available.left() + 12, x), available.right() - popup_w - 12)
            y = min(max(available.top() + 12, y), available.bottom() - popup_h - 12)
        self._popup.move(x, y)
        self._popup.show()

    def _on_date_selected(self, date):
        self.setDate(date)
        self._popup.hide()

    def date(self):
        return self._date

    def setDate(self, date):
        self._date = date
        if self._date and self._date.isValid():
            self._text.setText(self._date.toString("dd  MMM  yyyy"))
            self.dateChanged.emit(self._date)
        else:
            self._date = None
            self._text.setText("")


class SmartDateTimeEdit(QWidget):
    dateTimeChanged = pyqtSignal(QDateTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dt = QDateTime.currentDateTime()
        self.setStyleSheet("background: transparent;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._shell = QFrame()
        self._shell.setObjectName("smartDateTimeShell")
        self._shell.setStyleSheet(f"""
            QFrame#smartDateTimeShell {{
                background: white;
                border: 1.5px solid {BORDER};
                border-radius: 16px;
            }}
            QFrame#smartDateTimeShell:hover {{
                border: 1.5px solid #D8E6F5;
            }}
        """)
        shell_lay = QHBoxLayout(self._shell)
        shell_lay.setContentsMargins(16, 0, 0, 0)
        shell_lay.setSpacing(8)

        self._text = QLabel()
        self._text.setStyleSheet(f"color: {TEXT_CLR}; font-size: 13px; font-weight: 700; background: transparent;")
        shell_lay.addWidget(self._text)

        shell_lay.addStretch()

        self._btn = QPushButton()
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedSize(48, 46)
        self._btn.setIcon(qta.icon("mdi6.clock-edit-outline", color=BLUE))
        self._btn.setIconSize(self._btn.size() * 0.42)
        self._btn.setStyleSheet(
            "QPushButton { background: #F4F8FD; border: none; border-left: 1px solid #E8EEF5; "
            "border-top-right-radius: 16px; border-bottom-right-radius: 16px; }"
            "QPushButton:hover { background: #ECF4FF; }"
        )
        self._btn.clicked.connect(self._show_popup)
        shell_lay.addWidget(self._btn)
        outer.addWidget(self._shell)

        self._popup = None  # created lazily on first open
        self._calendar = None
        self._time_edit = None
        self._refresh_text()

    def _build_popup(self):
        self._popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        pop_lay = QVBoxLayout(self._popup)
        pop_lay.setContentsMargins(0, 8, 0, 0)
        pop_lay.setSpacing(0)

        card = QFrame()
        card.setMinimumSize(320, 400)
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #DDE7F0;
                border-radius: 22px;
            }}
            QCalendarWidget {{
                background: transparent;
                border: none;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: transparent;
                border: none;
                border-bottom: 1px solid #EDF2F7;
                min-height: 48px;
            }}
            QCalendarWidget QToolButton {{
                color: {TEXT_CLR};
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QCalendarWidget QToolButton:hover {{
                background: #EEF5FF;
                color: {BLUE};
            }}
            QCalendarWidget QHeaderView::section {{
                background: transparent;
                color: #8A97A8;
                border: none;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 0 10px 0;
            }}
            QCalendarWidget QTableView {{
                background: white;
                border: none;
                outline: 0;
                selection-background-color: {BLUE};
                selection-color: white;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: {TEXT_CLR};
                background: white;
                font-size: 13px;
                selection-background-color: {BLUE};
                selection-color: white;
                outline: 0;
            }}
        """)
        card.setGraphicsEffect(make_shadow(22, 8, 35))
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        card_lay.setSpacing(8)

        self._calendar = MonthOnlyCalendar()
        self._calendar.setMinimumSize(300, 244)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.setGridVisible(False)
        self._calendar.setSelectedDate(self._dt.date())
        self._calendar.clicked.connect(self._on_date_clicked)
        card_lay.addWidget(self._calendar)

        time_row = QFrame()
        time_row.setStyleSheet("background: #F7FAFE; border: none; border-radius: 14px;")
        time_lay = QHBoxLayout(time_row)
        time_lay.setContentsMargins(12, 10, 12, 10)
        time_lay.setSpacing(10)

        clock = QLabel()
        clock.setPixmap(qta.icon("mdi6.clock-time-four-outline", color=BLUE).pixmap(18, 18))
        time_lay.addWidget(clock)

        time_text = QLabel("Dose Time")
        time_text.setStyleSheet(f"color: {TEXT_CLR}; font-size: 12px; font-weight: 700;")
        time_lay.addWidget(time_text)
        time_lay.addStretch()

        self._time_edit = QTimeEdit(self._dt.time())
        self._time_edit.setDisplayFormat("hh:mm AP")
        self._time_edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self._time_edit.setStyleSheet(
            f"background: white; color: {TEXT_CLR}; border: 1px solid #DCE6F0; border-radius: 10px; "
            "padding: 6px 10px; font-size: 12px; font-weight: 700;"
        )
        self._time_edit.timeChanged.connect(self._on_time_changed)
        time_lay.addWidget(self._time_edit)
        card_lay.addWidget(time_row)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        now_btn = QPushButton("Now")
        now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        now_btn.setFixedHeight(32)
        now_btn.setStyleSheet(
            f"QPushButton {{ background: #EEF5FF; color: {BLUE}; border: none; border-radius: 10px; "
            f"padding: 6px 12px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #E2EEFF; }}"
        )
        now_btn.clicked.connect(self._set_now)
        footer.addWidget(now_btn)
        footer.addStretch()
        card_lay.addLayout(footer)

        pop_lay.addWidget(card)
        self._style_calendar_nav()

    def _style_calendar_nav(self):
        prev_btn = self._calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = self._calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        for btn, icon_name in [(prev_btn, "mdi6.chevron-left"), (next_btn, "mdi6.chevron-right")]:
            if btn is not None:
                btn.setText("")
                btn.setIcon(qta.icon(icon_name, color=BLUE))
                btn.setIconSize(btn.sizeHint() * 0.55)

    def _refresh_text(self):
        self._text.setText(self._dt.toString("dd.MM.yy   hh:mm AP"))

    def _show_popup(self):
        if self._popup is None or self._calendar is None or self._time_edit is None:
            self._build_popup()
        self._calendar.setSelectedDate(self._dt.date())
        self._time_edit.setTime(self._dt.time())
        self._popup.adjustSize()
        screen = self.screen() or __import__('PyQt6.QtWidgets', fromlist=['QApplication']).QApplication.primaryScreen()
        pos = self.mapToGlobal(self.rect().bottomLeft())
        x = pos.x()
        y = pos.y() + 6
        if screen is not None:
            available = screen.availableGeometry()
            popup_w = min(self._popup.width(), max(320, available.width() - 24))
            popup_h = min(self._popup.height(), max(320, available.height() - 24))
            self._popup.resize(popup_w, popup_h)
            x = min(max(available.left() + 12, x), available.right() - popup_w - 12)
            y = min(max(available.top() + 12, y), available.bottom() - popup_h - 12)
        self._popup.move(x, y)
        self._popup.show()

    def _on_date_clicked(self, date):
        self._dt.setDate(date)
        self._refresh_text()

    def _on_time_changed(self, time):
        self._dt.setTime(time)
        self._refresh_text()

    def _set_now(self):
        self.setDateTime(QDateTime.currentDateTime())

    def dateTime(self):
        return self._dt

    def setDateTime(self, dt):
        self._dt = dt
        if self._calendar is not None:
            self._calendar.setSelectedDate(dt.date())
        if self._time_edit is not None:
            self._time_edit.setTime(dt.time())
        self._refresh_text()
        self.dateTimeChanged.emit(self._dt)


# ─────────────────────────────────────────
# Toast message
# ─────────────────────────────────────────
class ToastMessage(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toastMessage")
        self.setVisible(False)
        self.setStyleSheet("""
            QFrame#toastMessage {
                background: #BFF1C7;
                border: none;
                border-radius: 18px;
            }
        """)
        self.setGraphicsEffect(make_shadow(18, 6, 28))

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(12)

        self.icon = QLabel()
        self.icon.setFixedSize(34, 34)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(
            "background: white; border-radius: 17px; color: #179B48; font-size: 18px; font-weight: bold;"
        )
        row.addWidget(self.icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel()
        self.title.setStyleSheet("color: #123524; font-size: 14px; font-weight: 700;")
        self.body = QLabel()
        self.body.setStyleSheet("color: #335847; font-size: 11px;")
        self.body.setWordWrap(True)
        text_col.addWidget(self.title)
        text_col.addWidget(self.body)
        row.addLayout(text_col, 1)

        self.close_btn = QPushButton()
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setIcon(qta.icon("mdi6.close", color="#4A6A58"))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.close_btn.clicked.connect(self.hide)
        row.addWidget(self.close_btn)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, title, body, duration_ms=2600, tone="success"):
        if tone == "warning":
            self.setStyleSheet("""
                QFrame#toastMessage {
                    background: #FDE2E2;
                    border: none;
                    border-radius: 18px;
                }
            """)
            self.icon.setStyleSheet(
                "background: white; border-radius: 17px; color: #DC2626; font-size: 18px; font-weight: bold;"
            )
            self.icon.setPixmap(qta.icon("mdi6.alert-circle", color="#DC2626").pixmap(18, 18))
            self.title.setStyleSheet("color: #7F1D1D; font-size: 14px; font-weight: 700;")
            self.body.setStyleSheet("color: #991B1B; font-size: 11px;")
            self.close_btn.setIcon(qta.icon("mdi6.close", color="#991B1B"))
        else:
            self.setStyleSheet("""
                QFrame#toastMessage {
                    background: #BFF1C7;
                    border: none;
                    border-radius: 18px;
                }
            """)
            self.icon.setStyleSheet(
                "background: white; border-radius: 17px; color: #179B48; font-size: 18px; font-weight: bold;"
            )
            self.icon.setPixmap(qta.icon("mdi6.check", color="#179B48").pixmap(18, 18))
            self.title.setStyleSheet("color: #123524; font-size: 14px; font-weight: 700;")
            self.body.setStyleSheet("color: #335847; font-size: 11px;")
            self.close_btn.setIcon(qta.icon("mdi6.close", color="#4A6A58"))
        self.title.setText(title)
        self.body.setText(body)
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)
