"""PyInstaller entry point: Avivi Client (PyQt6)."""
from __future__ import annotations

import os
import sys


def _chdir_to_bundle() -> None:
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))


def main() -> None:
    _chdir_to_bundle()
    from PyQt6.QtWidgets import QApplication

    from avivi_client.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Avivi Client")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
