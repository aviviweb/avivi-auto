from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class PollWorker(QThread):
    """Runs periodic work without blocking the GUI thread."""

    tick = pyqtSignal()

    def __init__(self, interval_sec: int = 45, parent=None) -> None:
        super().__init__(parent)
        self._interval_sec = max(10, interval_sec)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            self.tick.emit()
            for _ in range(self._interval_sec):
                if self._stop:
                    break
                self.msleep(1000)
