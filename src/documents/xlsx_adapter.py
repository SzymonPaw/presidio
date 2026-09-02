"""
Adapter XLSX - analiza i anonimizacja plikow Excel.

Cele:
- analiza inlineStr, sharedStrings, zwyklych stringow i wartosci liczbowych,
- analiza wszystkich worksheet XML, takze hidden / veryHidden,
- uzycie istniejacego DeterministicAnalyzer (bez nowych regul PII),
- selektywna anonimizacja sharedStrings przez klonowanie wpisu,
- fallback po raw_value, gdy warstwa HTTP zgubi lokalizacje XLSX.
"""

from __future__ import annotations

from copy import deepcopy
import logging
import posixpath
import re
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

from src.documents.ooxml_utils import (
    SecurityError,
    open_ooxml_package,
    read_xml_part,
    rewrite_ooxml_package,
)

logger = logging.getLogger(__name__)

S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SNS = f"{{{S_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class XlsxAdapter:
    """Adapter XLSX korzystajacy z istniejacego silnika analizy PII."""

    @staticmethod
    def _worksheet_parts(zf) -> List[str]:
        """Zwraca wszystkie worksheet XML, bez filtrowania hidden/veryHidden."""
        return sorted(
            name
            for name in zf.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )

    @staticmethod
    def _load_shared_strings(
        zf,
    ) -> Tuple[Optional[etree._Element], List[str]]:
        part_name = "xl/sharedStrings.xml"

        if part_name not in zf.namelist():
            return None, []

        tree = read_xml_part(zf, part_name)
        values: List[str] = []

        for si in tree.iter(f"{SNS}si"):
            values.append(
                "".join(node.text or "" for node in si.iter(f"{SNS}t"))
            )

        return tree, values

    @staticmethod
    def _cell_text(
        cell,
        shared_values: List[str],
    ) -> Tuple[str, str, Optional[int]]:
        """
        Zwraca:
            text,
            storage_type,
            shared_string_index
        """
        cell_type = cell.get("t")

        # <c t="inlineStr"><is><t>...</t></is></c>
        if cell_type == "inlineStr":
            return (
                "".join(node.text or "" for node in cell.iter(f"{SNS}t")),
                "inlineStr",
                None,
            )

        # <c t="s"><v>INDEX</v></c>
        if cell_type == "s":
            value_node = cell.find(f"{SNS}v")
            if value_node is None or value_node.text is None:
                return "", "sharedString", None

            try:
                index = int(value_node.text)
            except ValueError:
                return "", "sharedString", None

            if not 0 <= index < len(shared_values):
                return "", "sharedString", index

            return shared_values[index], "sharedString", index

        # Cached string formuly pozostawiamy nietkniety.
        if cell_type == "str":
            if cell.find(f"{SNS}f") is not None:
                return "", "formula", None

            value_node = cell.find(f"{SNS}v")
            text = (
                value_node.text
                if value_node is not None and value_node.text is not None
                else ""
            )
            return text, "string", None

        # Liczby i komorki bez t=...
        if cell_type in (None, "n"):
            if cell.find(f"{SNS}f") is not None:
                return "", "formula", None

            value_node = cell.find(f"{SNS}v")
            text = (
                value_node.text
                if value_node is not None and value_node.text is not None
                else ""
            )
            return text, "number", None

        return "", "unsupported", None

    def analyze(
        self,
        xlsx_bytes: bytes,
        analyzer,
    ) -> List[Dict[str, Any]]:
        try:
            zf = open_ooxml_package(xlsx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Odrzucono dokument: {exc}") from exc

        findings: List[Dict[str, Any]] = []
        _shared_tree, shared_values = self._load_shared_strings(zf)

        # Celowo iterujemy po wszystkich sheet*.xml.
        # Nie odrzucamy arkuszy hidden i veryHidden.
        for part_name in self._worksheet_parts(zf):
            try:
                tree = read_xml_part(zf, part_name)
            except Exception as exc:
                raise ValueError(
                    f"Nie udalo sie odczytac arkusza {part_name}"
                ) from exc

            for cell in tree.iter(f"{SNS}c"):
                full_text, storage, shared_index = self._cell_text(
                    cell,
                    shared_values,
                )

                if not full_text.strip():
                    continue

                cell_ref = cell.get("r") or "?"
                results = analyzer.analyze(full_text)

                for result in results:
                    raw_value = full_text[result.start:result.end]

                    findings.append(
                        {
                            "entity_type": result.entity_type,
                            "score": result.score,
                            "raw_value": raw_value,
                            "location": f"{part_name}!{cell_ref}",
                            "xlsx_part": part_name,
                            "xlsx_cell": cell_ref,
                            "xlsx_storage": storage,
                            "xlsx_shared_index": shared_index,
                        }
                    )

        return findings

    @staticmethod
    def _finding_target(
        finding: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[str]]:
        part_name = finding.get("xlsx_part")
        cell_ref = finding.get("xlsx_cell")

        if part_name and cell_ref:
            return str(part_name), str(cell_ref)

        location = str(finding.get("location", ""))

        if location.startswith("xl/worksheets/") and "!" in location:
            part_name, cell_ref = location.rsplit("!", 1)
            return part_name, cell_ref

        return None, None

    @staticmethod
    def _update_xml_space(node) -> None:
        text = node.text or ""

        if text.startswith((" ", "\t", "\n", "\r")) or text.endswith(
            (" ", "\t", "\n", "\r")
        ):
            node.set(XML_SPACE, "preserve")
        elif XML_SPACE in node.attrib:
            del node.attrib[XML_SPACE]

    @staticmethod
    def _find_cell(tree, cell_ref: str):
        for cell in tree.iter(f"{SNS}c"):
            if cell.get("r") == cell_ref:
                return cell
        return None

    def _replace_range_in_nodes(
        self,
        nodes,
        start: int,
        end: int,
        marker: str,
    ) -> None:
        """
        Podmienia zakres znakow nawet wtedy, gdy tekst jest rozbity
        na kilka elementow <t> (rich text).
        """
        cursor = 0
        marker_written = False

        for node in nodes:
            text = node.text or ""
            node_start = cursor
            node_end = cursor + len(text)
            cursor = node_end

            if end <= node_start or start >= node_end:
                continue

            local_start = max(0, start - node_start)
            local_end = min(len(text), end - node_start)

            before = text[:local_start]
            after = text[local_end:]

            if not marker_written:
                node.text = before + marker + after
                marker_written = True
            else:
                node.text = before + after

            self._update_xml_space(node)

    def _replace_in_text_nodes(
        self,
        nodes,
        replacements: List[Tuple[str, str]],
    ) -> bool:
        """
        Podmienia wszystkie wystapienia raw_value -> marker.
        Operuje od konca tekstu do poczatku.
        """
        modified = False

        for raw_value, marker in replacements:
            if not raw_value or not marker or raw_value == marker:
                continue

            full_text = "".join(node.text or "" for node in nodes)
            positions: List[int] = []
            cursor = 0

            while True:
                index = full_text.find(raw_value, cursor)
                if index < 0:
                    break

                positions.append(index)
                cursor = index + len(raw_value)

            for index in reversed(positions):
                self._replace_range_in_nodes(
                    nodes,
                    index,
                    index + len(raw_value),
                    marker,
                )
                modified = True

        return modified

    def _set_inline_string(self, cell, text: str) -> None:
        """
        Zamienia wartosc komorki na inlineStr, zachowujac atrybuty
        komorki (np. indeks stylu).
        """
        for child in list(cell):
            if child.tag in {f"{SNS}v", f"{SNS}is"}:
                cell.remove(child)

        cell.set("t", "inlineStr")

        inline = etree.SubElement(cell, f"{SNS}is")
        text_node = etree.SubElement(inline, f"{SNS}t")
        text_node.text = text
        self._update_xml_space(text_node)

    @staticmethod
    def _append_replacement(
        grouped: Dict[Tuple[str, str], List[Tuple[str, str]]],
        part_name: str,
        cell_ref: str,
        raw_value: str,
        marker: str,
    ) -> None:
        target = (part_name, cell_ref)
        replacement = (raw_value, marker)
        values = grouped.setdefault(target, [])

        if replacement not in values:
            values.append(replacement)

    def _locate_unlocated_findings(
        self,
        zf,
        unlocated_replacements: List[Tuple[str, str]],
        grouped: Dict[Tuple[str, str], List[Tuple[str, str]]],
    ) -> int:
        """
        Fallback na wypadek, gdy app_factory / frontend zgubi pola
        xlsx_part i xlsx_cell.

        Nie uruchamia ponownie regexow. Szuka tylko raw_value, ktore
        zostaly juz wykryte i zatwierdzone przez uzytkownika.
        """
        if not unlocated_replacements:
            return 0

        _shared_tree, shared_values = self._load_shared_strings(zf)
        matches = 0

        for part_name in self._worksheet_parts(zf):
            try:
                tree = read_xml_part(zf, part_name)
            except Exception as exc:
                raise ValueError(
                    f"Nie udalo sie ponownie odczytac arkusza {part_name}"
                ) from exc

            for cell in tree.iter(f"{SNS}c"):
                cell_text, _storage, _shared_index = self._cell_text(
                    cell,
                    shared_values,
                )

                if not cell_text:
                    continue

                cell_ref = cell.get("r") or "?"

                for raw_value, marker in unlocated_replacements:
                    if raw_value not in cell_text:
                        continue

                    before = len(grouped.get((part_name, cell_ref), []))

                    self._append_replacement(
                        grouped,
                        part_name,
                        cell_ref,
                        raw_value,
                        marker,
                    )

                    after = len(grouped.get((part_name, cell_ref), []))
                    if after > before:
                        matches += 1

        return matches

    def build_preview_html(
        self,
        xlsx_bytes: bytes,
        findings: List[Dict[str, Any]] | None = None,
        mode: str = "detections",
    ) -> str:
        """Buduje HTML podglądu arkusza XLSX z zachowaniem prostych tabel i podświetleń wykryć."""
        findings = findings or []
        try:
            zf = open_ooxml_package(xlsx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Odrzucono dokument: {exc}") from exc

        try:
            workbook_tree = read_xml_part(zf, "xl/workbook.xml")
        except SecurityError:
            return '<div class="docx-preview-empty">Nie udało się odczytać treści arkusza Excel.</div>'

        rels: Dict[str, str] = {}
        try:
            rels_tree = read_xml_part(zf, "xl/_rels/workbook.xml.rels")
            for rel in rels_tree.iterfind(f"{{http://schemas.openxmlformats.org/package/2006/relationships}}Relationship"):
                rel_id = rel.get("Id")
                target = rel.get("Target")
                if rel_id and target:
                    rels[rel_id] = target
        except SecurityError:
            rels = {}

        workbook_sheets = list(workbook_tree.iter(f"{SNS}sheet"))
        sheet_labels: Dict[str, str] = {}
        ordered_sheet_paths: List[str] = []
        for sheet_index, sheet in enumerate(workbook_sheets):
            rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rels.get(rel_id)
            if target:
                target = posixpath.normpath(posixpath.join("xl", target.lstrip("/")))
                if not target.startswith("xl/"):
                    target = "xl/" + target.lstrip("/")
            else:
                target = "xl/worksheets/sheet" + str(sheet_index + 1) + ".xml"

            if target in zf.namelist():
                ordered_sheet_paths.append(target)
                sheet_labels[target] = sheet.get("name") or target.rsplit("/", 1)[-1]

        _, shared_values = self._load_shared_strings(zf)
        sheet_paths: List[str] = []
        seen_sheet_paths = set()
        for target in ordered_sheet_paths:
            if target not in seen_sheet_paths:
                sheet_paths.append(target)
                seen_sheet_paths.add(target)

        if not sheet_paths:
            fallback_sheets = sorted(
                name for name in zf.namelist()
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            )
            for candidate in fallback_sheets:
                if candidate not in seen_sheet_paths:
                    sheet_paths.append(candidate)
                    seen_sheet_paths.add(candidate)

        for index, part_name in enumerate(sheet_paths):
            if part_name not in sheet_labels:
                if index < len(workbook_sheets):
                    sheet_labels[part_name] = workbook_sheets[index].get("name") or part_name.rsplit("/", 1)[-1]
                else:
                    sheet_labels[part_name] = part_name.rsplit("/", 1)[-1]

        if not sheet_paths:
            return '<div class="docx-preview-empty">Dokument Excel nie zawiera widocznych danych do podglądu.</div>'

        finding_map: Dict[str, List[Dict[str, Any]]] = {}

        for finding in findings:
            raw_value = str(finding.get("raw_value", "")).strip()
            if not raw_value:
                continue

            # 1) If finding already has explicit xlsx_part/xlsx_cell, use it.
            part_name = finding.get("xlsx_part")
            cell_ref = finding.get("xlsx_cell")
            if part_name and cell_ref:
                key = f"{part_name}!{cell_ref}"
                finding_map.setdefault(key, []).append(finding)
                # continue to next finding (we still allow occurrences below but explicit mapping is primary)
                continue

            # 2) If backend provided per-occurrence locations, honor them.
            occurrences = finding.get("occurrences")
            if isinstance(occurrences, list) and occurrences:
                for occ in occurrences:
                    if not isinstance(occ, dict):
                        continue
                    # Merge occurrence info with finding to preserve any extra keys
                    merged = dict(finding)
                    merged.update(occ)
                    p, c = self._finding_target(merged)
                    if p and c:
                        key = f"{p}!{c}"
                        finding_map.setdefault(key, []).append(merged)
                # continue to next finding after processing occurrences
                continue

            # 3) Fallback: try to derive from location or cell-only
            key = None
            part_name = str(finding.get("xlsx_part") or "")
            cell_ref = str(finding.get("xlsx_cell") or "")
            if part_name and cell_ref:
                key = f"{part_name}!{cell_ref}"
            elif cell_ref:
                key = cell_ref
            else:
                location = str(finding.get("location", ""))
                if "!" in location:
                    part_name, cell_ref = location.rsplit("!", 1)
                    key = f"{part_name}!{cell_ref}"
                elif location:
                    key = location

            if not key:
                continue

            finding_map.setdefault(key, []).append(finding)

        sheet_panels: List[str] = []
        preview_styles = self._load_preview_styles(zf)
        for index, part_name in enumerate(sheet_paths):
            try:
                tree = read_xml_part(zf, part_name)
            except SecurityError:
                continue

            columns, row_geometry, merges = self._load_sheet_geometry(tree)
            rows: Dict[int, Dict[int, Tuple[str, int]]] = {}
            for cell in tree.iter(f"{SNS}c"):
                cell_ref = cell.get("r")
                if not cell_ref:
                    continue
                text, _storage, _shared_index = self._cell_text(cell, shared_values)
                row_index, col_index = self._cell_coord(cell_ref)
                try:
                    style_index = int(cell.get("s", "0"))
                except ValueError:
                    style_index = 0
                rows.setdefault(row_index, {})[col_index] = (text, style_index)

            if not rows:
                continue

            max_row = max(rows)
            max_col = max(max(row.items(), key=lambda item: item[0])[0] for row in rows.values()) if rows else 0
            merge_map: Dict[Tuple[int, int], Tuple[int, int]] = {}
            for start_row, start_col, end_row, end_col in merges:
                merge_map[(start_row, start_col)] = (end_row, end_col)

            table_rows: List[str] = []
            for row_index in range(1, max_row + 1):
                cells: List[str] = []
                for col_index in range(1, max_col + 1):
                    merge = merge_map.get((row_index, col_index))
                    if merge is None:
                        if any(start_row <= row_index <= end_row and start_col <= col_index <= end_col
                               for start_row, start_col, end_row, end_col in merges):
                            continue

                    text, style_index = rows.get(row_index, {}).get(col_index, ("", 0))
                    cell_ref = self._cell_reference(col_index, row_index)
                    cell_key = f"{part_name}!{cell_ref}"
                    cell_findings = finding_map.get(cell_key, finding_map.get(cell_ref, []))
                    rendered = self._render_cell_value(text, cell_findings, mode) if text else "&nbsp;"
                    geometry = dict(columns.get(col_index, {}))
                    geometry.update(row_geometry.get(row_index, {}))
                    style = preview_styles[style_index] if style_index < len(preview_styles) else ""
                    style_attr = self._preview_cell_style(style, geometry)
                    style_html = f' style="{self._escape_attr(style_attr)}"' if style_attr else ""
                    span_html = ""
                    if merge is not None:
                        end_row, end_col = merge
                        if end_col > col_index:
                            span_html += f' colspan="{end_col - col_index + 1}"'
                        if end_row > row_index:
                            span_html += f' rowspan="{end_row - row_index + 1}"'
                    cell_html = (
                        f'<td class="xlsx-preview-cell"'
                        f' data-xlsx-part="{self._escape_attr(part_name)}"'
                        f' data-xlsx-cell="{self._escape_attr(cell_ref)}"'
                        f' data-xlsx-value="{self._escape_attr(text)}"'
                        f'{style_html}{span_html}>{rendered}</td>'
                    )
                    cells.append(cell_html)
                row_style = row_geometry.get(row_index, {})
                row_hidden = ' style="display:none"' if row_style.get("hidden") else ""
                table_rows.append(f'<tr{row_hidden}>{"".join(cells)}</tr>')

            if table_rows:
                sheet_label = sheet_labels.get(part_name, f"Arkusz {index + 1}")
                is_active = ' is-active' if index == 0 else ''
                sheet_panels.append(
                    '<section class="xlsx-sheet-panel' + is_active + '" data-sheet-name="' + self._escape_attr(sheet_label) + '">'
                    + '<div class="xlsx-sheet-header">' + self._escape_text(sheet_label) + '</div>'
                    + '<table class="xlsx-preview-table"><colgroup>'
                    + ''.join(
                        f'<col style="width:{float(columns[col].get("width")) * 7}px">'
                        if columns.get(col, {}).get("width") else '<col>'
                        for col in range(1, max_col + 1)
                    )
                    + '</colgroup>' + ''.join(table_rows) + '</table>'
                    + '</section>'
                )

        if not sheet_panels:
            return '<div class="docx-preview-empty">Dokument Excel nie zawiera widocznych danych do podglądu.</div>'

        tab_buttons = []
        for index, part_name in enumerate(sheet_paths):
            label = sheet_labels.get(part_name, f"Arkusz {index + 1}")
            active = ' is-active' if index == 0 else ''
            tab_buttons.append(
                '<button type="button" class="xlsx-sheet-tab' + active + '" data-sheet-name="' + self._escape_attr(label) + '">' + self._escape_text(label) + '</button>'
            )

        return (
            '<div class="docx-preview-document xlsx-preview-container xlsx-preview-workbook">'
            + '<div class="xlsx-sheet-tabs">' + ''.join(tab_buttons) + '</div>'
            + '<div class="xlsx-sheet-panels">' + ''.join(sheet_panels) + '</div>'
            + '</div>'
        )

    @staticmethod
    def _xml_attr(element, name: str, default: str = "") -> str:
        value = element.get(name)
        return value if value is not None else default

    def _load_preview_styles(self, zf) -> List[str]:
        """Zwraca style CSS dla indeksow s komorek, bez zmiany pakietu XLSX."""
        try:
            styles = read_xml_part(zf, "xl/styles.xml")
        except (SecurityError, KeyError):
            return []

        fonts = list(styles.iter(f"{SNS}font"))
        fills = list(styles.iter(f"{SNS}fill"))
        borders = list(styles.iter(f"{SNS}border"))
        cell_xfs = styles.find(f"{SNS}cellXfs")
        if cell_xfs is None:
            return []

        def color(node) -> str:
            if node is None:
                return ""
            value = node.get("rgb") or node.get("indexed") or node.get("theme")
            if not value:
                return ""
            if len(value) == 8 and value[:2] in {"00", "FF"}:
                value = value[2:]
            return f"#{value}" if re.fullmatch(r"[0-9A-Fa-f]{6}", value) else ""

        result: List[str] = []
        for xf in cell_xfs:
            css: List[str] = []
            font_id = int(xf.get("fontId", "0"))
            fill_id = int(xf.get("fillId", "0"))
            border_id = int(xf.get("borderId", "0"))

            if font_id < len(fonts):
                font = fonts[font_id]
                if font.find(f"{SNS}b") is not None:
                    css.append("font-weight:700")
                if font.find(f"{SNS}i") is not None:
                    css.append("font-style:italic")
                size = font.find(f"{SNS}sz")
                if size is not None and size.get("val"):
                    css.append(f"font-size:{size.get('val')}pt")
                font_color = color(font.find(f"{SNS}color"))
                if font_color:
                    css.append(f"color:{font_color}")

            if fill_id < len(fills):
                pattern = fills[fill_id].find(f"{SNS}patternFill")
                if pattern is not None and pattern.get("patternType") not in (None, "none"):
                    fill_color = color(pattern.find(f"{SNS}fgColor"))
                    if fill_color:
                        css.append(f"background-color:{fill_color}")

            if border_id < len(borders):
                border = borders[border_id]
                for side_name in ("left", "right", "top", "bottom"):
                    side = border.find(f"{SNS}{side_name}")
                    if side is not None and side.get("style"):
                        side_color = color(side.find(f"{SNS}color")) or "#808080"
                        css.append(f"border-{side_name}:1px solid {side_color}")

            alignment = xf.find(f"{SNS}alignment")
            if alignment is not None:
                horizontal = alignment.get("horizontal")
                vertical = alignment.get("vertical")
                wrap = alignment.get("wrapText")
                if horizontal:
                    css.append(f"text-align:{horizontal}")
                if vertical:
                    css.append(f"vertical-align:{vertical}")
                if wrap == "1" or wrap == "true":
                    css.append("white-space:pre-wrap")

            result.append(";".join(css))
        return result

    def _load_sheet_geometry(self, tree) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], List[Tuple[int, int, int, int]]]:
        """Odczytuje wymiary kolumn/wierszy i zakresy mergeCells arkusza."""
        columns: Dict[int, Dict[str, Any]] = {}
        cols = tree.find(f"{SNS}cols")
        if cols is not None:
            for column in cols.findall(f"{SNS}col"):
                try:
                    start = int(column.get("min", "1"))
                    end = int(column.get("max", str(start)))
                except ValueError:
                    continue
                for index in range(start, end + 1):
                    columns[index] = {
                        "width": column.get("width"),
                        "hidden": column.get("hidden") in {"1", "true"},
                    }

        rows: Dict[int, Dict[str, Any]] = {}
        sheet_data = tree.find(f"{SNS}sheetData")
        if sheet_data is not None:
            for row in sheet_data.findall(f"{SNS}row"):
                try:
                    index = int(row.get("r", "0"))
                except ValueError:
                    continue
                rows[index] = {
                    "height": row.get("ht"),
                    "hidden": row.get("hidden") in {"1", "true"},
                }

        merges: List[Tuple[int, int, int, int]] = []
        merge_cells = tree.find(f"{SNS}mergeCells")
        if merge_cells is not None:
            for merge in merge_cells.findall(f"{SNS}mergeCell"):
                ref = merge.get("ref", "")
                if ":" not in ref:
                    continue
                start, end = ref.split(":", 1)
                try:
                    start_row, start_col = self._cell_coord(start)
                    end_row, end_col = self._cell_coord(end)
                except (TypeError, ValueError):
                    continue
                merges.append((start_row, start_col, end_row, end_col))
        return columns, rows, merges

    @staticmethod
    def _preview_cell_style(style: str, geometry: Dict[str, Any]) -> str:
        declarations = [item for item in (style or "").split(";") if item]
        if geometry.get("width"):
            try:
                declarations.append(f"width:{float(geometry['width']) * 7}px")
            except ValueError:
                pass
        if geometry.get("height"):
            declarations.append(f"height:{geometry['height']}pt")
        if geometry.get("hidden"):
            declarations.append("display:none")
        return ";".join(declarations)

    @staticmethod
    def _cell_coord(cell_ref: str) -> Tuple[int, int]:
        ref = cell_ref.strip()
        letters = []
        for ch in ref:
            if ch.isalpha():
                letters.append(ch)
            else:
                break
        digits = ref[len(letters):]
        col = 0
        for ch in letters:
            col = col * 26 + (ord(ch.upper()) - 64)
        return int(digits), col

    @staticmethod
    def _cell_reference(col_index: int, row_index: int) -> str:
        letters = []
        current = col_index
        while current > 0:
            current, rem = divmod(current - 1, 26)
            letters.append(chr(65 + rem))
        return "".join(reversed(letters)) + str(row_index)

    def _render_cell_value(
        self,
        text: str,
        findings: List[Dict[str, Any]],
        mode: str,
    ) -> str:
        """Renderuje pojedynczą wartość komórki z highlightem wykryć i fallbackiem do danych."""
        if not text:
            return "&nbsp;"

        normalized: Dict[str, Dict[str, Any]] = {}
        for finding in findings:
            raw = str(finding.get("raw_value") or "").strip()
            if raw:
                normalized.setdefault(raw.lower(), finding)

        if not normalized:
            return self._escape_text(text)

        pattern = re.compile("|".join(re.escape(raw) for raw in sorted(normalized.keys(), key=len, reverse=True)), re.IGNORECASE)
        parts: List[str] = []
        last = 0

        for match in pattern.finditer(text):
            start, end = match.span()
            if start > last:
                parts.append(self._escape_text(text[last:start]))
            raw = match.group(0)
            finding = normalized.get(raw.lower()) or normalized.get(raw.casefold())
            if not finding:
                parts.append(self._escape_text(raw))
            else:
                marker = str(finding.get("marker") or raw).strip() or raw
                display = marker if mode == "output" else raw
                finding_id = finding.get("id")
                manual_id = finding.get("id") if finding.get("manual") else None
                attrs = []
                if finding_id is not None:
                    attrs.append(f'data-xlsx-finding-id="{self._escape_attr(str(finding_id))}"')
                if manual_id is not None:
                    attrs.append(f'data-manual-finding-id="{self._escape_attr(str(manual_id))}"')
                extra_classes = []
                if finding.get("manual"):
                    extra_classes.append("xlsx-manual-hit")
                if mode == "output":
                    extra_classes.append("is-output")
                class_name = " ".join(["xlsx-hit"] + extra_classes)
                attrs_html = (" " + " ".join(attrs)) if attrs else ""
                parts.append(f'<mark class="{class_name}"{attrs_html}>{self._escape_text(display)}</mark>')
            last = end

        if last < len(text):
            parts.append(self._escape_text(text[last:]))

        return "".join(parts)

    @staticmethod
    def _escape_text(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _escape_attr(value: str) -> str:
        return value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    def anonymize(
        self,
        xlsx_bytes: bytes,
        findings: List[Dict],
    ) -> bytes:
        try:
            zf = open_ooxml_package(xlsx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Blad bezpieczenstwa: {exc}") from exc

        grouped: Dict[
            Tuple[str, str],
            List[Tuple[str, str]],
        ] = {}

        unlocated_replacements: List[Tuple[str, str]] = []

        # ----------------------------------------------------
        # 1. Odczyt findings przekazanych przez backend.
        # ----------------------------------------------------
        for finding in findings:
            raw_value = str(finding.get("raw_value", ""))
            marker = str(finding.get("marker", ""))

            if not raw_value or not marker:
                continue

            located = False

            # Nowa sciezka: app_factory moze przekazac wiele wystapien
            # tej samej wartosci pod occurrences.
            occurrences = finding.get("occurrences")

            if isinstance(occurrences, list) and occurrences:
                for occurrence in occurrences:
                    if not isinstance(occurrence, dict):
                        continue

                    expanded = dict(finding)
                    expanded.update(occurrence)

                    part_name, cell_ref = self._finding_target(expanded)

                    if not part_name or not cell_ref:
                        continue

                    self._append_replacement(
                        grouped,
                        part_name,
                        cell_ref,
                        raw_value,
                        marker,
                    )
                    located = True

            # Kompatybilnosc: finding moze sam miec xlsx_part/xlsx_cell.
            if not located:
                part_name, cell_ref = self._finding_target(finding)

                if part_name and cell_ref:
                    self._append_replacement(
                        grouped,
                        part_name,
                        cell_ref,
                        raw_value,
                        marker,
                    )
                    located = True

            # Fallback: backend zgubil lokalizacje.
            if not located:
                replacement = (raw_value, marker)
                if replacement not in unlocated_replacements:
                    unlocated_replacements.append(replacement)

        # ----------------------------------------------------
        # 2. Fallback - odnajdz zatwierdzone wartosci w komorkach.
        # ----------------------------------------------------
        fallback_matches = self._locate_unlocated_findings(
            zf,
            unlocated_replacements,
            grouped,
        )

        if unlocated_replacements:
            logger.warning(
                "Fallback XLSX: odnaleziono %d zlokalizowanych "
                "wystapien zatwierdzonych wartosci.",
                fallback_matches,
            )

        if not grouped:
            logger.warning(
                "Brak zlokalizowanych findings XLSX do anonimizacji."
            )
            return xlsx_bytes

        modifications: Dict[str, bytes] = {}
        worksheet_trees: Dict[str, etree._Element] = {}
        changed_parts = set()

        shared_tree, _shared_values = self._load_shared_strings(zf)
        shared_modified = False

        # ----------------------------------------------------
        # 3. Modyfikacja konkretnych komorek.
        # ----------------------------------------------------
        for (part_name, cell_ref), replacements in grouped.items():
            if part_name not in zf.namelist():
                logger.warning(
                    "Nie znaleziono arkusza XLSX: %s",
                    part_name,
                )
                continue

            if part_name not in worksheet_trees:
                worksheet_trees[part_name] = read_xml_part(
                    zf,
                    part_name,
                )

            tree = worksheet_trees[part_name]
            cell = self._find_cell(tree, cell_ref)

            if cell is None:
                logger.warning(
                    "Nie znaleziono komorki XLSX: %s!%s",
                    part_name,
                    cell_ref,
                )
                continue

            cell_type = cell.get("t")

            # ---------- inlineStr ----------
            if cell_type == "inlineStr":
                text_nodes = list(cell.iter(f"{SNS}t"))

                if self._replace_in_text_nodes(
                    text_nodes,
                    replacements,
                ):
                    changed_parts.add(part_name)

                continue

            # ---------- sharedStrings ----------
            if cell_type == "s":
                if shared_tree is None:
                    logger.warning(
                        "Komorka %s!%s odwoluje sie do sharedStrings, "
                        "ale brak xl/sharedStrings.xml.",
                        part_name,
                        cell_ref,
                    )
                    continue

                value_node = cell.find(f"{SNS}v")

                if value_node is None or value_node.text is None:
                    continue

                try:
                    old_index = int(value_node.text)
                except ValueError:
                    continue

                shared_items = list(shared_tree.iter(f"{SNS}si"))

                if not 0 <= old_index < len(shared_items):
                    continue

                # NIE zmieniamy oryginalnego shared string globalnie.
                # Tworzymy kopie tylko dla tej konkretnej komorki.
                cloned_item = deepcopy(shared_items[old_index])
                text_nodes = list(cloned_item.iter(f"{SNS}t"))

                if not self._replace_in_text_nodes(
                    text_nodes,
                    replacements,
                ):
                    continue

                shared_tree.append(cloned_item)
                new_index = len(shared_items)
                value_node.text = str(new_index)

                if shared_tree.get("uniqueCount") is not None:
                    shared_tree.set(
                        "uniqueCount",
                        str(new_index + 1),
                    )

                shared_modified = True
                changed_parts.add(part_name)
                continue

            # ---------- string / number ----------
            if cell_type == "str" or cell_type in (None, "n"):
                # Formula pozostaje bez zmian.
                if cell.find(f"{SNS}f") is not None:
                    logger.warning(
                        "Pominieto formule w %s!%s",
                        part_name,
                        cell_ref,
                    )
                    continue

                value_node = cell.find(f"{SNS}v")
                old_text = (
                    value_node.text
                    if value_node is not None and value_node.text is not None
                    else ""
                )

                new_text = old_text

                for raw_value, marker in replacements:
                    new_text = new_text.replace(raw_value, marker)

                if new_text != old_text:
                    self._set_inline_string(
                        cell,
                        new_text,
                    )
                    changed_parts.add(part_name)

                continue

        # ----------------------------------------------------
        # 4. Serializacja zmienionych czesci.
        # ----------------------------------------------------
        for part_name in changed_parts:
            modifications[part_name] = etree.tostring(
                worksheet_trees[part_name],
                encoding="UTF-8",
                xml_declaration=True,
            )

        if shared_modified and shared_tree is not None:
            modifications["xl/sharedStrings.xml"] = etree.tostring(
                shared_tree,
                encoding="UTF-8",
                xml_declaration=True,
            )

        return rewrite_ooxml_package(
            xlsx_bytes,
            modifications,
        )
