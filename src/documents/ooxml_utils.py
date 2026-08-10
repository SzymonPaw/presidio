"""
Bezpieczna, lokalna obsługa pakietów OOXML (DOCX/XLSX) oparta na lxml + zipfile.

Wszystkie operacje wykonywane są w pamięci (bytes / BytesIO).
Brak wypakowywania na dysk (ZipFile.extract/extractall nie są używane).
"""
import io
import zipfile
import logging
from lxml import etree

from src.settings import (
    MAX_CONTENT_LENGTH,
    ZIP_MAX_ENTRIES,
    ZIP_MAX_DECOMPRESSED_PART,
    ZIP_MAX_DECOMPRESSED_TOTAL,
    ZIP_MAX_RATIO,
)

logger = logging.getLogger(__name__)


class SecurityError(ValueError):
    """Zgłaszane przy naruszeniu ograniczeń bezpieczeństwa dokumentu."""


# ---------------------------------------------------------------------------
# Otwieranie pakietu
# ---------------------------------------------------------------------------

def open_ooxml_package(file_bytes: bytes) -> zipfile.ZipFile:
    """
    Otwiera pakiet OOXML (ZIP) z bajtów i waliduje podstawowe limity bezpieczeństwa.

    Sprawdzane ograniczenia:
    - maksymalny rozmiar wejściowy;
    - liczba wpisów ZIP;
    - rozmiar poszczególnych zdekompresowanych składowych;
    - łączny rozmiar po dekompresji;
    - współczynnik kompresji (ZIP bomb);
    - path traversal w nazwach wpisów.
    """
    if len(file_bytes) > MAX_CONTENT_LENGTH:
        raise SecurityError(
            f"Plik przekracza dozwolony limit rozmiaru ({MAX_CONTENT_LENGTH} B)."
        )

    buf = io.BytesIO(file_bytes)
    try:
        zf = zipfile.ZipFile(buf, "r")
    except zipfile.BadZipFile:
        raise SecurityError("Plik nie jest poprawnym archiwum ZIP.")

    infos = zf.infolist()

    if len(infos) > ZIP_MAX_ENTRIES:
        raise SecurityError(
            f"Archiwum zawiera zbyt wiele wpisów: {len(infos)} > {ZIP_MAX_ENTRIES}."
        )

    total_decompressed = 0
    for info in infos:
        # Path traversal – odrzucamy ścieżki absolutne i sekwencje ".."
        if info.filename.startswith("/") or ".." in info.filename:
            raise SecurityError(
                f"Niedozwolona ścieżka we wpisie ZIP: {info.filename!r}"
            )

        if info.file_size > ZIP_MAX_DECOMPRESSED_PART:
            raise SecurityError(
                f"Składowa '{info.filename}' przekracza limit dekompresji "
                f"({info.file_size} B > {ZIP_MAX_DECOMPRESSED_PART} B)."
            )

        total_decompressed += info.file_size

        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > ZIP_MAX_RATIO:
                raise SecurityError(
                    f"Podejrzany współczynnik kompresji ({ratio:.1f}x) "
                    f"dla '{info.filename}' – możliwa ZIP bomb."
                )

    if total_decompressed > ZIP_MAX_DECOMPRESSED_TOTAL:
        raise SecurityError(
            f"Łączny rozmiar po dekompresji przekracza limit "
            f"({total_decompressed} B > {ZIP_MAX_DECOMPRESSED_TOTAL} B)."
        )

    return zf


# ---------------------------------------------------------------------------
# Parser XML
# ---------------------------------------------------------------------------

def get_defensive_xml_parser() -> etree.XMLParser:
    """
    Zwraca defensywnie skonfigurowany parser lxml.

    - resolve_entities=False – brak XXE / Billion Laughs
    - load_dtd=False          – brak pobierania DTD
    - no_network=True         – brak żądań sieciowych
    - huge_tree=False         – limit rozmiaru drzewa
    - recover=False           – odrzucamy uszkodzony XML (fail-closed)
    """
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
        remove_comments=False,  # Komentarze mogą zawierać dane użytkownika
    )


def read_xml_part(zip_file: zipfile.ZipFile, part_name: str) -> etree.ElementTree:
    """
    Bezpiecznie odczytuje i parsuje część XML z pakietu ZIP.

    Nie wypakowuje pliku na dysk — cała operacja w pamięci.
    """
    try:
        with zip_file.open(part_name) as f:
            raw = f.read()
    except KeyError:
        raise SecurityError(f"Brak składowej '{part_name}' w pakiecie.")

    # Blokujemy DTD już na poziomie detekcji – etree i tak blokuje przez XMLParser,
    # ale dodatkowe sprawdzenie na poziomie bajtów chroni przed edge-casami.
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise SecurityError(
            f"Składowa '{part_name}' zawiera DTD/ENTITY – odrzucono."
        )

    parser = get_defensive_xml_parser()
    try:
        tree = etree.fromstring(raw, parser=parser)  # type: ignore[arg-type]
    except etree.XMLSyntaxError as exc:
        raise SecurityError(f"Błąd składni XML w '{part_name}': {exc}") from exc

    return tree


# ---------------------------------------------------------------------------
# Ponowne składanie pakietu
# ---------------------------------------------------------------------------

def rewrite_ooxml_package(
    original_bytes: bytes,
    modifications: dict[str, bytes],
) -> bytes:
    """
    Kopiuje oryginalny pakiet OOXML i podmienia tylko wskazane składowe.

    Parametry:
        original_bytes:  bajty oryginalnego pliku.
        modifications:   słownik { nazwa_składowej: nowa_zawartość_bytes }.

    Zwraca nowy pakiet jako bytes (w pamięci, bez plików tymczasowych).
    Nie stosuje ZipFile.extract() ani extractall().
    """
    zf = open_ooxml_package(original_bytes)

    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as out_zf:
        for info in zf.infolist():
            if info.filename in modifications:
                out_zf.writestr(info, modifications[info.filename])
            else:
                # Kopiujemy oryginalną zawartość bez dekompresji / rekompresji
                # gdzie to możliwe (Python >= 3.9: writestr(ZipInfo, bytes) OK)
                out_zf.writestr(info, zf.read(info.filename))

    return out_buf.getvalue()
