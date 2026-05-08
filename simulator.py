"""
simulator.py
============
Symulator wagi RADWAG do testów aplikacji bez fizycznej wagi.

Symulator działa różnie w zależności od systemu:

LINUX / MACOS:
    Uruchom: python simulator.py
    Skrypt utworzy wirtualną parę portów (pty) i wypisze nazwę portu,
    którą trzeba wpisać w aplikacji, np. /dev/pts/3.

WINDOWS:
    Wbudowany w Windows nie ma odpowiednika pty, więc trzeba najpierw
    zainstalować com0com (https://com0com.sourceforge.net/) i utworzyć
    parę wirtualnych portów, np. COM10 ↔ COM11.
    Następnie uruchom: python simulator.py COM11
    W aplikacji wpisz drugi port pary (np. COM10).

Symulator wysyła "fałszywe" pomiary masy ~100 g z lekkimi wahaniami.
"""

import sys
import time
import random
import platform
import threading


def build_response(mass: float, unit: str = "g", stable: bool = True) -> bytes:
    """Buduje ramkę odpowiedzi w formacie RADWAG.

    Format: "SI" + sp + stab + sp + sign+9chars_mass + sp + 3chars_unit + CRLF
    """
    stab = " " if stable else "?"

    # Pole masy: 10 znaków, wyrównane do prawej.
    mass_field = f"{mass:.3f}".rjust(10)
    mass_field = mass_field[-10:]  # przycinamy gdyby się rozjechało

    unit_field = unit.ljust(3)

    frame = f"SI {stab} {mass_field} {unit_field}\r\n"
    return frame.encode("ascii")


def serve_serial(serial_obj) -> None:
    """Pętla obsługi połączenia. Czyta komendy, odsyła ramki RADWAG."""
    base_mass = 100.0
    print(f"[SIM] Czekam na komendy. Naciśnij Ctrl+C aby zakończyć.\n")

    while True:
        try:
            data = serial_obj.read(64)  # blokuje do timeoutu lub danych
            if not data:
                continue

            # Może przyjść więcej niż jedna komenda na raz; rozdzielamy po CRLF.
            for line in data.replace(b"\r", b"\n").split(b"\n"):
                cmd = line.strip().decode("ascii", errors="replace")
                if not cmd:
                    continue

                print(f"[SIM] Odebrano komendę: {cmd!r}")

                if cmd in ("S", "SI", "SU", "SIA"):
                    mass = base_mass + random.uniform(-0.05, 0.05)
                    stable = random.random() > 0.15  # 15% szans na "niestabilną"
                    response = build_response(mass, "g", stable)
                    serial_obj.write(response)
                    serial_obj.flush()
                    print(f"[SIM] Wysłano:        {response!r}")
                else:
                    print(f"[SIM] Nieznana komenda, ignoruję: {cmd!r}")
        except KeyboardInterrupt:
            print("\n[SIM] Zamykanie symulatora.")
            return
        except Exception as e:
            print(f"[SIM] Błąd: {e}")
            time.sleep(0.5)


def run_pty() -> None:
    """Tryb Linux/Mac: tworzy parę pty i czeka na połączenia."""
    import os
    import pty

    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    print(f"[SIM] Wirtualny port utworzony: {slave_name}")
    print(f"[SIM] W aplikacji wpisz ten port jako 'Port wagi'.")
    print(f"[SIM] (Auto-skan może go nie wykryć — wpisz ręcznie.)\n")

    # Owijamy master_fd w obiekt podobny do serial.Serial.
    # Nie używamy pyserial bo on nie lubi pty na wszystkich systemach.
    class PtyWrapper:
        def __init__(self, fd):
            self.fd = fd
        def read(self, n):
            try:
                return os.read(self.fd, n)
            except OSError:
                return b""
        def write(self, data):
            return os.write(self.fd, data)
        def flush(self):
            pass

    serve_serial(PtyWrapper(master_fd))


def run_serial(port_name: str) -> None:
    """Tryb Windows (z com0com) lub gdy chcemy przypiąć się do konkretnego portu."""
    import serial

    print(f"[SIM] Otwieram port: {port_name}")
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=9600,
            bytesize=8,
            stopbits=1,
            parity="N",
            timeout=0.5,  # niski, żeby pętla read() nie blokowała na wieki
        )
    except serial.SerialException as e:
        print(f"[SIM] Nie mogę otworzyć portu {port_name}: {e}")
        print(f"[SIM] Na Windowsie zainstaluj com0com i utwórz parę portów.")
        sys.exit(1)

    print(f"[SIM] Port otwarty.")
    print(f"[SIM] W aplikacji wybierz drugi port pary com0com.\n")
    try:
        serve_serial(ser)
    finally:
        ser.close()


def main() -> None:
    print("=" * 60)
    print(" SYMULATOR WAGI RADWAG WLC X2 ")
    print("=" * 60)

    if len(sys.argv) > 1:
        # Podany port w argumencie — używamy pyserial.
        run_serial(sys.argv[1])
    elif platform.system() in ("Linux", "Darwin"):
        # Linux / Mac — używamy pty.
        run_pty()
    else:
        # Windows bez argumentu.
        print("\n[SIM] Na Windowsie:")
        print("[SIM]   1. Zainstaluj com0com: https://com0com.sourceforge.net/")
        print("[SIM]   2. Utwórz parę portów, np. COM10 ↔ COM11")
        print("[SIM]   3. Uruchom: python simulator.py COM11")
        print("[SIM]   4. W aplikacji wybierz COM10")
        sys.exit(1)


if __name__ == "__main__":
    main()
