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

                #logger.warning(
                #    "Finding XLSX bez lokalizacji; "
                #    "zostanie odnaleziony ponownie po raw_value: %s",
                #    finding.get("entity_type", "?"),
                #)

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

        logger.warning(
            "Anonimizacja XLSX: zmodyfikowano %d czesci OOXML.",
            len(modifications),
        )

        return rewrite_ooxml_package(
            xlsx_bytes,
            modifications,
        )
