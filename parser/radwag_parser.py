"""
parser/radwag_parser.py
=======================
Parser odpowiedzi z wagi RADWAG (protokół znakowy).

FORMAT ODPOWIEDZI NA KOMENDĘ "SI" (pomiar natychmiastowy)
---------------------------------------------------------
Wg instrukcji protokołu komunikacyjnego RADWAG ramka ma stałą długość
i wygląda tak (pozycje znakowe, liczone od 1):

    poz.  1-2 : nazwa komendy, czyli "SI"
    poz.  3   : spacja
    poz.  4   : znak stabilności:
                  ' ' (spacja) = wynik STABILNY
                  '?'          = wynik NIESTABILNY
                  '^'          = przekroczenie zakresu "+"
                  'v'          = przekroczenie zakresu "-"
    poz.  5   : spacja
    poz.  6   : znak liczby ('-' albo spacja jeśli dodatnia)
    poz.  7-15: masa, 9 znaków, wyrównana do prawej, z kropką dziesiętną
    poz. 16   : spacja
    poz. 17-19: jednostka, 3 znaki, wyrównana do lewej (np. "g  ", "kg ")
    poz. 20-21: CR LF

Przykład (znaki '_' to spacje):
    SI_ _-__18.3000_g__\\r\\n     -> stabilna, -18.3 g
    SI_?___123.456_g__\\r\\n      -> niestabilna, +123.456 g

Klasa zwraca obiekt MeasurementResult z polami:
    mass         - float, masa (None gdy parse error)
    unit         - str, jednostka (np. "g", "kg")
    status       - str: "STABLE" / "UNSTABLE" / "OVER_RANGE" / "ERROR"
    raw_response - str, dokładnie to co przyszło z wagi (do logów / debugu)
"""

from dataclasses import dataclass
from typing import Optional


# Mapowanie znaku stabilności → status logiczny.
_STABILITY_MAP = {
    " ": "STABLE",
    "?": "UNSTABLE",
    "^": "OVER_RANGE",
    "v": "OVER_RANGE",
}


@dataclass
class MeasurementResult:
    """Wynik jednego pomiaru z wagi.

    Pola:
        mass:         masa w jednostce z pola unit (None jeśli nie udało się sparsować)
        unit:         jednostka jako string ("g", "kg", "ct", ...)
        status:       "STABLE" | "UNSTABLE" | "OVER_RANGE" | "ERROR"
        raw_response: surowa, oryginalna ramka tekstowa odebrana z wagi
    """
    mass: Optional[float]
    unit: str
    status: str
    raw_response: str


class RadwagParser:
    """Parser ramki odpowiedzi RADWAG.

    Trzymamy go jako klasę (zamiast luźnej funkcji), bo dzięki temu
    łatwo będzie później dodać warianty (np. inny format dla "S" zamiast "SI",
    albo dla wagi w trybie "ciągłej transmisji").
    """

    def parse(self, raw: str) -> MeasurementResult:
        """Parsuje surową odpowiedź z wagi.

        Argumenty:
            raw: tekstowa odpowiedź z wagi, łącznie z CR LF lub bez nich.

        Zwraca:
            MeasurementResult — nigdy nie rzuca wyjątku. Jeśli format się
            nie zgadza, ustawia status="ERROR" i mass=None, ale ZAWSZE
            zwraca raw_response, żeby było co wpisać do CSV i logów.

        Dlaczego nigdy nie rzuca wyjątku?
            Bo rejestrator ma działać 24/7 i jedna nietypowa ramka
            (np. waga akurat się resetuje) nie może zabić wątku.
        """
        # Zapamiętujemy oryginał do logów — niezależnie od tego co się dalej stanie.
        original = raw

        if raw is None:
            return MeasurementResult(None, "", "ERROR", "")

        # Zdejmujemy CR/LF i białe znaki na końcach — ale tylko na końcach.
        # NIE używamy strip() na środku ramki, bo spacje w środku są znaczące
        # (to one tworzą stały format pozycyjny).
        clean = raw.rstrip("\r\n")

        # Pusta ramka = błąd. Nic do roboty.
        if not clean:
            return MeasurementResult(None, "", "ERROR", original)

        # Minimalna długość sensownej ramki "SI": 2 (cmd) + 1 (sp) + 1 (stb)
        # + 1 (sp) + 1 (znak) + co najmniej 1 cyfra + 1 (sp) + 1 (jedn.) = 9 znaków.
        # Realne ramki mają ~19 znaków. Poniżej 9 = na pewno śmieć.
        if len(clean) < 9:
            return MeasurementResult(None, "", "ERROR", original)

        # --- Parsowanie pozycyjne ---
        # Indeksy w Pythonie liczymy od 0, więc pozycja "4" w dokumentacji
        # to indeks [3] w stringu.
        try:
            stability_char = clean[3]
            status = _STABILITY_MAP.get(stability_char, "ERROR")

            # Znak liczby (poz. 6 w dok. = indeks [5]) i masa (poz. 7-15 = [6:15])
            # to oddzielne pola — nie można ich łączyć i stripować razem,
            # bo float("-    72.04") rzuca ValueError przez wewnętrzne spacje.
            sign_char = clean[5] if len(clean) > 5 else " "
            mass_field = clean[6:15].strip()
            mass_value = float(mass_field) if mass_field else None
            if mass_value is not None and sign_char == "-":
                mass_value = -mass_value

            # Jednostka: pozycje 17-19 (w dokumentacji), czyli [16:19].
            # Wyrównana do lewej spacjami, więc strip() daje czyste "g" / "kg".
            unit_field = clean[16:19].strip() if len(clean) >= 17 else ""

            return MeasurementResult(
                mass=mass_value,
                unit=unit_field,
                status=status,
                raw_response=original,
            )

        except (ValueError, IndexError):
            # ValueError: float() nie połknął tego co było w polu masy.
            # IndexError: ramka krótsza niż się spodziewaliśmy.
            # W obu przypadkach: zwracamy ERROR ale z surową odpowiedzią,
            # żeby człowiek mógł zobaczyć co właściwie waga wysłała.
            return MeasurementResult(None, "", "ERROR", original)
