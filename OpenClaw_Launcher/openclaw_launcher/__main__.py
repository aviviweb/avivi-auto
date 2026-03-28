import sys

from PyQt6.QtWidgets import QApplication

from openclaw_launcher.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenClaw Launcher")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
