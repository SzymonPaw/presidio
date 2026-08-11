#!/usr/bin/env python3
"""Generator lokalnych slownikow z surowych plikow zrodlowych.

Czyta pliki z data/source/ i generuje znormalizowane slowniki
w config/recognizers/. Rekordy z podejrzanymi znakami sa pomijane
i zapisywane w data/reports/dictionary_rejections.csv.
"""
import os
import csv
import sys

# ---------------------------------------------------------------------------
# Konfiguracja sciezek
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_DIR = os.path.join(BASE_DIR, "data", "source")
RECOGNIZERS_DIR = os.path.join(BASE_DIR, "config", "recognizers")
REPORTS_DIR = os.path.join(BASE_DIR, "data", "reports")
REJECTION_REPORT_PATH = os.path.join(REPORTS_DIR, "dictionary_rejections.csv")

# Znaki, ktore wskazuja na uszkodzony rekord
_SUSPICIOUS_CHARS = frozenset([
    "?",        # znak zapytania moze swiadczyc o bledzie dekodowania
    "�",   # Unicode Replacement Character
])


def _has_suspicious(value: str) -> bool:
    """Zwraca True, jesli wartosc zawiera podejrzane znaki zastepche."""
    for ch in value:
        if ch in _SUSPICIOUS_CHARS:
            return True
    return False


def _detect_delimiter(header_line: str) -> str:
    """Probuje rozpoznac separator na podstawie pierwszego wiersza."""
    if ";" in header_line:
        return ";"
    if "\t" in header_line:
        return "\t"
    if "," in header_line:
        return ","
    return ""


# ---------------------------------------------------------------------------
# Przetwarzanie imion / nazwisk
# ---------------------------------------------------------------------------
_NAME_COLUMNS = ["name", "imie", "imię"]         # imie / imie z polskimi znakami
_SURNAME_COLUMNS = ["surname", "nazwisko"]
_COUNT_COLUMNS = ["count", "liczba", "liczba_wystapien"]


def _find_column(header: list[str], candidates: list[str], label: str, file_path: str) -> int:
    """Znajduje dokladnie jedna kolumne z listy kandydatow.

    Jesli nie znaleziono lub znaleziono wiecej niz jedna - konczy skrypt
    z czytelnym bledem.
    """
    matches = []
    for idx, col in enumerate(header):
        if col in candidates:
            matches.append((idx, col))
    if len(matches) == 0:
        print(f"BLAD: Nie znaleziono kolumny {label} w pliku {os.path.basename(file_path)}.")
        print(f"  Znalezione kolumny: {header}")
        print(f"  Oczekiwane nazwy : {candidates}")
        sys.exit(1)
    if len(matches) > 1:
        found = [m[1] for m in matches]
        print(f"BLAD: Niejednoznaczna struktura pliku {os.path.basename(file_path)}.")
        print(f"  Znaleziono wiele pasujacych kolumn {label}: {found}")
        sys.exit(1)
    return matches[0][0]


def process_names_file(
    file_path: str,
    output_path: str,
    is_surname: bool = False,
) -> list[list[str]]:
    """Przetwarza plik imion lub nazwisk i zwraca liste odrzuconych rekordow."""
    kind = "nazwisk" if is_surname else "imion"
    print(f"\nPrzetwarzanie {kind}: {os.path.basename(file_path)} ...")

    if not os.path.exists(file_path):
        print(f"BLAD: Brak pliku zrodlowego: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8-sig") as f:
        first_line = f.readline().strip()
        f.seek(0)

        delimiter = _detect_delimiter(first_line)
        if not delimiter:
            delimiter = ";"  # domyslny fallback dla imion/nazwisk

        reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        header_raw = next(reader, None)
        if not header_raw:
            print(f"BLAD: Pusty plik {file_path}")
            sys.exit(1)

        header = [col.strip().lower() for col in header_raw]

        name_candidates = _SURNAME_COLUMNS if is_surname else _NAME_COLUMNS
        val_idx = _find_column(header, name_candidates, kind, file_path)

        # Kolumna z liczba wystapien jest opcjonalna
        count_idx = -1
        for idx, col in enumerate(header):
            if col in _COUNT_COLUMNS:
                count_idx = idx
                break

        seen: set[str] = set()
        results: list[tuple[str, str]] = []
        duplicates = 0
        empty_count = 0
        rejected = 0
        rejections: list[list[str]] = []

        for line_no, row in enumerate(reader, start=2):
            if not row or len(row) <= val_idx:
                empty_count += 1
                continue

            val = row[val_idx].strip().upper()
            count = "0"
            if count_idx != -1 and len(row) > count_idx:
                c = row[count_idx].strip()
                if c.isdigit():
                    count = c

            if not val:
                empty_count += 1
                continue

            if _has_suspicious(val):
                rejected += 1
                rejections.append([
                    file_path, str(line_no), val,
                    "Podejrzany znak zastepczy (? lub U+FFFD)"
                ])
                continue

            if val in seen:
                duplicates += 1
                continue

            seen.add(val)
            results.append((val, count))

    # Zapis
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.writer(out_f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        head_name = "surname" if is_surname else "name"
        writer.writerow([head_name, "count"])
        for val, count in results:
            writer.writerow([val, count])

    valid = len(results)
    print(f"  Zaimportowano : {valid}")
    print(f"  Puste        : {empty_count}")
    print(f"  Zduplikowane : {duplicates}")
    print(f"  Odrzucone    : {rejected}")
    return rejections

# ---------------------------------------------------------------------------
# Przetwarzanie TERC
# ---------------------------------------------------------------------------

_TERC_REQUIRED_COLUMNS = [
    "woj",
    "pow",
    "gmi",
    "rodz",
    "nazwa",
]


def _read_terc_text(file_path: str) -> str:
    """
    Wczytuje TERC z kilkoma bezpiecznymi probami kodowania.

    Pliki z GUS moga pochodzic z roznych eksportow, dlatego
    obslugujemy UTF-8 oraz popularne polskie kodowania Windows.

    Funkcja nie modyfikuje danych.
    """
    with open(file_path, "rb") as f:
        raw = f.read()

    encodings = (
        "utf-8-sig",
        "utf-8",
        "cp1250",
        "iso-8859-2",
    )

    for encoding in encodings:
        try:
            text = raw.decode(encoding)

            print(
                f"  Kodowanie TERC: {encoding}"
            )

            return text

        except UnicodeDecodeError:
            continue

    print(
        "BLAD: Nie udalo sie rozpoznac kodowania "
        f"pliku {os.path.basename(file_path)}."
    )

    sys.exit(1)


def _write_simple_dictionary(
    output_path: str,
    values: set[str],
) -> None:
    """
    Zapisuje prosty slownik tekstowy:
    jedna wartosc w jednej linii.

    Wartosc jest przechowywana malymi literami,
    tak samo jak obecny localities.txt.
    """
    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
        newline="",
    ) as out_f:

        for value in sorted(values):
            out_f.write(
                value + "\n"
            )


def process_terc_file(
    file_path: str,
    voivodeships_output_path: str,
    counties_output_path: str,
    communes_output_path: str,
) -> list[list[str]]:
    """
    Przetwarza pelny plik TERC.

    Generuje trzy slowniki:

    - voivodeships.txt
      wojewodztwa

    - counties.txt
      powiaty oraz jednostki wystepujace
      na poziomie powiatu

    - communes.txt
      gminy miejskie, wiejskie
      i miejsko-wiejskie

    Dla gmin miejskich generowane sa dodatkowo aliasy:

        GDANSK
        M.GDANSK
        M. GDANSK

    co pozwala obsluzyc formularze zapisujace
    nazwe gminy np. jako M.GDANSK.
    """

    print(
        f"\nPrzetwarzanie TERC: "
        f"{os.path.basename(file_path)} ..."
    )

    if not os.path.exists(
        file_path
    ):
        print(
            f"BLAD: Brak pliku zrodlowego: "
            f"{file_path}"
        )
        sys.exit(1)

    text = _read_terc_text(
        file_path
    )

    lines = text.splitlines()

    if not lines:
        print(
            f"BLAD: Pusty plik {file_path}"
        )
        sys.exit(1)

    delimiter = _detect_delimiter(
        lines[0]
    )

    if not delimiter:
        # Oficjalne CSV TERYT zwykle wykorzystuje
        # srednik. Jezeli autodetekcja sie nie uda,
        # stosujemy go jako fallback.
        delimiter = ";"

    reader = csv.reader(
        lines,
        delimiter=delimiter,
        quoting=csv.QUOTE_MINIMAL,
    )

    header_raw = next(
        reader,
        None,
    )

    if not header_raw:
        print(
            f"BLAD: Pusty plik {file_path}"
        )
        sys.exit(1)

    header = [
        col
        .lstrip("\ufeff")
        .strip()
        .lower()
        for col in header_raw
    ]

    print(
        f"  Kolumny TERC: {header}"
    )

    # -------------------------------------------------------
    # Sprawdzamy tylko kolumny potrzebne naszej aplikacji.
    #
    # STAN_NA NIE jest wymagane.
    # -------------------------------------------------------

    missing_columns = [
        column
        for column in _TERC_REQUIRED_COLUMNS
        if column not in header
    ]

    if missing_columns:
        print(
            "BLAD: Brakuje wymaganych kolumn TERC: "
            f"{missing_columns}"
        )

        print(
            f"  Znalezione kolumny: {header}"
        )

        print(
            f"  Wymagane kolumny: "
            f"{_TERC_REQUIRED_COLUMNS}"
        )

        sys.exit(1)

    woj_idx = header.index(
        "woj"
    )

    pow_idx = header.index(
        "pow"
    )

    gmi_idx = header.index(
        "gmi"
    )

    rodz_idx = header.index(
        "rodz"
    )

    nazwa_idx = header.index(
        "nazwa"
    )

    max_required_index = max(
        woj_idx,
        pow_idx,
        gmi_idx,
        rodz_idx,
        nazwa_idx,
    )

    # -------------------------------------------------------
    # Slowniki
    # -------------------------------------------------------

    voivodeships: set[str] = set()
    counties: set[str] = set()
    communes: set[str] = set()

    # Liczniki informacyjne
    empty_count = 0
    rejected = 0

    # Ile aliasow M.xxx dodalismy.
    commune_aliases = 0

    rejections: list[list[str]] = []

    # -------------------------------------------------------
    # Rekordy TERC
    # -------------------------------------------------------

    for line_no, row in enumerate(
        reader,
        start=2,
    ):
        if (
            not row
            or len(row)
            <= max_required_index
        ):
            empty_count += 1
            continue

        woj = row[
            woj_idx
        ].strip()

        powiat = row[
            pow_idx
        ].strip()

        gmina = row[
            gmi_idx
        ].strip()

        rodz = row[
            rodz_idx
        ].strip()

        name = row[
            nazwa_idx
        ].strip()

        # Normalizacja bialych znakow.
        name = " ".join(
            name.split()
        )

        if not name:
            empty_count += 1
            continue

        if _has_suspicious(
            name
        ):
            rejected += 1

            rejections.append(
                [
                    file_path,
                    str(line_no),
                    name,
                    (
                        "Podejrzany znak zastepczy "
                        "(? lub U+FFFD)"
                    ),
                ]
            )

            continue

        # Zachowujemy ten sam styl co localities.txt:
        # wartosci w pliku wynikowym sa lowercase.
        normalized = (
            name
            .strip()
            .lower()
        )

        # ===================================================
        # WOJEWODZTWO
        #
        # WOJ = wypelnione
        # POW = puste
        # GMI = puste
        # ===================================================

        if (
            woj
            and not powiat
            and not gmina
        ):
            voivodeships.add(
                normalized
            )

            continue

        # ===================================================
        # POWIAT
        #
        # WOJ = wypelnione
        # POW = wypelnione
        # GMI = puste
        #
        # Na tym poziomie TERC wystepuja rowniez
        # miasta na prawach powiatu.
        # ===================================================

        if (
            woj
            and powiat
            and not gmina
        ):
            counties.add(
                normalized
            )

            continue

        # ===================================================
        # GMINA
        #
        # RODZ:
        #
        # 1 = gmina miejska
        # 2 = gmina wiejska
        # 3 = gmina miejsko-wiejska
        #
        # Nie dodajemy tutaj:
        # 4 = miasto w gminie miejsko-wiejskiej
        # 5 = obszar wiejski
        # 8 = dzielnica Warszawy
        # 9 = delegatura
        #
        # ponieważ chcemy slownik GMIN,
        # a nie wszystkich jednostek pomocniczych.
        # ===================================================

        if (
            gmina
            and rodz in {
                "1",
                "2",
                "3",
            }
        ):
            communes.add(
                normalized
            )

            # -----------------------------------------------
            # Formularze administracyjne bardzo czesto
            # zapisują gmine miejska w formacie:
            #
            # M.GDANSK
            #
            # TERC ma natomiast:
            #
            # GDANSK
            #
            # Dlatego dla RODZ=1 tworzymy dwa dodatkowe
            # warianty.
            # -----------------------------------------------

            if rodz == "1":
                alias_no_space = (
                    f"m.{normalized}"
                )

                alias_space = (
                    f"m. {normalized}"
                )

                before = len(
                    communes
                )

                communes.add(
                    alias_no_space
                )

                communes.add(
                    alias_space
                )

                commune_aliases += (
                    len(communes)
                    - before
                )

    # -------------------------------------------------------
    # Zapis plikow
    # -------------------------------------------------------

    _write_simple_dictionary(
        voivodeships_output_path,
        voivodeships,
    )

    _write_simple_dictionary(
        counties_output_path,
        counties,
    )

    _write_simple_dictionary(
        communes_output_path,
        communes,
    )

    print()
    print(
        "  TERC - wyniki:"
    )

    print(
        "  Wojewodztwa : "
        f"{len(voivodeships)}"
    )

    print(
        "  Powiaty      : "
        f"{len(counties)}"
    )

    print(
        "  Gminy/aliasy : "
        f"{len(communes)}"
    )

    print(
        "  Aliasy M.xxx : "
        f"{commune_aliases}"
    )

    print(
        "  Puste        : "
        f"{empty_count}"
    )

    print(
        "  Odrzucone    : "
        f"{rejected}"
    )

    return rejections

# ---------------------------------------------------------------------------
# Przetwarzanie SIMC (miejscowosci)
# ---------------------------------------------------------------------------
_LOCALITY_COLUMNS = ["nazwa", "name", "miejscowosc", "miejscowość"]


def process_simc_file(file_path: str, output_path: str) -> list[list[str]]:
    """Przetwarza plik SIMC i zwraca liste odrzuconych rekordow."""
    print(f"\nPrzetwarzanie miejscowosci: {os.path.basename(file_path)} ...")

    if not os.path.exists(file_path):
        print(f"BLAD: Brak pliku zrodlowego: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8-sig") as f:
        first_line = f.readline().strip()
        f.seek(0)

        delimiter = _detect_delimiter(first_line)
        is_single_column = not delimiter

        if is_single_column:
            # Plik jednokolumnowy - czytamy linie bezposrednio
            lines = f.readlines()
            header_line = lines[0].strip().lower() if lines else ""

            start_idx = 0
            if header_line in _LOCALITY_COLUMNS:
                start_idx = 1  # pomijamy naglowek

            seen: set[str] = set()
            results: list[str] = []
            duplicates = 0
            empty_count = 0
            rejected = 0
            rejections: list[list[str]] = []

            for i in range(start_idx, len(lines)):
                line_no = i + 1
                val = lines[i].strip()
                val = " ".join(val.split())
                val_lower = val.lower()

                if not val_lower:
                    empty_count += 1
                    continue

                if _has_suspicious(val_lower):
                    rejected += 1
                    rejections.append([
                        file_path, str(line_no), val,
                        "Podejrzany znak zastepczy (? lub U+FFFD)"
                    ])
                    continue

                if val_lower in seen:
                    duplicates += 1
                    continue

                seen.add(val_lower)
                results.append(val_lower)
        else:
            # Plik wielokolumnowy - uzywamy csv.reader
            reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
            header_raw = next(reader, None)
            if not header_raw:
                print(f"BLAD: Pusty plik {file_path}")
                sys.exit(1)

            header = [col.strip().lower() for col in header_raw]

            # Szukamy kolumny z nazwa miejscowosci
            matches = []
            for idx, col in enumerate(header):
                if col in _LOCALITY_COLUMNS:
                    matches.append((idx, col))

            if len(matches) == 0:
                print(f"BLAD: Nie znaleziono kolumny miejscowosci w pliku {os.path.basename(file_path)}.")
                print(f"  Znalezione kolumny: {header}")
                print(f"  Oczekiwane nazwy : {_LOCALITY_COLUMNS}")
                sys.exit(1)
            if len(matches) > 1:
                found_names = [m[1] for m in matches]
                print(f"BLAD: Niejednoznaczna struktura pliku {os.path.basename(file_path)}.")
                print(f"  Znaleziono wiele pasujacych kolumn: {found_names}")
                sys.exit(1)

            val_idx = matches[0][0]

            seen = set()
            results = []
            duplicates = 0
            empty_count = 0
            rejected = 0
            rejections = []

            for line_no, row in enumerate(reader, start=2):
                if not row or len(row) <= val_idx:
                    empty_count += 1
                    continue

                val = row[val_idx].strip()
                val = " ".join(val.split())
                val_lower = val.lower()

                if not val_lower:
                    empty_count += 1
                    continue

                if _has_suspicious(val_lower):
                    rejected += 1
                    rejections.append([
                        file_path, str(line_no), val,
                        "Podejrzany znak zastepczy (? lub U+FFFD)"
                    ])
                    continue

                if val_lower in seen:
                    duplicates += 1
                    continue

                seen.add(val_lower)
                results.append(val_lower)

    # Zapis
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out_f:
        for val in sorted(results):
            out_f.write(val + "\n")

    valid = len(results)
    print(f"  Zaimportowano : {valid}")
    print(f"  Puste        : {empty_count}")
    print(f"  Zduplikowane : {duplicates}")
    print(f"  Odrzucone    : {rejected}")
    return rejections


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 50)
    print("Generator slownikow - start")
    print("=" * 50)

    first_names_src = os.path.join(SOURCE_DIR, "first_names_source.csv")
    first_names_out = os.path.join(RECOGNIZERS_DIR, "first_names.csv")

    surnames_src = os.path.join(SOURCE_DIR, "surnames_source.csv")
    surnames_out = os.path.join(RECOGNIZERS_DIR, "surnames.csv")

    simc_src = os.path.join(SOURCE_DIR, "SIMC.csv")
    simc_out = os.path.join(RECOGNIZERS_DIR, "localities.txt")
    terc_src = os.path.join(
        SOURCE_DIR,
        "TERC.csv",
    )

    voivodeships_out = os.path.join(
        RECOGNIZERS_DIR,
        "voivodeships.txt",
    )

    counties_out = os.path.join(
        RECOGNIZERS_DIR,
        "counties.txt",
    )

    communes_out = os.path.join(
        RECOGNIZERS_DIR,
        "communes.txt",
    )


    all_rejections: list[list[str]] = []

    all_rejections.extend(
        process_names_file(
            first_names_src,
            first_names_out,
            is_surname=False,
        )
    )

    all_rejections.extend(
        process_names_file(
            surnames_src,
            surnames_out,
            is_surname=True,
        )
    )

    all_rejections.extend(
        process_simc_file(
            simc_src,
            simc_out,
        )
    )

    all_rejections.extend(
        process_terc_file(
            terc_src,
            voivodeships_out,
            counties_out,
            communes_out,
        )
    )

    # Zapis raportu odrzucen
    if all_rejections:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        with open(REJECTION_REPORT_PATH, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["file_path", "line_no", "source_value", "reason"])
            for rej in all_rejections:
                writer.writerow(rej)
        print(f"\nZapisano {len(all_rejections)} odrzuconych rekordow w: {REJECTION_REPORT_PATH}")
    else:
        print("\nBrak odrzuconych rekordow.")

    print("\n" + "=" * 50)
    print("Generowanie slownikow zakonczone sukcesem.")
    print("=" * 50)


if __name__ == "__main__":
    main()
