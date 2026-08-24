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
import html as html_lib
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


def _collect_paragraph_text(node: etree.Element) -> str:
    """Zwraca tekst akapitu z uwzględnieniem elementów w:t, w:tab, w:br."""
    chunks: List[str] = []

    def walk(current: etree.Element) -> None:
        tag = current.tag
        if tag in TEXT_TAGS:
            if current.text:
                chunks.append(current.text)
        elif tag == f"{WNS}tab":
            chunks.append("\t")
        elif tag == f"{WNS}br":
            chunks.append("\n")

        for child in current:
            walk(child)
            if child.tail:
                chunks.append(child.tail)

    walk(node)
    return "".join(chunks)


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

    def _render_inline_preview_text(
        self,
        text: str,
        findings: List[Dict[str, Any]],
        mode: str,
    ) -> str:
        """Renderuje skrawek tekstu z zamianą znalezionych wartości na znaczniki."""
        if not text:
            return ""

        normalized: Dict[str, Dict[str, Any]] = {}
        for finding in findings:
            raw = (finding.get("raw_value") or "").strip()
            if not raw:
                continue
            normalized.setdefault(raw.lower(), finding)

        if not normalized:
            return html_lib.escape(text, quote=False)

        sorted_raw_values = sorted(normalized.keys(), key=len, reverse=True)
        if not sorted_raw_values:
            return html_lib.escape(text, quote=False)

        pattern = re.compile("|".join(re.escape(raw) for raw in sorted_raw_values), re.IGNORECASE)

        parts: List[str] = []
        last_index = 0

        for match in pattern.finditer(text):
            start, end = match.span()
            if start > last_index:
                parts.append(html_lib.escape(text[last_index:start], quote=False))

            raw = match.group(0)
            finding = normalized.get(raw.lower()) or normalized.get(raw.casefold())
            if not finding:
                parts.append(html_lib.escape(raw, quote=False))
            else:
                marker = (finding.get("marker") or raw).strip() or raw
                display = marker if mode == "output" else raw
                finding_id = finding.get("id")
                attr = f' data-docx-finding-id="{html_lib.escape(str(finding_id), quote=False)}"' if finding_id is not None else ""
                css_class = "docx-hit is-output" if mode == "output" else "docx-hit"
                parts.append(
                    f'<mark class="{css_class}"{attr}>{html_lib.escape(display, quote=False)}</mark>'
                )

            last_index = end

        if last_index < len(text):
            parts.append(html_lib.escape(text[last_index:], quote=False))

        return "".join(parts)

    def _load_theme_map(self, zf) -> Dict[str, str]:
        """Wczytuje paletę kolorów z word/theme/theme1.xml, aby odtworzyć motyw Worda."""
        theme_map: Dict[str, str] = {}
        try:
            theme_root = read_xml_part(zf, "word/theme/theme1.xml")
        except SecurityError:
            return theme_map

        try:
            for node in theme_root.iter():
                if node.tag.endswith("}srgbClr"):
                    val = node.get("val")
                    if val:
                        theme_map[node.tag.rsplit("}", 1)[-1]] = f"#{val}"
            for node in theme_root.iter():
                if node.tag.endswith("}scheme"):
                    continue
        except Exception:
            pass

        if not theme_map:
            return {
                "dk1": "#000000",
                "lt1": "#ffffff",
                "dk2": "#1f1f1f",
                "lt2": "#f2f2f2",
                "accent1": "#4f81bd",
                "accent2": "#c0504d",
                "accent3": "#9bbb59",
                "accent4": "#8064a2",
                "accent5": "#4bacc6",
                "accent6": "#f79646",
                "hlink": "#0000ff",
                "folHlink": "#800080",
            }

        return theme_map

    def _theme_color(self, color_value: str | None, theme_map: Dict[str, str] | None = None) -> str | None:
        """Mapuje wartości kolorów Worda do hex, również dla tokenów z motywu."""
        if not color_value:
            return None
        value = color_value.strip().lower()
        if value in {"auto", "inherit"}:
            return None

        if theme_map and value.startswith("theme"):
            key = value.replace("theme", "")
            if key.startswith("-"):
                key = key[1:]
            if key in theme_map:
                return theme_map[key]

        if theme_map and value in theme_map:
            return theme_map[value]

        palette = {
            "black": "#000000",
            "blue": "#0000ff",
            "cyan": "#00ffff",
            "darkblue": "#00008b",
            "darkcyan": "#008b8b",
            "darkgray": "#a9a9a9",
            "darkgreen": "#006400",
            "darkmagenta": "#8b008b",
            "darkred": "#8b0000",
            "darkyellow": "#808000",
            "green": "#008000",
            "grey": "#808080",
            "lightgray": "#d3d3d3",
            "magenta": "#ff00ff",
            "red": "#ff0000",
            "white": "#ffffff",
            "yellow": "#ffff00",
        }
        if value in palette:
            return palette[value]
        if value.startswith("#") and len(value) in {4, 7}:
            return value
        if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
            return f"#{value}"
        return None

    def _get_run_style(self, run_node: etree.Element, theme_map: Dict[str, str] | None = None) -> str:
        """Zwraca style CSS dla elementu w:r z uwzględnieniem pogrubienia, kursywy, koloru, highlightu i shading."""
        rpr = run_node.find(f"{WNS}rPr")
        if rpr is None:
            return ""

        css: List[str] = []

        if rpr.find(f"{WNS}b") is not None:
            css.append("font-weight: 700")
        if rpr.find(f"{WNS}i") is not None:
            css.append("font-style: italic")
        if rpr.find(f"{WNS}u") is not None:
            css.append("text-decoration: underline")
        if rpr.find(f"{WNS}strike") is not None:
            css.append("text-decoration: line-through")

        size_node = rpr.find(f"{WNS}sz")
        if size_node is not None and size_node.get("val"):
            try:
                size_value = int(size_node.get("val")) / 2
                css.append(f"font-size: {size_value}px")
            except (TypeError, ValueError):
                pass

        color_node = rpr.find(f"{WNS}color")
        color_value = color_node.get("val") if color_node is not None else None
        mapped_color = self._theme_color(color_value, theme_map)
        if mapped_color:
            css.append(f"color: {mapped_color}")

        highlight_node = rpr.find(f"{WNS}highlight")
        if highlight_node is not None:
            highlight_val = highlight_node.get("val")
            if highlight_val:
                highlight_color = self._theme_color(highlight_val, theme_map)
                if highlight_color:
                    css.append(f"background-color: {highlight_color}")

        shd = rpr.find(f"{WNS}shd")
        if shd is not None:
            fill = shd.get("fill")
            if fill:
                resolved_fill = self._theme_color(fill, theme_map) or f"#{fill}"
                css.append(f"background-color: {resolved_fill}")

        rfonts = rpr.find(f"{WNS}rFonts")
        if rfonts is not None and rfonts.get("ascii"):
            css.append(f"font-family: '{rfonts.get('ascii')}', sans-serif")

        return "; ".join(css)

    def _render_run_preview(
        self,
        run_node: etree.Element,
        findings: List[Dict[str, Any]],
        mode: str,
        theme_map: Dict[str, str] | None = None,
    ) -> str:
        """Renderuje pojedynczą sekcję w:r Word z zachowaniem prostego formatowania."""
        parts: List[str] = []

        for child in run_node:
            tag = child.tag
            if tag in TEXT_TAGS:
                text = child.text or ""
                if text:
                    parts.append(self._render_inline_preview_text(text, findings, mode))
            elif tag == f"{WNS}tab":
                parts.append("&nbsp;&nbsp;")
            elif tag in (f"{WNS}br", f"{WNS}cr"):
                parts.append("<br>")
            elif tag == f"{WNS}sym":
                sym = child.get(f"{{{W_NS}}}char") or child.get("char") or ""
                if sym:
                    parts.append(html_lib.escape(sym, quote=False))
            if child.tail:
                parts.append(self._render_inline_preview_text(child.tail, findings, mode))

        text_html = "".join(parts)
        if not text_html:
            return ""

        style = self._get_run_style(run_node, theme_map)
        style_attr = f' style="{html_lib.escape(style, quote=False)}"' if style else ""
        return f'<span class="docx-preview-run"{style_attr}>{text_html}</span>'

    def _load_style_map(self, zf, theme_map: Dict[str, str] | None = None) -> Dict[str, Dict[str, str]]:
        """Wczytuje definicje stylów z word/styles.xml, aby lepiej odwzorować dokument Word."""
        style_map: Dict[str, Dict[str, str]] = {}
        try:
            styles_root = read_xml_part(zf, "word/styles.xml")
        except SecurityError:
            return style_map

        for style in styles_root.iterfind(f"{WNS}style"):
            style_id = style.get("styleId") or style.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}styleId")
            if not style_id:
                continue
            style_map[style_id] = {}

            p_pr = style.find(f"{WNS}pPr")
            r_pr = style.find(f"{WNS}rPr")
            if p_pr is not None:
                jc = p_pr.find(f"{WNS}jc")
                if jc is not None and jc.get("val"):
                    style_map[style_id]["text-align"] = jc.get("val")
                spacing = p_pr.find(f"{WNS}spacing")
                if spacing is not None:
                    before = spacing.get("before")
                    after = spacing.get("after")
                    if before:
                        style_map[style_id]["margin-top"] = f"{int(before) / 20}px"
                    if after:
                        style_map[style_id]["margin-bottom"] = f"{int(after) / 20}px"
                indent = p_pr.find(f"{WNS}ind")
                if indent is not None:
                    left = indent.get("left")
                    if left:
                        style_map[style_id]["padding-left"] = f"{int(left) / 20}px"
                shd = p_pr.find(f"{WNS}shd")
                if shd is not None and shd.get("fill"):
                    fill = self._theme_color(shd.get("fill"), theme_map) or f"#{shd.get('fill')}"
                    style_map[style_id]["background-color"] = fill
            if r_pr is not None:
                b = r_pr.find(f"{WNS}b")
                if b is not None:
                    style_map[style_id]["font-weight"] = "700"
                i = r_pr.find(f"{WNS}i")
                if i is not None:
                    style_map[style_id]["font-style"] = "italic"
                sz = r_pr.find(f"{WNS}sz")
                if sz is not None and sz.get("val"):
                    try:
                        style_map[style_id]["font-size"] = f"{int(sz.get('val')) / 2}px"
                    except ValueError:
                        pass
                color = r_pr.find(f"{WNS}color") if r_pr is not None else None
                if color is not None and color.get("val"):
                    mapped_color = self._theme_color(color.get("val"), theme_map)
                    if mapped_color:
                        style_map[style_id]["color"] = mapped_color
                    else:
                        style_map[style_id]["color"] = f"#{color.get('val')}"

                if r_pr.find(f"{WNS}highlight") is not None:
                    style_map[style_id]["background-color"] = "rgba(255, 255, 0, 0.35)"

            if style_id.lower() in {"title", "heading1", "heading2", "heading3"}:
                style_map[style_id]["font-family"] = "'Segoe UI', Arial, sans-serif"
                if style_id.lower() == "title":
                    style_map[style_id]["font-size"] = "22px"
                    style_map[style_id]["font-weight"] = "700"
                elif style_id.lower() == "heading1":
                    style_map[style_id]["font-size"] = "18px"
                    style_map[style_id]["font-weight"] = "700"
                elif style_id.lower() == "heading2":
                    style_map[style_id]["font-size"] = "16px"
                    style_map[style_id]["font-weight"] = "700"

        return style_map

    def _get_paragraph_css(self, paragraph: etree.Element, style_map: Dict[str, Dict[str, str]]) -> str:
        """Zwraca style CSS dla akapitu na podstawie pPr i stylu dokumentu."""
        css: Dict[str, str] = {}

        p_pr = paragraph.find(f"{WNS}pPr")
        if p_pr is not None:
            jc = p_pr.find(f"{WNS}jc")
            if jc is not None and jc.get("val"):
                css["text-align"] = jc.get("val")

            spacing = p_pr.find(f"{WNS}spacing")
            if spacing is not None:
                before = spacing.get("before")
                after = spacing.get("after")
                if before:
                    css["margin-top"] = f"{int(before) / 20}px"
                if after:
                    css["margin-bottom"] = f"{int(after) / 20}px"

            indent = p_pr.find(f"{WNS}ind")
            if indent is not None:
                left = indent.get("left")
                if left:
                    css["padding-left"] = f"{int(left) / 20}px"

        p_style = p_pr.find(f"{WNS}pStyle") if p_pr is not None else None
        if p_style is not None:
            style_id = p_style.get("val")
            if style_id and style_map.get(style_id):
                for key, value in style_map[style_id].items():
                    css.setdefault(key, value)

        if paragraph.tag == f"{WNS}p":
            if any(ch.tag == f"{WNS}r" for ch in paragraph):
                has_title = False
                for ch in paragraph:
                    if ch.tag == f"{WNS}pPr" and ch.find(f"{WNS}pStyle") is not None:
                        if ch.find(f"{WNS}pStyle").get("val", "").lower() in {"title", "heading1", "heading2", "heading3"}:
                            has_title = True
                if has_title:
                    css.setdefault("font-family", "'Segoe UI', Arial, sans-serif")

        if css:
            return "; ".join(f"{key}: {value}" for key, value in css.items())
        return ""

    def _render_paragraph_preview(
        self,
        paragraph: etree.Element,
        findings: List[Dict[str, Any]],
        mode: str,
        style_map: Dict[str, Dict[str, str]] | None = None,
        theme_map: Dict[str, str] | None = None,
    ) -> str:
        """Renderuje pojedynczy akapit Word do HTML, z zachowaniem prostego formatowania."""
        parts: List[str] = []
        style_map = style_map or {}

        for child in paragraph:
            if child.tag == f"{WNS}r":
                rendered = self._render_run_preview(child, findings, mode, theme_map)
                if rendered:
                    parts.append(rendered)
            elif child.tag == f"{WNS}hyperlink":
                link_html = "".join(
                    self._render_run_preview(r, findings, mode, theme_map)
                    for r in child.iterfind(f"{WNS}r")
                    if self._render_run_preview(r, findings, mode, theme_map)
                )
                if link_html:
                    parts.append(f'<span class="docx-preview-link">{link_html}</span>')

        if not parts:
            return ""

        paragraph_css = self._get_paragraph_css(paragraph, style_map)
        css_attr = f' style="{html_lib.escape(paragraph_css, quote=False)}"' if paragraph_css else ""
        return f'<div class="docx-preview-paragraph"{css_attr}>{"".join(parts)}</div>'

    def _render_cell_preview(
        self,
        cell: etree.Element,
        findings: List[Dict[str, Any]],
        mode: str,
        style_map: Dict[str, Dict[str, str]] | None = None,
        theme_map: Dict[str, str] | None = None,
    ) -> str:
        """Renderuje komórkę tabeli z zachowaniem kolejności bloków."""
        content: List[str] = []
        for child in cell:
            if child.tag == f"{WNS}p":
                rendered = self._render_paragraph_preview(child, findings, mode, style_map, theme_map)
                if rendered:
                    content.append(rendered)
            elif child.tag == f"{WNS}tbl":
                rendered = self._render_table_preview(child, findings, mode, style_map, theme_map)
                if rendered:
                    content.append(rendered)
        return "".join(content)

    def _render_table_preview(
        self,
        table: etree.Element,
        findings: List[Dict[str, Any]],
        mode: str,
        style_map: Dict[str, Dict[str, str]] | None = None,
        theme_map: Dict[str, str] | None = None,
    ) -> str:
        """Renderuje prostą tabelę DOCX jako HTML."""
        rows_html: List[str] = []
        for row in table.iterfind(f".//{WNS}tr"):
            cells_html: List[str] = []
            for cell in row.iterfind(f"{WNS}tc"):
                cell_content = self._render_cell_preview(cell, findings, mode, style_map, theme_map)
                cells_html.append(f'<td class="docx-preview-cell">{cell_content}</td>')
            if cells_html:
                rows_html.append(f'<tr>{"".join(cells_html)}</tr>')

        if not rows_html:
            return ""

        return '<table class="docx-preview-table">' + ''.join(rows_html) + '</table>'

    def build_preview_html(
        self,
        docx_bytes: bytes,
        findings: List[Dict[str, Any]] | None = None,
        mode: str = "detections",
    ) -> str:
        """Tworzy podgląd DOCX zbliżony do finalnego dokumentu Word, z zachowaniem prostych tabel i formatowania."""
        findings = findings or []
        try:
            zf = open_ooxml_package(docx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Odrzucono dokument: {exc}") from exc

        validate_docx_structure(zf)

        try:
            root = read_xml_part(zf, "word/document.xml")
        except SecurityError:
            return "<div class=\"docx-preview-empty\">Nie udało się odczytać treści dokumentu Word.</div>"

        body = root.find(f"{WNS}body")
        if body is None:
            return "<div class=\"docx-preview-empty\">Dokument Word nie zawiera widocznego tekstu do podglądu.</div>"

        theme_map = self._load_theme_map(zf)
        style_map = self._load_style_map(zf, theme_map)
        parts: List[str] = []
        for child in body:
            if child.tag == f"{WNS}p":
                rendered = self._render_paragraph_preview(child, findings, mode, style_map, theme_map)
                if rendered:
                    parts.append(rendered)
            elif child.tag == f"{WNS}tbl":
                rendered = self._render_table_preview(child, findings, mode, style_map, theme_map)
                if rendered:
                    parts.append(rendered)

        if not parts:
            return "<div class=\"docx-preview-empty\">Dokument Word nie zawiera widocznego tekstu do podglądu.</div>"

        return "<div class=\"docx-preview-document\">" + "".join(parts) + "</div>"

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
