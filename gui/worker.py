"""
gui/worker.py
=============
Wątek roboczy (QThread) który robi cykliczne odpytywanie wagi.

Dlaczego osobny wątek a nie QTimer?
-----------------------------------
QTimer jest super do prostych spraw, ale problem jest taki:
- gdy wysyłamy zapytanie po porcie i czekamy na odpowiedź (do 2s timeout),
  to przy małych interwałach (np. 0.5s) może się zdarzyć że timer odpali
  drugi cykl zanim pierwszy się skończy.
- Każda operacja na porcie BLOKUJE wątek na czas oczekiwania na dane.
- W głównym wątku Qt ten blok = zamrożenie GUI (kursor klepsydry).

Osobny QThread odcina to wszystko: GUI bryka żwawo, a wątek roboczy
spokojnie sobie czeka na wagę nawet 2 sekundy.

Komunikacja worker → GUI: przez sygnały Qt (thread-safe).
"""

import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from communication.radwag_client import RadwagClient, RadwagConnectionError
from parser.radwag_parser import RadwagParser
from config import (
    RADWAG_WEIGHT_COMMAND, SERIAL_TIMEOUT_S,
    DEFAULT_BAUDRATE, DEFAULT_BYTESIZE, DEFAULT_STOPBITS, DEFAULT_PARITY,
)


class WeighingWorker(QThread):
    """Wątek roboczy: cyklicznie pyta wagę i emituje wyniki przez sygnały.

    Sygnały:
        measurement_ready(result, timestamp) - nowy poprawny / błędny pomiar
        connection_lost(reason)              - połączenie padło, GUI ma zatrzymać rejestrację
        log_message(text)                    - tekst do wyświetlenia w panelu logów
    """

    # Definicje sygnałów. PySide6 wymaga żeby były na poziomie klasy.
    measurement_ready = Signal(object, object)  # (MeasurementResult, datetime)
    connection_lost = Signal(str)                # (powód jako string)
    log_message = Signal(str)                    # (tekst loga)

    def __init__(
        self,
        port: str,
        interval_s: float,
        baudrate: int = DEFAULT_BAUDRATE,
        bytesize: int = DEFAULT_BYTESIZE,
        stopbits: int = DEFAULT_STOPBITS,
        parity: str = DEFAULT_PARITY,
        parent=None,
    ):
        """
        Argumenty:
            port:       nazwa portu szeregowego (np. "COM3")
            interval_s: co ile sekund pytać (float, np. 0.5, 1, 60)
            baudrate:   prędkość transmisji (zwykle 9600)
            bytesize:   bity danych (zwykle 8)
            stopbits:   bity stopu (1)
            parity:     parzystość ("N")
            parent:     standardowy parent Qt (zwykle None)
        """
        super().__init__(parent)
        self.port = port
        self.interval_s = interval_s

        # Flaga zatrzymania. Ustawiana z GUI przez stop().
        # Sprawdzana w pętli głównej wątku — gdy True, wątek się kończy.
        self._stop_requested = False

        # Klient portu szeregowego i parser — tworzone tu, używane w pętli run().
        self._client = RadwagClient(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            timeout=SERIAL_TIMEOUT_S,
        )
        self._parser = RadwagParser()

    def stop(self) -> None:
        """Prosi wątek o zakończenie. Wątek wyjdzie z pętli przy najbliższej okazji.

        Nie zabija wątku siłą (terminate) — to jest nieczyste. Daje mu
        szansę zamknąć port porządnie.
        """
        self._stop_requested = True

    def run(self) -> None:
        """Główna pętla wątku.

        1. Otwiera port szeregowy.
        2. W pętli: wyślij komendę -> odbierz -> sparsuj -> emituj sygnał.
        3. Przy każdym błędzie komunikacji: emituje connection_lost i kończy wątek.
        4. Po stop() — czysto zamyka port i wychodzi.
        """
        # Krok 1: połączenie. Jeśli się nie uda, od razu zgłaszamy do GUI.
        try:
            self.log_message.emit(f"Otwieranie portu {self.port}...")
            self._client.connect()
            self.log_message.emit("Port otwarty. Start rejestracji.")
        except RadwagConnectionError as e:
            self.connection_lost.emit(str(e))
            return

        # Krok 2: pętla pomiarów.
        # Mierzymy czas startu cyklu, żeby interwał był rzeczywisty
        # (nie 'interwał + czas pomiaru', tylko trzymający rytm).
        try:
            while not self._stop_requested:
                cycle_start = time.monotonic()

                # --- Jeden pomiar ---
                try:
                    raw = self._client.send_and_receive(RADWAG_WEIGHT_COMMAND)
                    timestamp = datetime.now()  # czas LOKALNY komputera
                    result = self._parser.parse(raw)
                    self.measurement_ready.emit(result, timestamp)
                except RadwagConnectionError as e:
                    # Decyzja użytkownika: przy rozłączeniu STOP + alert.
                    # Nie próbujemy się sami reconnectować.
                    self.connection_lost.emit(str(e))
                    return

                # --- Czekamy do następnego cyklu ---
                # Liczymy ile zostało do końca interwału (uwzględniając czas
                # spędzony na samym pomiarze).
                elapsed = time.monotonic() - cycle_start
                remaining = self.interval_s - elapsed

                if remaining > 0:
                    # Drobny trick: dzielimy sleep na małe kawałki (0.05s),
                    # żeby szybko reagować na stop_requested. Inaczej przy
                    # interwale 60s i kliknięciu STOP użytkownik czekałby
                    # nawet minutę aż wątek się zorientuje.
                    sleep_chunks = int(remaining / 0.05) + 1
                    chunk_size = remaining / sleep_chunks
                    for _ in range(sleep_chunks):
                        if self._stop_requested:
                            break
                        time.sleep(chunk_size)
                # Jeśli remaining <= 0, znaczy że pomiar trwał dłużej niż
                # interwał (powolne USB?). Nie czekamy w ogóle, lecimy z kolejnym.
        finally:
            # ZAWSZE zamykaj port przy wyjściu — niezależnie od tego
            # czy to graceful stop czy błąd.
            self._client.close()
            self.log_message.emit("Wątek rejestracji zakończony, port zamknięty.")
