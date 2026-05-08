"""
storage/csv_logger.py
=====================
Zapisywanie pomiarów do pliku CSV.

Kluczowa rzecz: po każdym wpisie robimy FLUSH na dysku. Inaczej przy
crashu / wyłączeniu zasilania można stracić ostatnie kilkadziesiąt
pomiarów które siedziały w buforze systemowym.

Format pliku:
    timestamp;mass;unit;status;raw_response
    2026-04-30 14:22:10;123.456;g;STABLE;SI       123.456 g  ...
"""

import csv
import os
from datetime import datetime
from typing import Optional

from config import CSV_SEPARATOR, CSV_ENCODING, TIMESTAMP_FORMAT


class CsvLogger:
    """Logger CSV. Otwiera plik w trybie append, dopisuje wiersze, flushuje.

    Trzymanie otwartego uchwytu (zamiast otwierania pliku przy każdym wpisie)
    jest szybsze i pewniejsze — nie ma problemu z 'plik zajęty przez Excel'
    który się pojawia przy ciągłym otwieraniu/zamykaniu na Windowsie.

    Użycie:
        logger = CsvLogger("log_wagi.csv")
        logger.open()
        logger.write_row(timestamp, mass, unit, status, raw)
        logger.close()
    """

    # Nagłówki kolumn — w jednym miejscu, łatwo zmienić.
    HEADERS = ["timestamp", "mass", "unit", "status", "raw_response"]

    def __init__(self, file_path: str):
        """
        Argumenty:
            file_path: ścieżka do pliku CSV (może nie istnieć — wtedy go utworzymy).
        """
        self.file_path = file_path
        self._fh = None        # uchwyt pliku
        self._writer = None    # csv.writer

    def open(self) -> None:
        """Otwiera plik do dopisywania. Jeśli plik nie istniał — dopisuje nagłówek.

        Jeśli plik istniał wcześniej (np. wznawiamy rejestrację),
        dopisujemy do niego BEZ nagłówka. Żeby Excel nie miał drugiego
        nagłówka w środku danych.
        """
        # Czy plik już istnieje i ma jakąś zawartość?
        # Sprawdzamy ROZMIAR a nie samo istnienie, bo czasem zostają
        # puste pliki po nieudanym poprzednim uruchomieniu.
        write_header = not (os.path.exists(self.file_path)
                            and os.path.getsize(self.file_path) > 0)

        # newline='' jest WAŻNE dla modułu csv — bez tego na Windowsie
        # robi się podwójne końce linii (\r\r\n) i Excel pluje krzakami.
        self._fh = open(
            self.file_path,
            mode="a",
            newline="",
            encoding=CSV_ENCODING,
        )
        self._writer = csv.writer(self._fh, delimiter=CSV_SEPARATOR)

        if write_header:
            self._writer.writerow(self.HEADERS)
            self._fh.flush()

    def write_row(
        self,
        timestamp: datetime,
        mass: Optional[float],
        unit: str,
        status: str,
        raw_response: str,
    ) -> None:
        """Dopisuje jeden wiersz pomiaru.

        Argumenty:
            timestamp:    moment pomiaru (datetime), formatowany wg TIMESTAMP_FORMAT
            mass:         masa (float) lub None gdy parser zwrócił błąd
            unit:         jednostka (string)
            status:       STABLE / UNSTABLE / OVER_RANGE / ERROR
            raw_response: surowa odpowiedź z wagi do logu / debugu

        Po zapisie WYMUSZA flush — żeby przy crashu nie stracić danych.
        """
        if self._writer is None or self._fh is None:
            raise RuntimeError("CsvLogger nie został otwarty — wywołaj open() najpierw.")

        # Formatujemy masę. None -> pusty string (nie 'None' tekstem).
        # Float bez wymuszania notacji naukowej — Excel czyta lepiej.
        mass_str = "" if mass is None else f"{mass:.6f}".rstrip("0").rstrip(".")
        # przykład: 18.300000 -> "18.3", 1.234500 -> "1.2345"

        # Surową odpowiedź zapisujemy z usuniętymi CR/LF, żeby nie łamała wiersza.
        # Spacje w środku ZOSTAJĄ — to sygnatura formatu RADWAG.
        raw_clean = raw_response.replace("\r", "").replace("\n", " ").strip()

        self._writer.writerow([
            timestamp.strftime(TIMESTAMP_FORMAT),
            mass_str,
            unit,
            status,
            raw_clean,
        ])

        # WAŻNE: flush + fsync. flush() spycha z bufora Pythona do bufora OS.
        # fsync zmuszałby OS do zapisu na dysk fizyczny — to drogie, robimy
        # tylko flush() bo i tak chronimy się przed crashem aplikacji,
        # a nie przed zanikiem zasilania (na to jest UPS).
        self._fh.flush()

    def close(self) -> None:
        """Zamyka plik. Bezpieczne wielokrotne wywołanie."""
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
            self._writer = None

    # Context manager — żeby można było 'with CsvLogger(...) as log:'
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
