from __future__ import annotations

import sys
from pathlib import Path


def _asset_path(name: str) -> Path:
    """Resolve an app asset both from source and a PyInstaller bundle."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / "assets" / name


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
    app.setWindowIcon(QIcon(str(_asset_path("petshelf.ico"))))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
