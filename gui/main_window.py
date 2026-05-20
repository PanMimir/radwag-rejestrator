"""
gui/main_window.py
==================
Główne okno aplikacji.

Layout (w przybliżeniu):

    +----------------------------------------------------------+
    | Port: [COM3 v] [Odśwież] [Szukaj wagi]  Interwał[s]:[1.0]|
    | Plik CSV: [...]  [Wybierz...]                            |
    | [Start rejestracji]  [Stop rejestracji]                  |
    +----------------------------------------------------------+
    | Aktualna masa: 123.4567 g                                |
    | Status: STABLE     Ostatni odczyt: 2026-04-30 14:22:10   |
    +----------------------------------------------------------+
    | Tabela ostatnich 20 pomiarów                              |
    +----------------------------------------------------------+
    | Logi / debug komunikacji                                  |
    +----------------------------------------------------------+
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QGridLayout, QTableWidget, QTableWidgetItem, QTextEdit, QMessageBox,
    QFileDialog, QGroupBox, QDoubleSpinBox, QComboBox, QLineEdit,
    QMenuBar,
)

from gui.worker import WeighingWorker
from gui.scan_worker import ScanWorker
from communication.radwag_client import list_serial_ports
from storage.excel_logger import ExcelLogger
from parser.radwag_parser import MeasurementResult
from config import (
    DEFAULT_INTERVAL_S, EXCEL_DEFAULT_FILENAME, TIMESTAMP_FORMAT,
    WINDOW_TITLE, TABLE_MAX_ROWS, LOG_MAX_LINES,
)


# Kolory tła wiersza w tabeli wg statusu pomiaru.
# Wizualna pomoc: od razu widać które pomiary są niestabilne lub błędne.
_STATUS_COLORS = {
    "STABLE":     QColor(220, 255, 220),  # delikatna zieleń
    "UNSTABLE":   QColor(255, 250, 200),  # delikatny żółty
    "OVER_RANGE": QColor(255, 220, 220),  # delikatna czerwień
    "ERROR":      QColor(255, 200, 200),  # mocniejsza czerwień
}


class MainWindow(QWidget):
    """Główne okno aplikacji rejestratora."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(900, 700)

        # Stan aplikacji.
        self._worker = None       # WeighingWorker, None gdy nie rejestrujemy
        self._scan_worker = None  # ScanWorker, None gdy nie skanujemy
        self._excel_logger = None # ExcelLogger, None gdy nie rejestrujemy
        self._excel_path = EXCEL_DEFAULT_FILENAME

        # Budujemy interfejs.
        self._build_ui()

        # Na start wypełniamy listę portów.
        self._refresh_ports()

    # ===================================================================
    # BUDOWANIE INTERFEJSU
    # ===================================================================

    def _build_ui(self) -> None:
        """Składa cały layout okna."""
        root = QVBoxLayout(self)

        menu_bar = QMenuBar(self)
        help_menu = menu_bar.addMenu("Pomoc")
        about_action = help_menu.addAction("O programie")
        about_action.triggered.connect(self._show_about)
        root.setMenuBar(menu_bar)

        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_status_group())
        root.addWidget(self._build_table_group(), stretch=2)
        root.addWidget(self._build_log_group(), stretch=1)

    def _build_connection_group(self) -> QGroupBox:
        """Pasek z polami port/interwał i przyciskami Start/Stop."""
        box = QGroupBox("Połączenie i rejestracja")
        layout = QGridLayout(box)

        # Port szeregowy — combo z dostępnymi portami.
        layout.addWidget(QLabel("Port wagi:"), 0, 0)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        self.port_combo.setEditable(True)  # pozwala wpisać ręcznie jeśli auto-skan nie działa
        layout.addWidget(self.port_combo, 0, 1)

        # Przycisk odświeżania listy portów.
        self.refresh_btn = QPushButton("Odśwież listę")
        self.refresh_btn.setToolTip("Ponownie sprawdź jakie porty COM są dostępne w systemie")
        self.refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(self.refresh_btn, 0, 2)

        # Przycisk auto-skanu.
        self.scan_btn = QPushButton("🔍 Szukaj wagi")
        self.scan_btn.setToolTip("Wysyła komendę SI do każdego portu COM i sprawdza czy odpowiada wagą RADWAG")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        layout.addWidget(self.scan_btn, 0, 3)

        # Interwał.
        layout.addWidget(QLabel("Interwał [s]:"), 0, 4)
        self.interval_input = QDoubleSpinBox()
        self.interval_input.setRange(0.1, 3600.0)
        self.interval_input.setSingleStep(0.5)
        self.interval_input.setDecimals(2)
        self.interval_input.setValue(DEFAULT_INTERVAL_S)
        self.interval_input.setMaximumWidth(100)
        layout.addWidget(self.interval_input, 0, 5)

        # Plik Excel — edytowalne pole ze ścieżką + przycisk obok.
        layout.addWidget(QLabel("Plik Excel:"), 1, 0)
        self.excel_path_input = QLineEdit(self._excel_path)
        self.excel_path_input.setPlaceholderText("Ścieżka do pliku .xlsx...")
        layout.addWidget(self.excel_path_input, 1, 1, 1, 3)
        self.choose_excel_btn = QPushButton("📂 Wybierz plik Excel")
        self.choose_excel_btn.setToolTip("Kliknij, aby wybrać gdzie zapisywać pomiary")
        self.choose_excel_btn.clicked.connect(self._on_choose_excel)
        layout.addWidget(self.choose_excel_btn, 1, 4, 1, 2)

        # Przyciski Start / Stop.
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start rejestracji")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("⏹ Stop rejestracji")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row, 2, 0, 1, 6)

        return box

    def _build_status_group(self) -> QGroupBox:
        """Panel ze stanem aktualnym: masa, status, czas."""
        box = QGroupBox("Aktualny pomiar")
        layout = QGridLayout(box)

        # Duża czcionka dla masy — żeby z 3 metrów było widać.
        self.mass_label = QLabel("--- ---")
        font = self.mass_label.font()
        font.setPointSize(28)
        font.setBold(True)
        self.mass_label.setFont(font)
        self.mass_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mass_label, 0, 0, 1, 4)

        layout.addWidget(QLabel("Status:"), 1, 0)
        self.status_label = QLabel("---")
        layout.addWidget(self.status_label, 1, 1)

        layout.addWidget(QLabel("Ostatni odczyt:"), 1, 2)
        self.timestamp_label = QLabel("---")
        layout.addWidget(self.timestamp_label, 1, 3)

        return box

    def _build_table_group(self) -> QGroupBox:
        """Tabela ostatnich 20 pomiarów."""
        box = QGroupBox(f"Ostatnie {TABLE_MAX_ROWS} pomiarów")
        layout = QVBoxLayout(box)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Czas", "Masa", "Jednostka", "Status", "Surowa odpowiedź"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        return box

    def _build_log_group(self) -> QGroupBox:
        """Panel logów / debug komunikacji."""
        box = QGroupBox("Logi")
        layout = QVBoxLayout(box)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        layout.addWidget(self.log_view)

        return box

    # ===================================================================
    # OBSŁUGA PORTÓW COM
    # ===================================================================

    def _refresh_ports(self) -> None:
        """Odświeża listę portów COM w combo boxie.

        Zachowuje aktualnie wybrany port jeśli jeszcze istnieje w systemie.
        """
        # Zapamiętujemy bieżący wybór, żeby nie zniknął przy odświeżeniu.
        current = self.port_combo.currentText().strip()

        self.port_combo.clear()

        ports = list_serial_ports()
        if not ports:
            self.port_combo.addItem("(brak dostępnych portów COM)")
            self._append_log("Nie znaleziono żadnych portów COM. Podłącz wagę przez USB.")
            return

        for port_name, description in ports:
            # Pokazujemy "COM3 — USB Serial Device" w combo.
            label = f"{port_name} — {description}" if description else port_name
            # Drugi argument (userData) trzymamy nazwę portu — łatwiej ją potem wyciągnąć.
            self.port_combo.addItem(label, userData=port_name)

        # Próbujemy przywrócić poprzedni wybór.
        if current:
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == current or current in self.port_combo.itemText(i):
                    self.port_combo.setCurrentIndex(i)
                    break

        self._append_log(f"Znaleziono {len(ports)} port(ów) COM.")

    def _get_selected_port(self) -> str:
        """Zwraca nazwę wybranego portu (np. "COM3") z comboboxa.

        Combo zachowuje się dwojako:
        - jeśli użytkownik wybrał z listy → mamy w userData nazwę portu
        - jeśli wpisał ręcznie (tryb editable) → mamy zwykły tekst do wyłuskania

        Funkcja zwraca samą nazwę portu, bez opisu.
        """
        # Najpierw próbujemy z userData.
        idx = self.port_combo.currentIndex()
        if idx >= 0:
            data = self.port_combo.itemData(idx)
            if data:
                return str(data)

        # Fallback: użytkownik wpisał ręcznie. Odcinamy " — opis" jeśli jest.
        text = self.port_combo.currentText().strip()
        if " — " in text:
            text = text.split(" — ")[0]
        return text

    def _on_scan_clicked(self) -> None:
        """Klik 'Szukaj wagi' — uruchamia auto-skan w osobnym wątku."""
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return  # już skanujemy, nie odpalamy drugiego

        # Blokujemy GUI na czas skanu, żeby nie odpalić rejestracji w trakcie.
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ Skanuję...")
        self.refresh_btn.setEnabled(False)
        self.start_btn.setEnabled(False)

        self._append_log("=== AUTO-SKAN: szukam wagi RADWAG na portach COM ===")

        self._scan_worker = ScanWorker()
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished_with_result.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_progress(self, port: str, status: str) -> None:
        """Postęp skanu — wpis do logów."""
        self._append_log(f"  [skan] {port}: {status}")

    def _on_scan_finished(self, found_port: str, description: str) -> None:
        """Skan zakończony. Albo znalazł port, albo nie."""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 Szukaj wagi")
        self.refresh_btn.setEnabled(True)
        self.start_btn.setEnabled(True)

        if found_port:
            self._append_log(f"=== SUKCES: znaleziono wagę na {found_port} ({description}) ===")
            # Ustawiamy znaleziony port jako wybrany w combo.
            self._refresh_ports()
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == found_port:
                    self.port_combo.setCurrentIndex(i)
                    break
            QMessageBox.information(
                self,
                "Waga znaleziona",
                f"Wagę RADWAG znaleziono na porcie:\n\n  {found_port}\n  ({description})\n\n"
                f"Możesz teraz kliknąć 'Start rejestracji'.",
            )
        else:
            self._append_log("=== Nie znaleziono wagi na żadnym porcie ===")
            QMessageBox.warning(
                self,
                "Nie znaleziono wagi",
                "Auto-skan nie znalazł wagi RADWAG na żadnym porcie COM.\n\n"
                "Sprawdź:\n"
                "• czy waga jest włączona\n"
                "• czy kabel USB jest podłączony do komputera\n"
                "• czy w menu wagi: Urządzenia → Komputer → Port = USB\n"
                "• czy w Menedżerze urządzeń Windows widzisz port COM dla wagi\n\n"
                "Możesz też wpisać port ręcznie w polu wyboru.",
            )

        self._scan_worker = None

    # ===================================================================
    # OBSŁUGA ZDARZEŃ GUI - REJESTRACJA
    # ===================================================================

    def _on_choose_excel(self) -> None:
        """Pozwala wybrać plik Excel, gdzie pójdą pomiary."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Wybierz plik Excel do zapisu pomiarów",
            self._excel_path,
            "Excel (*.xlsx);;Wszystkie pliki (*)",
        )
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self._excel_path = path
            self.excel_path_input.setText(path)
            self._append_log(f"Plik Excel ustawiony na: {path}")

    def _on_start(self) -> None:
        """Klik przycisku Start: walidacja, otwarcie pliku Excel, start wątku."""
        # --- Walidacja danych z formularza ---
        port = self._get_selected_port()
        if not port or port.startswith("(brak"):
            self._show_error("Wybierz port COM. Jeśli lista jest pusta, podłącz wagę przez USB i kliknij 'Odśwież listę'.")
            return

        interval = self.interval_input.value()
        if interval <= 0:
            self._show_error("Interwał musi być większy od zera.")
            return

        # --- Potwierdzenie pliku docelowego ---
        self._excel_path = self.excel_path_input.text().strip()
        answer = QMessageBox.question(
            self,
            "Potwierdzenie pliku docelowego",
            f"Pomiary zostaną zapisane do:\n\n  {self._excel_path}\n\n"
            f"Czy plik docelowy jest ustawiony poprawnie?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        # --- Otwieramy plik Excel ---
        try:
            self._excel_logger = ExcelLogger(self._excel_path)
            self._excel_logger.open()
            self._append_log(f"Plik Excel otwarty: {self._excel_path}")
        except OSError as e:
            self._show_error(f"Nie mogę otworzyć pliku Excel: {e}")
            self._excel_logger = None
            return

        # --- Tworzymy i startujemy wątek ---
        self._worker = WeighingWorker(port, interval)
        self._worker.measurement_ready.connect(self._on_measurement)
        self._worker.connection_lost.connect(self._on_connection_lost)
        self._worker.log_message.connect(self._append_log)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        # Blokujemy edycję pól podczas rejestracji.
        self._set_inputs_enabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_stop(self) -> None:
        """Klik Stop: prosi wątek o zakończenie."""
        if self._worker is not None:
            self._append_log("Zatrzymywanie rejestracji...")
            self._worker.stop()
            if not self._worker.wait(3000):
                self._append_log("UWAGA: wątek nie zakończył się w 3s, wymuszam terminate.")
                self._worker.terminate()
                self._worker.wait()

    def _on_worker_finished(self) -> None:
        """Wątek się zakończył (sam albo na nasze życzenie). Sprzątamy."""
        if self._excel_logger is not None:
            self._excel_logger.close()
            self._excel_logger = None
            self._append_log("Plik Excel zamknięty.")

        self._worker = None

        self._set_inputs_enabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Włącza/wyłącza edycję pól konfiguracyjnych."""
        self.port_combo.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.scan_btn.setEnabled(enabled)
        self.interval_input.setEnabled(enabled)
        self.choose_excel_btn.setEnabled(enabled)

    # ===================================================================
    # SLOTY DLA SYGNAŁÓW Z WĄTKU REJESTRACJI
    # ===================================================================

    def _on_measurement(self, result: MeasurementResult, timestamp: datetime) -> None:
        """Wywoływane gdy wątek zwróci nowy pomiar."""
        # 1. Panel statusu.
        if result.mass is not None:
            self.mass_label.setText(f"{result.mass:.4f} {result.unit}")
        else:
            self.mass_label.setText("--- ---")
        self.status_label.setText(result.status)
        self.timestamp_label.setText(timestamp.strftime(TIMESTAMP_FORMAT))

        # 2. Tabela.
        self._add_row_to_table(result, timestamp)

        # 3. Excel.
        if self._excel_logger is not None:
            try:
                self._excel_logger.write_row(timestamp, result.mass, result.unit, result.status)
            except OSError as e:
                self._append_log(f"BŁĄD zapisu Excel: {e}")

    def _on_connection_lost(self, reason: str) -> None:
        """Wątek zgłosił że połączenie padło. Zatrzymujemy + alert."""
        self._append_log(f"!!! POŁĄCZENIE UTRACONE: {reason}")

        QMessageBox.warning(
            self,
            "Utracono połączenie z wagą",
            f"Rejestracja została zatrzymana.\n\nPowód:\n{reason}",
        )
        # Sprzątanie zrobi się samo w _on_worker_finished gdy wątek wyjdzie z run().

    def _add_row_to_table(self, result: MeasurementResult, timestamp: datetime) -> None:
        """Dodaje wiersz do tabeli historii i obcina najstarsze."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        mass_text = "" if result.mass is None else f"{result.mass:.4f}"
        cells = [
            timestamp.strftime(TIMESTAMP_FORMAT),
            mass_text,
            result.unit,
            result.status,
            result.raw_response.replace("\r", "").replace("\n", " "),
        ]

        bg = _STATUS_COLORS.get(result.status)

        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if bg is not None:
                item.setBackground(bg)
            item.setForeground(QColor(0, 0, 0))
            self.table.setItem(row, col, item)

        while self.table.rowCount() > TABLE_MAX_ROWS:
            self.table.removeRow(0)

        self.table.scrollToBottom()

    def _append_log(self, message: str) -> None:
        """Dodaje wpis do panelu logów z timestampem."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {message}")

        doc = self.log_view.document()
        if doc.blockCount() > LOG_MAX_LINES:
            cursor = self.log_view.textCursor()
            cursor.movePosition(cursor.Start)
            for _ in range(doc.blockCount() - LOG_MAX_LINES):
                cursor.select(cursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

    def _show_error(self, message: str) -> None:
        """Wyświetla popup z błędem."""
        QMessageBox.critical(self, "Błąd", message)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "O programie",
            "<b>Radwag Rejestrator</b><br>"
            "Wersja 1.0.1<br><br>"
            "Producent: <a href='https://sincore.io'>sincore.io</a><br>"
            "Kontakt: <a href='mailto:contact@sincore.io'>contact@sincore.io</a>",
        )

    # ===================================================================
    # ZAMYKANIE OKNA
    # ===================================================================

    def closeEvent(self, event) -> None:
        """Gdy użytkownik klika X w rogu okna."""
        if self._worker is not None and self._worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Rejestracja w toku",
                "Trwa rejestracja pomiarów. Zamknąć aplikację mimo to?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._on_stop()

        # Anulujemy też skan jeśli trwa.
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._scan_worker.terminate()
            self._scan_worker.wait()

        event.accept()
