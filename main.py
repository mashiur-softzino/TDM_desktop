"""
TDM Report — Therapeutic Drug Monitoring Software
Entry point
"""

import os
import sys
import faulthandler
faulthandler.enable()
os.environ.setdefault('QT_MAC_WANTS_LAYER', '1')

from PyQt6.QtWidgets import QApplication
from tdm_report import TDMMainWindow, STYLE


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    window = TDMMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
