"""
Adapter DOCX — analiza i anonimizacja dokumentów Word.

Architektura:
1. Otwórz pakiet OOXML (ZIP) wyłącznie w pamięci.
2. Wyodrębnij tekst ze wszystkich istotnych części (akapit po akapicie).
3. Przekaż tekst do istniejącego DeterministicAnalyzer.
4. Podmień zatwierdzone wartości od końca zakresu (by nie przesuwać offsetów).
5. Zapisz zmienione składowe XML z powrotem do zmodyfikowanego pakietu ZIP.

Nie używa python-docx do zapisu — tylko lxml + zipfile.
Nie tworzy plików tymczasowych.
"""
from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Tuple

from lxml import etree

from src.documents.ooxml_utils import (
    open_ooxml_package,
    read_xml_part,
    rewrite_ooxml_package,
    SecurityError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stałe XML
# ---------------------------------------------------------------------------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WNS = f"{{{W_NS}}}"
NAMESPACES = {"w": W_NS}

# Elementy zawierające tekst użytkownika
TEXT_TAGS = {
    f"{WNS}t",         # Normalny tekst
    f"{WNS}delText",   # Tekst śledzenia zmian (usunięty)
    f"{WNS}instrText", # Tekst pól instrukcji (mogą zawierać dane)
}

# Składowe pomijane przy skanowaniu (nie zawierają tekstu użytkownika)
_SKIP_WORD_PARTS = frozenset({
    "word/fontTable.xml",
    "word/settings.xml",
    "word/webSettings.xml",
    "word/styles.xml",
    "word/stylesWithEffects.xml",
    "word/theme/theme1.xml",
    "word/numbering.xml",
})

# Elementy wysokiego ryzyka — ostrzegamy, jeśli są obecne
_HIGH_RISK_RE = re.compile(
    r"word/embeddings/|activeX|oleObject|/digitalSignature|vbaProject",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Story — logiczny blok tekstu (=akapit) z mapowaniem char→węzeł XML
# ---------------------------------------------------------------------------

class DocxStory:
    """
    Reprezentuje pojedynczy akapit (w:p) jako ciągłą sekwencję znakową
    z mapowaniem char offset → węzeł XML.

    mapping: lista krotek (global_start, txt_node, internal_start, internal_len)
    """

    __slots__ = ("node", "part_name", "text", "mapping")

    def __init__(self, node: etree.Element, part_name: str) -> None:
        self.node = node
        self.part_name = part_name
        self.text: str = ""
        self.mapping: List[Tuple[int, etree.Element, int, int]] = []
        self._build()

    def _build(self) -> None:
        """Łączy tekst wszystkich w:t / w:delText / w:instrText w akapicie."""
        pos = 0
        for txt_node in self.node.iter(*TEXT_TAGS):
            val = txt_node.text or ""
            if not val:
                continue
            self.mapping.append((pos, txt_node, 0, len(val)))
            self.text += val
            pos += len(val)


def extract_docx_stories(root: etree.Element, part_name: str) -> List[DocxStory]:
    """Wyodrębnia wszystkie akapity (w:p) z drzewa XML jako Story."""
    stories: List[DocxStory] = []
    for p in root.iter(f"{WNS}p"):
        story = DocxStory(p, part_name)
        if story.text.strip():
            stories.append(story)
    return stories


# ---------------------------------------------------------------------------
# Podmiana tekstu w Story (od końca, wielowęzłowa)
# ---------------------------------------------------------------------------

def _apply_replacement(story: DocxStory, f_start: int, f_end: int, marker: str) -> None:
    """
    Zastępuje zakres [f_start, f_end) w Story markerem.

    Jeśli zakres obejmuje wiele węzłów:
    - do pierwszego wpisuje prefiks + marker;
    - z kolejnych węzłów usuwa treść objętą findingiem (zostawiając tail).
    Run properties (rPr) każdego węzła pozostają nienaruszone.
    """
    involved: List[Tuple[int, etree.Element, int]] = []
    for (g_start, txt_node, _, g_len) in story.mapping:
        g_end = g_start + g_len
        if max(f_start, g_start) < min(f_end, g_end):
            involved.append((g_start, txt_node, g_len))

    if not involved:
        return

    first_g, first_node, first_len = involved[0]
    node_txt = first_node.text or ""

    prefix = node_txt[: max(0, f_start - first_g)]

    if len(involved) == 1:
        suffix = node_txt[max(0, f_end - first_g) :]
        first_node.text = prefix + marker + suffix
    else:
        first_node.text = prefix + marker
        for (g_start2, txt_node2, g_len2) in involved[1:]:
            node_txt2 = txt_node2.text or ""
            cut = max(0, f_end - g_start2)
            if cut < len(node_txt2):
                txt_node2.text = node_txt2[cut:]
            else:
                txt_node2.text = ""  # Cały tekst objęty findingiem — czyścimy, węzeł zostaje (rPr)


# ---------------------------------------------------------------------------
# Detekcja osadzonych obiektów wysokiego ryzyka
# ---------------------------------------------------------------------------

def detect_embedded_risks(part_names: List[str]) -> List[str]:
    """Zwraca listę ostrzeżeń dot. składowych, których aplikacja nie analizuje."""
    warnings: List[str] = []
    for name in part_names:
        if _HIGH_RISK_RE.search(name):
            warnings.append(
                f"Plik zawiera składową '{name}', której aplikacja nie analizuje. "
                f"Nie można potwierdzić pełnej anonimizacji."
            )
    return warnings


# ---------------------------------------------------------------------------
# Walidacja struktury DOCX
# ---------------------------------------------------------------------------

def validate_docx_structure(zf) -> None:
    """Sprawdza minimalną wymaganą strukturę pakietu DOCX."""
    names = set(zf.namelist())

    if "[Content_Types].xml" not in names:
        raise SecurityError(
            "Brak [Content_Types].xml — plik nie jest prawidłowym pakietem OOXML."
        )

    if "word/document.xml" not in names:
        raise SecurityError(
            "Brak word/document.xml — plik nie jest prawidłowym plikiem DOCX."
        )

    # Weryfikacja Content_Types — musi zawierać identyfikator wordprocessingml
    try:
        ct_raw = zf.read("[Content_Types].xml")
        if b"wordprocessingml" not in ct_raw:
            raise SecurityError(
                "Plik nie identyfikuje się jako dokument Word (wordprocessingml)."
            )
    except KeyError:
        raise SecurityError("Nie można odczytać [Content_Types].xml.")

    # Zaszyfrowane dokumenty
    if "EncryptionInfo" in names or "EncryptedPackage" in names:
        raise SecurityError(
            "Plik DOCX jest zaszyfrowany. Anonimizacja jest niemożliwa."
        )


# ---------------------------------------------------------------------------
# DocxAdapter
# ---------------------------------------------------------------------------

class DocxAdapter:
    """Adapter do analizy i anonimizacji dokumentów DOCX."""

    _TEXT_PART_PREFIXES = ("word/",)
    _META_PART_PREFIXES = ("docProps/",)

    def _get_scannable_parts(self, zf) -> List[str]:
        """Zwraca listę składowych XML do skanowania."""
        parts: List[str] = []
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            if name in _SKIP_WORD_PARTS:
                continue
            if any(name.startswith(p) for p in self._TEXT_PART_PREFIXES):
                parts.append(name)
            elif any(name.startswith(p) for p in self._META_PART_PREFIXES):
                parts.append(name)
        return parts

    # ------------------------------------------------------------------
    # Analiza
    # ------------------------------------------------------------------

    def analyze(self, docx_bytes: bytes, analyzer) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Analizuje DOCX i zwraca (findings, warnings).

        Nie tworzy nowych recognizerów — używa przekazanego DeterministicAnalyzer.
        """
        try:
            zf = open_ooxml_package(docx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Odrzucono dokument: {exc}") from exc

        validate_docx_structure(zf)

        warnings = detect_embedded_risks(zf.namelist())
        findings: List[Dict[str, Any]] = []

        for part_name in self._get_scannable_parts(zf):
            try:
                root = read_xml_part(zf, part_name)
            except SecurityError:
                continue

            if part_name.startswith("docProps/"):
                # Metadane — prosty tekst ze wszystkich węzłów
                for node in root.iter():
                    text = (node.text or "").strip()
                    if not text:
                        continue
                    results = analyzer.analyze(text)
                    for r in results:
                        raw_val = text[r.start : r.end]
                        findings.append({
                            "entity_type": r.entity_type,
                            "score": r.score,
                            "raw_value": raw_val,
                            "part": part_name,
                            "location": "metadata",
                        })
                continue

            # Akapit po akapicie w częściach word/*
            for story in extract_docx_stories(root, part_name):
                results = analyzer.analyze(story.text)
                for r in results:
                    raw_val = story.text[r.start : r.end]
                    findings.append({
                        "entity_type": r.entity_type,
                        "score": r.score,
                        "raw_value": raw_val,
                        "part": part_name,
                        "location": story.part_name,
                    })

        return findings, warnings

    # ------------------------------------------------------------------
    # Anonimizacja
    # ------------------------------------------------------------------

    def anonymize(self, docx_bytes: bytes, findings: List[Dict]) -> bytes:
        """
        Zastępuje zatwierdzone wartości markerami w pliku DOCX.
        Zwraca zmodyfikowany pakiet jako bytes.
        """
        try:
            zf = open_ooxml_package(docx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Błąd bezpieczeństwa: {exc}") from exc

        validate_docx_structure(zf)

        replacements: Dict[str, str] = {}
        for f in findings:
            raw = (f.get("raw_value") or "").strip()
            marker = (f.get("marker") or "").strip()
            if raw and marker:
                replacements[raw] = marker

        if not replacements:
            return docx_bytes

        modifications: Dict[str, bytes] = {}

        for part_name in self._get_scannable_parts(zf):
            try:
                root = read_xml_part(zf, part_name)
            except SecurityError:
                continue

            modified = False

            if part_name.startswith("docProps/"):
                for node in root.iter():
                    if node.text and node.text.strip():
                        orig = node.text
                        for raw_val, marker in replacements.items():
                            if raw_val in node.text:
                                node.text = node.text.replace(raw_val, marker)
                                modified = True
            else:
                for story in extract_docx_stories(root, part_name):
                    hits: List[Tuple[int, int, str]] = []
                    for raw_val, marker in replacements.items():
                        start = 0
                        while True:
                            idx = story.text.find(raw_val, start)
                            if idx == -1:
                                break
                            hits.append((idx, idx + len(raw_val), marker))
                            start = idx + len(raw_val)

                    if not hits:
                        continue

                    # Od końca do początku
                    hits.sort(key=lambda x: x[0], reverse=True)
                    for f_start, f_end, marker in hits:
                        _apply_replacement(story, f_start, f_end, marker)
                        modified = True

            if modified:
                xml_bytes = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
                modifications[part_name] = xml_bytes

        return rewrite_ooxml_package(docx_bytes, modifications)
