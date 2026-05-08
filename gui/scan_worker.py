"""
gui/scan_worker.py
==================
Wątek roboczy do auto-skanu portów COM w poszukiwaniu wagi RADWAG.

Skan może trwać 2-10 sekund (zależnie od liczby portów w systemie),
więc musi działać w osobnym wątku — inaczej GUI by zamarzło.
"""

from PySide6.QtCore import QThread, Signal

from communication.radwag_client import scan_for_radwag
from config import DEFAULT_BAUDRATE, SCAN_TIMEOUT_S


class ScanWorker(QThread):
    """Wątek skanujący porty COM w poszukiwaniu wagi.

    Sygnały:
        progress(port_name, status_text)  - postęp dla każdego sprawdzanego portu
        finished_with_result(port_or_empty, description) - wynik:
            jeśli znaleziono → ("COM3", "USB Serial Device")
            jeśli nie       → ("", "")
    """

    progress = Signal(str, str)
    finished_with_result = Signal(str, str)

    def run(self) -> None:
        """Wykonuje skan i emituje wynik."""
        # Callback do raportowania postępu — wywoływany z wewnątrz scan_for_radwag.
        def progress_cb(port: str, status: str) -> None:
            self.progress.emit(port, status)

        result = scan_for_radwag(
            baudrate=DEFAULT_BAUDRATE,
            timeout=SCAN_TIMEOUT_S,
            progress_callback=progress_cb,
        )

        if result is None:
            self.finished_with_result.emit("", "")
        else:
            port_name, description = result
            self.finished_with_result.emit(port_name, description)
