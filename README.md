# Rejestrator wagi RADWAG WLC X2

Prosta aplikacja desktopowa w Pythonie do cyklicznego odczytu masy
z wagi analitycznej RADWAG WLC X2 podłączonej przez **USB** (lub RS232)
i zapisu do pliku CSV.

## Pobieranie (gotowy .exe)

Najprościej: pobierz gotowy `Radwag_Rejestrator.exe` z
**[GitHub Releases](https://github.com/PanMimir/radwag-rejestrator/releases/latest)**
i uruchom dwuklikiem. Nie wymaga instalacji Pythona ani żadnych zależności.

- **Wymagania:** Windows 10 / 11 (64-bit)
- Plik nie jest podpisany cyfrowo — jeśli pojawi się ekran **SmartScreen**,
  kliknij „Więcej informacji" → „Uruchom mimo to".

Sekcje poniżej (Wymagania, Instalacja, Uruchomienie) dotyczą uruchamiania
aplikacji **ze źródeł** — potrzebne tylko jeśli chcesz rozwijać projekt
lub zbudować własny `.exe`.

## Wymagania

- Python 3.10+
- PySide6 (GUI)
- pyserial (komunikacja po porcie szeregowym)
- waga RADWAG WLC X2 z portem USB-B lub RS232
- na Windows: sterowniki USB-Serial (zazwyczaj instalują się automatycznie)

## Instalacja

```bash
pip install -r requirements.txt
```

## Konfiguracja wagi

W menu wagi:

**Komunikacja → COM 1 / COM 2** (jeśli używasz RS232) lub po prostu zostaw
ustawienia domyślne dla USB:
- Prędkość: **9600**
- Bity danych: **8**
- Bity stopu: **1**
- Parzystość: **Brak**

**Urządzenia → Komputer:**
- Port: **USB** (jeśli kabel USB-B do komputera) lub **COM 1 / COM 2** (jeśli RS232)
- Adres: **1**
- Transmisja ciągła: **Brak** ⚠️ KLUCZOWE — bo aplikacja sama pyta cyklicznie
- Interwał: dowolny (nieużywany przy transmisji "Brak")

## Uruchomienie

```bash
python main.py
```

W aplikacji:

1. Kliknij **"🔍 Szukaj wagi"** — aplikacja przeskanuje wszystkie porty COM
   wysyłając do każdego komendę `SI` i sprawdzając czy odpowiedź wygląda
   jak ramka RADWAG. Po znalezieniu od razu wybierze port w combo boxie.

   Alternatywnie: rozwiń listę **Port wagi** i wybierz ręcznie z dostępnych
   portów COM. Możesz też wpisać port ręcznie (combo jest edytowalne),
   np. `COM7` na Windowsie albo `/dev/ttyUSB0` na Linuxie.

2. Ustaw **Interwał** w sekundach (np. 1.0 = pomiar co sekundę).

3. (Opcjonalnie) **Wybierz** plik CSV gdzie będą zapisywane pomiary.
   Domyślnie `log_wagi.csv` w katalogu aplikacji.

4. Kliknij **▶ Start rejestracji**.

Aplikacja:
- co X sekund wysyła do wagi komendę `SI` (pomiar natychmiastowy),
- parsuje odpowiedź (masa, jednostka, status stabilności),
- pokazuje w GUI i dopisuje wiersz do CSV,
- gdy waga się rozłączy (kabel wyciągnięty, waga wyłączona) — zatrzymuje
  rejestrację i pokazuje alert.

## Test bez fizycznej wagi

W projekcie jest **symulator** (`simulator.py`).

**Linux / macOS:**
```bash
python simulator.py
```
Symulator utworzy wirtualny port (np. `/dev/pts/3`) — wpisz go w aplikacji.

**Windows:**
1. Zainstaluj [com0com](https://com0com.sourceforge.net/)
2. Utwórz parę wirtualnych portów, np. `COM10 ↔ COM11`
3. Uruchom: `python simulator.py COM11`
4. W aplikacji wybierz `COM10`

## Struktura projektu

```
radwag_rejestrator/
├── main.py                          # punkt wejścia
├── config.py                        # stałe i wartości domyślne
├── requirements.txt
├── simulator.py                     # symulator wagi do testów
├── README.md
├── gui/
│   ├── main_window.py               # okno główne
│   ├── worker.py                    # QThread pytający wagę cyklicznie
│   └── scan_worker.py               # QThread skanujący porty COM
├── communication/
│   └── radwag_client.py             # klient pyserial + auto-skan
├── parser/
│   └── radwag_parser.py             # parser ramki RADWAG
└── storage/
    └── csv_logger.py                # zapis do CSV
```

## Jak działa auto-skan

Aplikacja wykorzystuje fakt że protokół RADWAG ma charakterystyczną odpowiedź:

1. `pyserial.tools.list_ports.comports()` zwraca listę wszystkich portów COM
   widocznych w systemie.
2. Dla każdego portu próbuje otworzyć port z baudrate=9600.
3. Wysyła komendę `SI\r\n`.
4. Czeka maksymalnie 1 sekundę na odpowiedź.
5. Sprawdza czy odpowiedź zaczyna się od `"SI"`, `"S "`, `"SU"` lub `"SA"`.

Jeśli któryś port odpowie poprawnie — to jest waga. Skan kończy działanie
przy pierwszym dopasowaniu. Cały proces zwykle trwa 2-5 sekund.

⚠️ **Uwaga**: jeśli na innym porcie COM wisi inne urządzenie szeregowe,
dostanie zapytanie `SI\r\n`, którego się nie spodziewa. W praktyce nic
się nie dzieje (większość urządzeń ignoruje nieznane komendy), ale gdyby
miało być problemem — wybierz port ręcznie z listy zamiast skanu.

## Format CSV

```
timestamp;mass;unit;status;raw_response
2026-04-30 14:22:10;123.456;g;STABLE;SI       123.456 g
2026-04-30 14:22:11;123.457;g;STABLE;SI       123.457 g
2026-04-30 14:22:12;123.458;g;UNSTABLE;SI ?     123.458 g
```

- separator: `;` (Excel PL otwiera bez kombinowania)
- kodowanie: UTF-8 z BOM
- po każdym wierszu jest `flush()` — bezpieczne przy crashu aplikacji

## Statusy pomiaru

- **STABLE** — waga odczytała stabilną masę
- **UNSTABLE** — masa się zmienia (wibracje, podmuchy, ktoś dolewa)
- **OVER_RANGE** — przekroczony zakres ważenia
- **ERROR** — odpowiedź wagi nie pasuje do formatu (parser nie umiał rozkodować)

## Dostosowywanie parsera do innego formatu RADWAG

Domyślny parser obsługuje **standardowy protokół znakowy RADWAG** (komendy `S`, `SI`, `SU`, `SIA`).
Format odpowiedzi to ramka stałej długości 21 bajtów:

```
pozycja: 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21
znak:    S I _ ? _ - _ _ 1  8  .  3  0  0  _ g  _  _  CR LF
                |stab| |     masa (10 znaków)        | jedn. (3 znaki) |
```

Jeśli twoja waga zwraca inny format (np. dwukierunkowy z taryfą, MODBUS, albo
ciągłą transmisję CONTI), zmodyfikuj `parser/radwag_parser.py`:

1. Zmień indeksy w metodzie `parse()` zgodnie z faktycznym formatem (sprawdź
   na surowych odpowiedziach widocznych w panelu logów aplikacji oraz
   w kolumnie `raw_response` w CSV).
2. Dostosuj mapę `_STABILITY_MAP` jeśli waga używa innych znaków stabilności.

## Diagnostyka problemów

**Aplikacja nie widzi żadnego portu COM:**
- Sprawdź Menedżer urządzeń (Windows): `Win+X` → Menedżer urządzeń → "Porty (COM i LPT)".
  Powinien być widoczny port pojawiający się i znikający po podłączeniu/odpięciu USB wagi.
- Jeśli portu nie ma — brak sterownika. RADWAG zwykle używa konwerterów FTDI lub Silicon Labs.
  Spróbuj zainstalować VCP driver z [ftdichip.com](https://ftdichip.com/drivers/vcp-drivers/).

**Auto-skan nic nie znajduje:**
- Sprawdź w menu wagi: **Urządzenia → Komputer → Port = USB** i **Transmisja ciągła = Brak**.
- Sprawdź czy żadna inna aplikacja nie trzyma portu (np. monitor portu szeregowego, PuTTY).
- Wpisz port ręcznie i kliknij Start — w panelu logów zobaczysz dokładny błąd.

**ERROR w statusach:**
- Otwórz CSV i sprawdź kolumnę `raw_response` — co waga faktycznie wysyła.
  Jeśli format jest inny niż opisany wyżej, dostosuj parser.

## Co dalej (rozbudowa)

Łatwo dorobić:
- zapis do SQLite (`storage/sqlite_logger.py` o tym samym interfejsie co `CsvLogger`)
- wykres live (PySide6 + pyqtgraph)
- alarmy gdy masa wyjdzie poza zakres
- auto-reconnect po rozłączeniu (obecnie jest tylko stop+alert)
- zapis Tare / Zero / kalibracji (komendy `T`, `Z` w protokole RADWAG)

## Uwagi

- Aplikacja używa lokalnego czasu komputera. Jeśli ważne są dokładne znaczniki czasu,
  upewnij się że komputer ma synchronizację NTP.
- Plik CSV jest dopisywany — można go bezpiecznie zostawić między uruchomieniami,
  nagłówek zostanie dodany tylko jeśli plik jest pusty/nowy.
- Excel czasem blokuje plik CSV gdy ma go otwarty. Jeśli rejestracja sypie błędem
  zapisu — zamknij plik w Excelu.
