from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is missing. Run: pip install -r requirements.txt", file=sys.stderr)
        return 2

    from .ui import MainWindow, STYLE

    QCoreApplication.setOrganizationName("PetShelf")
    QCoreApplication.setApplicationName("PetShelf")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
