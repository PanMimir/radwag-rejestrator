"""
communication/radwag_client.py
==============================
Klient portu szeregowego do gadania z wagą RADWAG (USB lub RS232).

Działa synchronicznie (jeden cykl: open -> send -> recv -> return).
Asynchroniczne odpalanie cykli co X sekund jest robione w wątku w GUI,
TUTAJ siedzi tylko logika "wyślij komendę i przeczytaj odpowiedź".

Bonus: funkcja scan_for_radwag() która znajduje port, na którym wisi
waga, próbując wysłać do każdego dostępnego COM-a komendę SI i sprawdzając
czy odpowiedź wygląda jak ramka RADWAG.
"""

from typing import Optional, List, Tuple

import serial
from serial.tools import list_ports


class RadwagConnectionError(Exception):
    """Rzucane gdy coś poszło nie tak z połączeniem albo odbiorem.

    Trzymamy własny typ wyjątku (a nie zwykły OSError), bo łatwiej
    łapać go w GUI: 'except RadwagConnectionError' i wiadomo o co chodzi.
    """
    pass


class RadwagClient:
    """Wrapper na port szeregowy (pyserial) — gada z wagą RADWAG.

    Użycie:
        client = RadwagClient("COM3", baudrate=9600, timeout=2.0)
        client.connect()
        raw = client.send_and_receive(b"SI\\r\\n")
        client.close()
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = "N",
        timeout: float = 2.0,
    ):
        """
        Argumenty:
            port:     nazwa portu — "COM3" / "/dev/ttyUSB0"
            baudrate: prędkość transmisji (9600 dla COM 1 wagi)
            bytesize: bity danych (zwykle 8)
            stopbits: bity stopu (1 lub 2)
            parity:   "N"=none, "E"=even, "O"=odd
            timeout:  timeout odbioru w sekundach
        """
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.stopbits = stopbits
        self.parity = parity
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    def connect(self) -> None:
        """Otwiera port szeregowy.

        Rzuca RadwagConnectionError jeśli port nie istnieje, jest zajęty
        przez inną aplikację, albo waga jest wyłączona.
        """
        # Jeśli ktoś wywoła connect() drugi raz, najpierw zamykamy stare gniazdo.
        self.close()

        try:
            # pyserial mapuje stopbits/parity na własne stałe — robimy konwersję.
            stopbits_map = {1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}
            parity_map = {
                "N": serial.PARITY_NONE,
                "E": serial.PARITY_EVEN,
                "O": serial.PARITY_ODD,
            }

            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                stopbits=stopbits_map.get(self.stopbits, serial.STOPBITS_ONE),
                parity=parity_map.get(self.parity, serial.PARITY_NONE),
                timeout=self.timeout,
                # write_timeout: ile czekać na zakończenie wysłania.
                # Bez tego, gdyby drugi koniec zatkał bufor, sendall by się zawiesił.
                write_timeout=self.timeout,
            )

            # Czyścimy bufory wejściowy i wyjściowy.
            # Czasem po otwarciu portu siedzą tam jakieś śmieci z poprzednich
            # sesji albo niedokończonych ramek.
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

        except (serial.SerialException, OSError) as e:
            raise RadwagConnectionError(
                f"Nie udało się otworzyć portu {self.port} ({e})"
            ) from e

    def close(self) -> None:
        """Zamyka port szeregowy. Bezpieczne nawet jeśli nie był otwarty."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except (serial.SerialException, OSError):
                # Coś się posypało przy zamykaniu — trudno, lecimy dalej.
                pass
            self._serial = None

    def is_connected(self) -> bool:
        """Czy port jest otwarty."""
        return self._serial is not None and self._serial.is_open

    def send_and_receive(self, command: bytes) -> str:
        """Wysyła komendę do wagi i czeka na odpowiedź (do CR LF lub timeoutu).

        Argumenty:
            command: komenda jako bajty, np. b"SI\\r\\n"

        Zwraca:
            Surową odpowiedź jako string (zdekodowany ASCII), z zachowanymi
            spacjami w środku — bo parser potrzebuje pozycyjnego formatu.

        Rzuca:
            RadwagConnectionError — jeśli port nieotwarty, timeout,
            urwane połączenie, albo błąd dekodowania.
        """
        if self._serial is None or not self._serial.is_open:
            raise RadwagConnectionError("Port nieotwarty — wywołaj connect() najpierw.")

        try:
            # Zanim wyślemy zapytanie, wyrzucamy z bufora wejściowego wszystko
            # co mogło tam zostać z poprzednich cykli (spóźniona odpowiedź,
            # niedoczytany ogon ramki). Bez tego czytalibyśmy STARE bajty jako
            # odpowiedź na NOWĄ komendę i ramki by się rozjeżdżały — parser
            # zgłaszałby wtedy cykliczne błędy mimo sprawnej wagi.
            self._serial.reset_input_buffer()

            # Wyślij komendę. write() sam pilnuje że poszło wszystko.
            self._serial.write(command)
            # flush() to dla pewności — niektóre konwertery USB→Serial buforują
            # i bez flusha komenda potrafi siedzieć w buforze sterownika
            # zamiast lecieć po kablu.
            self._serial.flush()

            # Odbieramy odpowiedź. read_until(b"\n") czyta do napotkania LF
            # albo do timeoutu (z self._serial.timeout).
            #
            # Dlaczego nie readline()? Bo readline() ma kilka wbudowanych dziwactw
            # z buforowaniem przez io.RawIOBase — przy szybkich zapytaniach
            # potrafi gubić ramki. read_until jest niskopoziomowe i pewne.
            data = self._serial.read_until(expected=b"\n", size=256)

            if not data:
                # Pusta odpowiedź = timeout — waga nic nie odpowiedziała.
                raise RadwagConnectionError(
                    f"Brak odpowiedzi od wagi w ciągu {self.timeout}s. "
                    f"Sprawdź czy waga jest włączona i czy ma ustawioną komunikację "
                    f"przez Komputer → USB w protokole RADWAG."
                )

            # Sprawdzamy czy odpowiedź faktycznie kończy się LF — jeśli nie,
            # to znaczy że trafił timeout w środku ramki (ramka uszkodzona).
            if not data.endswith(b"\n"):
                raise RadwagConnectionError(
                    f"Niepełna odpowiedź (brak końca linii). Odebrano: {data!r}"
                )

            # Dekodujemy. ASCII jest najbezpieczniejsze — protokół RADWAG nie używa
            # znaków diakrytycznych. errors='replace' zamiast crashu na egzotycznych bajtach.
            return data.decode("ascii", errors="replace")

        except serial.SerialTimeoutException as e:
            raise RadwagConnectionError(
                f"Timeout zapisu komendy (port zatkany?): {e}"
            ) from e
        except (serial.SerialException, OSError) as e:
            # Tu trafia np. "ClearCommError failed (PermissionError)" gdy
            # ktoś wyciągnął kabel USB w środku komunikacji.
            raise RadwagConnectionError(f"Błąd komunikacji z wagą: {e}") from e

    # --- Wsparcie dla 'with RadwagClient(...) as c:' ---
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # nie tłumimy wyjątków


# =====================================================================
# AUTO-SKAN PORTÓW
# =====================================================================

def list_serial_ports() -> List[Tuple[str, str]]:
    """Zwraca listę dostępnych portów szeregowych w systemie.

    Zwraca:
        Lista par (nazwa_portu, opis), np. [("COM3", "USB Serial Device"),
                                            ("COM4", "Communications Port")]

    Działa na Windows, Linux i macOS dzięki pyserial.tools.list_ports.
    """
    return [(p.device, p.description) for p in list_ports.comports()]


def is_radwag_response(raw: str) -> bool:
    """Heurystyka: czy ta odpowiedź wygląda jak ramka RADWAG?

    Ramka odpowiedzi na komendę SI ma format:
        "SI" + spacja + znak_stabilności + spacja + masa + spacja + jednostka + CR LF

    Czyli: zaczyna się od "SI " (z możliwą spacją) i ma długość >= 19 znaków.
    """
    if not raw or len(raw) < 9:
        return False
    # Pierwsze 2 znaki to "SI" (echo komendy).
    # W niektórych konfiguracjach waga odpowiada samą wartością bez echa,
    # zaczynając od znaku stabilności + spacja. Akceptujemy oba.
    head = raw[:2]
    return head in ("SI", "S ", "SU", "SA")


def scan_for_radwag(
    baudrate: int = 9600,
    timeout: float = 1.0,
    progress_callback=None,
) -> Optional[Tuple[str, str]]:
    """Skanuje wszystkie dostępne porty szeregowe szukając wagi RADWAG.

    Argumenty:
        baudrate:          prędkość do testowania (9600 jak na COM 1 w wadze)
        timeout:           ile czekać na każdą odpowiedź (krótki, żeby nie blokować)
        progress_callback: opcjonalna funkcja(port, status) do raportowania postępu
                           — przyda się żeby GUI mogło pokazać "skanuję COM3..."

    Zwraca:
        (port, opis) jeśli znaleziono wagę, None jeśli nic nie znaleziono.

    UWAGA: ta funkcja blokuje (synchroniczna). W GUI wywołuj ją w osobnym
    wątku, inaczej okno zamarznie na kilka sekund.
    """
    from config import RADWAG_WEIGHT_COMMAND  # import lokalny, żeby uniknąć cyklicznego

    ports = list_serial_ports()

    for port_name, description in ports:
        if progress_callback:
            progress_callback(port_name, f"sprawdzam {port_name} ({description})...")

        # Próbujemy się połączyć i zapytać.
        # Każdy błąd ignorujemy i lecimy dalej — to jest właśnie sens skanu.
        try:
            client = RadwagClient(port_name, baudrate=baudrate, timeout=timeout)
            client.connect()
            try:
                raw = client.send_and_receive(RADWAG_WEIGHT_COMMAND)
                if is_radwag_response(raw):
                    if progress_callback:
                        progress_callback(port_name, f"ZNALEZIONO! Odpowiedź: {raw.strip()!r}")
                    return (port_name, description)
                else:
                    if progress_callback:
                        progress_callback(port_name, f"odpowiedź nie pasuje do RADWAG: {raw.strip()!r}")
            finally:
                client.close()
        except RadwagConnectionError as e:
            if progress_callback:
                progress_callback(port_name, f"brak odpowiedzi ({e})")
        except Exception as e:
            # Cokolwiek innego — np. port zajęty przez inną aplikację.
            if progress_callback:
                progress_callback(port_name, f"błąd: {e}")

    return None
