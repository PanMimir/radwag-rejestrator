"""
config.py
=========
Centralne miejsce na wszystkie stałe i wartości domyślne aplikacji.
Jeśli coś trzeba zmienić (komenda, port, format daty) — robimy to TUTAJ,
żeby nie szukać po całym projekcie.
"""

# =====================================================================
# KOMUNIKACJA Z WAGĄ (USB / RS232)
# =====================================================================
#
# Waga RADWAG WLC X2 udostępnia komunikację jako wirtualny port szeregowy
# (Virtual COM Port). Niezależnie od tego czy łączymy się przez fizyczne
# RS232 (DB9) czy przez USB-B, w systemie pojawia się port typu COM (Windows)
# albo /dev/ttyUSB* / /dev/ttyACM* (Linux).
#
# Z punktu widzenia kodu — zachowuje się identycznie. Używamy biblioteki
# pyserial.

# Domyślne parametry portu szeregowego.
# WARTOŚCI ODCZYTANE Z MENU WAGI (Komunikacja → COM 1):
#   Prędkość (baud):     9600
#   Bity danych:         8
#   Bity stopu:          1
#   Parzystość:          Brak (none)
#
# Dla USB w wadze RADWAG te ustawienia są zwykle "wirtualne" — tzn.
# urządzenie ignoruje baud rate i tak — ale i tak je ustawiamy, żeby
# pyserial nie marudził i żeby kod działał też na fizycznym RS232.
DEFAULT_BAUDRATE = 9600
DEFAULT_BYTESIZE = 8
DEFAULT_STOPBITS = 1
DEFAULT_PARITY = "N"   # N = none, E = even, O = odd

# Domyślny port szeregowy (na wypadek gdy auto-skan nic nie znajdzie
# i użytkownik chce wpisać ręcznie).
# Windows:  "COM3"
# Linux:    "/dev/ttyUSB0" lub "/dev/ttyACM0"
DEFAULT_PORT = "COM3"

# Co ile sekund pytać wagę (start).
DEFAULT_INTERVAL_S = 1.0

# Timeout odbioru odpowiedzi z wagi w sekundach.
# Mała waga + lokalne USB = odpowiada w milisekundach. 2s to luz.
SERIAL_TIMEOUT_S = 2.0

# Komendy protokołu znakowego RADWAG.
# Format: ASCII + CR + LF (dwa bajty końca linii).
#
# Najważniejsze komendy (pełna lista w instrukcji RADWAG, sekcja "Protokół komunikacyjny"):
#   S    - pomiar STABILNY (waga czeka aż będzie stabilna i dopiero odpowiada)
#   SI   - pomiar NATYCHMIASTOWY (cokolwiek aktualnie pokazuje, stabilne czy nie)
#   SU   - pomiar stabilny w jednostce aktualnej
#   SIA  - pomiar natychmiastowy w jednostce aktualnej
#
# Do logowania co X sekund chcemy SI — bo gdyby waga nie była stabilna,
# odpowiedź na "S" mogłaby nigdy nie przyjść w terminie i timer by się rozjechał.
# Stabilność i tak widać w odpowiedzi (pole "status").
RADWAG_WEIGHT_COMMAND = b"SI\r\n"   # TU ZMIEŃ KOMENDĘ jeśli chcesz inny tryb pytania

# =====================================================================
# AUTO-SKAN PORTÓW
# =====================================================================
#
# Przy skanowaniu portów aplikacja wysyła komendę "SI\r\n" do każdego
# znalezionego portu szeregowego i sprawdza czy odpowiedź wygląda jak
# ramka RADWAG (zaczyna się od "SI" lub "S "). Jeśli tak — uznajemy że
# znaleźliśmy wagę.
SCAN_TIMEOUT_S = 1.0   # krótszy timeout dla skanu, żeby nie czekać wiecznie na każdy port

# =====================================================================
# ZAPIS DANYCH
# =====================================================================

# Wzorzec nazwy pliku Excel proponowanej przy starcie aplikacji.
# strftime: %d.%m.%y = dzień.miesiąc.rok(2 cyfry), np. "10.07.26_Pomiar_wagi".
# Uwaga: w nazwie pliku nie może być ukośników (DD/MM/YY), Windows ich zabrania,
# dlatego separator daty to kropka.
EXCEL_FILENAME_PATTERN = "%d.%m.%y_Pomiar_wagi"

# Format znacznika czasu zapisywanego w CSV i pokazywanego w GUI.
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# =====================================================================
# GUI
# =====================================================================

WINDOW_TITLE = "Rejestrator wagi RADWAG WLC X2"
TABLE_MAX_ROWS = 20    # ile ostatnich pomiarów trzymać w tabeli (starsze wypadają)
LOG_MAX_LINES = 200    # ile linii w panelu logów (starsze obcinamy, żeby nie puchło)
