"""
main.py
=======
Punkt wejścia aplikacji.

Uruchomienie:
    python main.py

Tyle wystarczy. Reszta dzieje się w gui/main_window.py.
"""

import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    """Tworzy QApplication, pokazuje okno, oddaje sterowanie pętli zdarzeń Qt."""
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # exec() blokuje aż użytkownik zamknie okno. Zwraca kod wyjścia.
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
