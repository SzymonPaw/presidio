"""Privacy-first sanitizer metadanych dokumentow.

Obslugiwane formaty:
- PDF
- DOCX
- XLSX

PDF:
- usuwa standardowe edytowalne pola /Info,
- usuwa caly pakiet XMP,
- zapisuje PDF z garbage collection, aby stare obiekty metadanych
  nie pozostaly w pliku wynikowym.

DOCX / XLSX:
- usuwa cala standardowa galaz docProps/ z pakietu OOXML,
  w tym m.in. core.xml, app.xml, custom.xml oraz miniatury,
- usuwa odpowiadajace relacje z _rels/.rels,
- usuwa odpowiadajace wpisy Override z [Content_Types].xml.

Modul dziala calkowicie lokalnie.
Nie korzysta z Office, LibreOffice, chmury ani zewnetrznych API.
"""

import io
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz


# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

OOXML_DOCPROPS_PREFIX = "docProps/"
ROOT_RELS_PATH = "_rels/.rels"
CONTENT_TYPES_PATH = "[Content_Types].xml"

# Standardowe, edytowalne pola metadanych PDF udostepniane przez PyMuPDF.
# Nie probujemy zmieniac technicznych pol typu "format" lub "encryption".
PDF_METADATA_KEYS = (
    "title",
    "author",
    "subject",
    "keywords",
    "creator",
    "producer",
    "creationDate",
    "modDate",
    "trapped",
)


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def sanitize_document_metadata(
    file_bytes: bytes,
    filename: str,
) -> bytes:
    """Usuwa standardowe metadane dokumentu.

    Dla nieobslugiwanego rozszerzenia zwraca oryginalne bajty bez zmian.
    """

    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return _sanitize_pdf_metadata(file_bytes)

    if suffix in {
        ".docx",
        ".xlsx",
    }:
        return _sanitize_ooxml_metadata(file_bytes)

    return file_bytes


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _sanitize_pdf_metadata(
    pdf_bytes: bytes,
) -> bytes:
    """Usuwa standardowe metadane PDF oraz caly pakiet XMP."""

    if not pdf_bytes:
        return pdf_bytes

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        metadata = dict(
            doc.metadata or {}
        )

        changed = False

        for key in PDF_METADATA_KEYS:
            current = metadata.get(key)

            if current not in (
                None,
                "",
                "none",
            ):
                changed = True

            # None oznacza usuniecie wartosci przy set_metadata().
            metadata[key] = None

        xml_metadata = doc.get_xml_metadata()

        if xml_metadata:
            changed = True

        # Jezeli dokument nie ma zadnych metadanych do wyczyszczenia,
        # nie przepisujemy go bez potrzeby.
        if not changed:
            return pdf_bytes

        doc.set_metadata(metadata)

        # XMP moze zawierac kopie autora, tytulu, dat oraz dowolne
        # dodatkowe pola producenta dokumentu.
        if xml_metadata:
            doc.del_xml_metadata()

        output = io.BytesIO()

        # garbage=4 usuwa nieuzywane / stare obiekty po modyfikacji.
        doc.save(
            output,
            garbage=4,
            deflate=True,
        )

        result = output.getvalue()

        if not result:
            raise RuntimeError(
                "Czyszczenie metadanych PDF wygenerowalo pusty plik."
            )

        return result

    finally:
        doc.close()


# ---------------------------------------------------------------------------
# DOCX / XLSX
# ---------------------------------------------------------------------------

def _normalize_package_path(
    value: str,
) -> str:
    """Normalizuje sciezke pakietu / target relacji do postaci POSIX."""

    normalized = (value or "").replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized.lstrip("/")


def _is_docprops_path(
    value: str,
) -> bool:
    """Zwraca True dla dowolnego elementu nalezacego do docProps/."""

    normalized = _normalize_package_path(value)

    return (
        normalized == "docProps"
        or normalized.startswith(OOXML_DOCPROPS_PREFIX)
    )


def _sanitize_ooxml_metadata(
    package_bytes: bytes,
) -> bytes:
    """Usuwa standardowe wlasciwosci dokumentu z DOCX / XLSX.

    Usuwana jest cala galaz docProps/, w tym typowo:
    - docProps/core.xml
    - docProps/app.xml
    - docProps/custom.xml
    - docProps/thumbnail.*

    Dodatkowo czyszczone sa:
    - relacje glowne pakietu w _rels/.rels,
    - wpisy Override w [Content_Types].xml.

    Tresc dokumentu, arkusze, style, obrazy, formuly i pozostale
    czesci pakietu sa kopiowane bez modyfikowania ich zawartosci.
    """

    if not package_bytes:
        return package_bytes

    source = io.BytesIO(package_bytes)

    try:
        zin = zipfile.ZipFile(
            source,
            "r",
        )
    except zipfile.BadZipFile as exc:
        raise ValueError(
            "Niepoprawny pakiet DOCX/XLSX."
        ) from exc

    with zin:
        infos = zin.infolist()

        names = [
            info.filename
            for info in infos
        ]

        # Zduplikowane nazwy w ZIP utrudniaja jednoznaczne stwierdzenie,
        # ktora wersja wpisu jest aktywna. W trybie privacy-first
        # odrzucamy taki pakiet zamiast zgadywac.
        if len(names) != len(set(names)):
            raise ValueError(
                "Pakiet DOCX/XLSX zawiera zduplikowane wpisy ZIP."
            )

        has_docprops = any(
            _is_docprops_path(name)
            for name in names
        )

        if not has_docprops:
            # Brak standardowych czesci properties = brak standardowych
            # metadanych Office do usuniecia.
            return package_bytes

        output = io.BytesIO()

        with zipfile.ZipFile(
            output,
            "w",
        ) as zout:

            for info in infos:
                filename = _normalize_package_path(
                    info.filename
                )

                # -------------------------------------------------------
                # Usuwamy cala standardowa galaz metadanych Office.
                # -------------------------------------------------------

                if _is_docprops_path(filename):
                    continue

                # -------------------------------------------------------
                # Usuwamy relacje prowadzace do docProps/*.
                # -------------------------------------------------------

                if filename == ROOT_RELS_PATH:
                    raw = zin.read(info)

                    cleaned = _remove_docprops_relationships(
                        raw
                    )

                    zout.writestr(
                        info,
                        cleaned,
                    )

                    continue

                # -------------------------------------------------------
                # Usuwamy wpisy Content Types odnoszace sie do docProps/*.
                # -------------------------------------------------------

                if filename == CONTENT_TYPES_PATH:
                    raw = zin.read(info)

                    cleaned = _remove_docprops_content_types(
                        raw
                    )

                    zout.writestr(
                        info,
                        cleaned,
                    )

                    continue

                # -------------------------------------------------------
                # Wszystko inne kopiujemy strumieniowo bez zmian.
                # -------------------------------------------------------

                with zin.open(
                    info,
                    "r",
                ) as src:

                    with zout.open(
                        info,
                        "w",
                        force_zip64=True,
                    ) as dst:

                        shutil.copyfileobj(
                            src,
                            dst,
                            length=1024 * 1024,
                        )

        result = output.getvalue()

        if not result:
            raise RuntimeError(
                "Czyszczenie metadanych OOXML wygenerowalo pusty plik."
            )

        # Fail closed: po sanitizacji w pakiecie nie moze zostac
        # zadna standardowa czesc docProps/.
        _verify_no_ooxml_docprops(result)

        return result


def _remove_docprops_relationships(
    xml_bytes: bytes,
) -> bytes:
    """Usuwa z _rels/.rels wszystkie relacje kierujace do docProps/*."""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(
            "Niepoprawny plik _rels/.rels."
        ) from exc

    for relationship in list(root):
        target = relationship.get(
            "Target",
            "",
        )

        if _is_docprops_path(target):
            root.remove(relationship)

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _remove_docprops_content_types(
    xml_bytes: bytes,
) -> bytes:
    """Usuwa wpisy [Content_Types].xml dotyczace docProps/*."""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(
            "Niepoprawny plik [Content_Types].xml."
        ) from exc

    for element in list(root):
        part_name = element.get(
            "PartName",
            "",
        )

        if _is_docprops_path(part_name):
            root.remove(element)

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _verify_no_ooxml_docprops(
    package_bytes: bytes,
) -> None:
    """Sprawdza, ze wynikowy DOCX/XLSX nie zawiera juz docProps/*."""

    try:
        with zipfile.ZipFile(
            io.BytesIO(package_bytes),
            "r",
        ) as zf:
            remaining = [
                name
                for name in zf.namelist()
                if _is_docprops_path(name)
            ]
    except zipfile.BadZipFile as exc:
        raise RuntimeError(
            "Po sanitizacji powstal niepoprawny pakiet DOCX/XLSX."
        ) from exc

    if remaining:
        raise RuntimeError(
            "Nie udalo sie usunac wszystkich metadanych OOXML: "
            + ", ".join(remaining)
        )