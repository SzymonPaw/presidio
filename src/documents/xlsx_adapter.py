"""
Adapter XLSX - analiza i anonimizacja plikow Excel.
"""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

from src.documents.ooxml_utils import (
    open_ooxml_package,
    read_xml_part,
    rewrite_ooxml_package,
    SecurityError,
)


logger = logging.getLogger(__name__)


# ============================================================
# Namespace SpreadsheetML
# ============================================================

S_NS = (
    "http://schemas.openxmlformats.org/"
    "spreadsheetml/2006/main"
)

SNS = f"{{{S_NS}}}"

XML_SPACE = (
    "{http://www.w3.org/XML/1998/namespace}space"
)


class XlsxAdapter:
    """
    Adapter XLSX.

    Obsluguje tekst przechowywany jako:
    - inlineStr,
    - sharedStrings,
    - zwykly string,
    - wartosc liczbowa bez formuly.

    Analizowane sa wszystkie worksheet XML,
    takze arkusze hidden i veryHidden.
    """

    # ========================================================
    # Lista arkuszy
    # ========================================================

    @staticmethod
    def _worksheet_parts(zf) -> List[str]:
        """
        Zwraca wszystkie czesci worksheet.

        Celowo nie sprawdzamy tutaj visible/hidden/veryHidden.
        Ukryty arkusz nadal moze zawierac PII i musi byc
        analizowany.
        """

        return sorted(
            name
            for name in zf.namelist()
            if (
                name.startswith("xl/worksheets/sheet")
                and name.endswith(".xml")
            )
        )

    # ========================================================
    # Shared Strings
    # ========================================================

    @staticmethod
    def _load_shared_strings(
        zf,
    ) -> Tuple[Optional[etree._Element], List[str]]:
        """
        Laduje sharedStrings.xml.

        Zwraca:
        - drzewo XML albo None,
        - liste tekstowych wartosci.
        """

        part_name = "xl/sharedStrings.xml"

        if part_name not in zf.namelist():
            return None, []

        tree = read_xml_part(
            zf,
            part_name,
        )

        values: List[str] = []

        for si in tree.iter(f"{SNS}si"):
            full_text = "".join(
                node.text or ""
                for node in si.iter(f"{SNS}t")
            )

            values.append(full_text)

        return tree, values

    # ========================================================
    # Odczyt tekstu komorki
    # ========================================================

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

        storage_type:
            inlineStr
            sharedString
            string
            number
            formula
            unsupported
        """

        cell_type = cell.get("t")

        # ----------------------------------------------------
        # INLINE STRING
        #
        # <c r="A1" t="inlineStr">
        #   <is>
        #     <t>Filip Tarczyński</t>
        #   </is>
        # </c>
        #
        # Moze tez zawierac rich text:
        #
        # <is>
        #   <r><t>Filip </t></r>
        #   <r><t>Tarczyński</t></r>
        # </is>
        # ----------------------------------------------------

        if cell_type == "inlineStr":
            full_text = "".join(
                node.text or ""
                for node in cell.iter(f"{SNS}t")
            )

            return (
                full_text,
                "inlineStr",
                None,
            )

        # ----------------------------------------------------
        # SHARED STRING
        #
        # <c r="A1" t="s">
        #   <v>0</v>
        # </c>
        # ----------------------------------------------------

        if cell_type == "s":
            value_node = cell.find(
                f"{SNS}v"
            )

            if (
                value_node is None
                or value_node.text is None
            ):
                return (
                    "",
                    "sharedString",
                    None,
                )

            try:
                index = int(
                    value_node.text
                )
            except ValueError:
                return (
                    "",
                    "sharedString",
                    None,
                )

            if not (
                0 <= index < len(shared_values)
            ):
                return (
                    "",
                    "sharedString",
                    index,
                )

            return (
                shared_values[index],
                "sharedString",
                index,
            )

        # ----------------------------------------------------
        # STRING
        #
        # Nie ruszamy cached result formuly.
        # ----------------------------------------------------

        if cell_type == "str":
            formula = cell.find(
                f"{SNS}f"
            )

            if formula is not None:
                return (
                    "",
                    "formula",
                    None,
                )

            value_node = cell.find(
                f"{SNS}v"
            )

            text = (
                value_node.text
                if (
                    value_node is not None
                    and value_node.text is not None
                )
                else ""
            )

            return (
                text,
                "string",
                None,
            )

        # ----------------------------------------------------
        # LICZBA / BRAK TYPE
        #
        # Pozwala np. wykryc PESEL wpisany jako liczba.
        #
        # Formul nie analizujemy jako zwyklej wartosci.
        # ----------------------------------------------------

        if cell_type in (None, "n"):
            formula = cell.find(
                f"{SNS}f"
            )

            if formula is not None:
                return (
                    "",
                    "formula",
                    None,
                )

            value_node = cell.find(
                f"{SNS}v"
            )

            text = (
                value_node.text
                if (
                    value_node is not None
                    and value_node.text is not None
                )
                else ""
            )

            return (
                text,
                "number",
                None,
            )

        return (
            "",
            "unsupported",
            None,
        )

    # ========================================================
    # ANALIZA
    # ========================================================

    def analyze(
        self,
        xlsx_bytes: bytes,
        analyzer,
    ) -> List[Dict[str, Any]]:
        """
        Analizuje tekst komorek we wszystkich arkuszach.

        Nie tworzymy zadnych nowych regexow.
        Wszystkie wartosci sa przekazywane do istniejacego
        DeterministicAnalyzer.
        """

        try:
            zf = open_ooxml_package(
                xlsx_bytes
            )
        except SecurityError as exc:
            raise ValueError(
                f"Odrzucono dokument: {exc}"
            ) from exc

        findings: List[Dict[str, Any]] = []

        (
            _shared_tree,
            shared_values,
        ) = self._load_shared_strings(zf)

        for part_name in self._worksheet_parts(
            zf
        ):
            try:
                tree = read_xml_part(
                    zf,
                    part_name,
                )
            except Exception as exc:
                raise ValueError(
                    "Nie udalo sie odczytac "
                    f"arkusza {part_name}"
                ) from exc

            for cell in tree.iter(
                f"{SNS}c"
            ):
                (
                    full_text,
                    storage,
                    shared_index,
                ) = self._cell_text(
                    cell,
                    shared_values,
                )

                if not full_text.strip():
                    continue

                cell_ref = (
                    cell.get("r")
                    or "?"
                )

                results = analyzer.analyze(
                    full_text
                )

                for result in results:
                    raw_value = full_text[
                        result.start:
                        result.end
                    ]

                    findings.append(
                        {
                            "entity_type":
                                result.entity_type,

                            "score":
                                result.score,

                            "raw_value":
                                raw_value,

                            # Czytelna lokalizacja.
                            #
                            # Jest tez uzywana jako fallback
                            # podczas anonimizacji.
                            "location":
                                f"{part_name}!{cell_ref}",

                            # Dodatkowe informacje techniczne.
                            "xlsx_part":
                                part_name,

                            "xlsx_cell":
                                cell_ref,

                            "xlsx_storage":
                                storage,

                            "xlsx_shared_index":
                                shared_index,
                        }
                    )

        return findings

    # ========================================================
    # Lokalizacja findingu
    # ========================================================

    @staticmethod
    def _finding_target(
        finding: Dict[str, Any],
    ) -> Tuple[
        Optional[str],
        Optional[str],
    ]:
        """
        Odczytuje worksheet i komorke.

        Najpierw korzysta z pol xlsx_part/xlsx_cell.

        Jezeli frontend ich nie zachowal,
        odtwarza je z pola location:
            xl/worksheets/sheet2.xml!B3
        """

        part_name = finding.get(
            "xlsx_part"
        )

        cell_ref = finding.get(
            "xlsx_cell"
        )

        if part_name and cell_ref:
            return (
                str(part_name),
                str(cell_ref),
            )

        location = str(
            finding.get(
                "location",
                "",
            )
        )

        if (
            location.startswith(
                "xl/worksheets/"
            )
            and "!" in location
        ):
            part_name, cell_ref = (
                location.rsplit(
                    "!",
                    1,
                )
            )

            return (
                part_name,
                cell_ref,
            )

        return (
            None,
            None,
        )

    # ========================================================
    # Pomocnicze XML
    # ========================================================

    @staticmethod
    def _update_xml_space(node) -> None:
        """
        Ustawia xml:space=preserve,
        jesli tekst zaczyna lub konczy sie bialym znakiem.
        """

        text = node.text or ""

        if (
            text.startswith(
                (" ", "\t", "\n", "\r")
            )
            or text.endswith(
                (" ", "\t", "\n", "\r")
            )
        ):
            node.set(
                XML_SPACE,
                "preserve",
            )

        elif XML_SPACE in node.attrib:
            del node.attrib[
                XML_SPACE
            ]

    @staticmethod
    def _find_cell(
        tree,
        cell_ref: str,
    ):
        """
        Znajduje komorke po adresie np. B3.
        """

        for cell in tree.iter(
            f"{SNS}c"
        ):
            if cell.get("r") == cell_ref:
                return cell

        return None

    # ========================================================
    # Podmiana w wielu <t>
    # ========================================================

    def _replace_range_in_nodes(
        self,
        nodes,
        start: int,
        end: int,
        marker: str,
    ) -> None:
        """
        Podmienia zakres znakow rozlozony nawet na kilka
        elementow <t>.

        Marker jest wpisywany do pierwszego wezla.
        Pozostale fragmenty znajdujace sie w zakresie sa
        usuwane.
        """

        cursor = 0
        marker_written = False

        for node in nodes:
            text = node.text or ""

            node_start = cursor
            node_end = (
                cursor + len(text)
            )

            cursor = node_end

            if (
                end <= node_start
                or start >= node_end
            ):
                continue

            local_start = max(
                0,
                start - node_start,
            )

            local_end = min(
                len(text),
                end - node_start,
            )

            before = text[
                :local_start
            ]

            after = text[
                local_end:
            ]

            if not marker_written:
                node.text = (
                    before
                    + marker
                    + after
                )

                marker_written = True

            else:
                node.text = (
                    before
                    + after
                )

            self._update_xml_space(
                node
            )

    def _replace_in_text_nodes(
        self,
        nodes,
        replacements: List[
            Tuple[str, str]
        ],
    ) -> bool:
        """
        Podmienia raw_value -> marker.

        Obsluguje rowniez sytuacje, gdy tekst jest
        rozbity na kilka rich-text runow.
        """

        modified = False

        for raw_value, marker in replacements:
            if (
                not raw_value
                or not marker
                or raw_value == marker
            ):
                continue

            full_text = "".join(
                node.text or ""
                for node in nodes
            )

            positions: List[int] = []

            cursor = 0

            while True:
                index = full_text.find(
                    raw_value,
                    cursor,
                )

                if index < 0:
                    break

                positions.append(
                    index
                )

                cursor = (
                    index
                    + len(raw_value)
                )

            # Od konca do poczatku,
            # aby offsety wczesniejszych trafien
            # pozostaly prawidlowe.
            for index in reversed(
                positions
            ):
                self._replace_range_in_nodes(
                    nodes,
                    index,
                    index + len(raw_value),
                    marker,
                )

                modified = True

        return modified

    # ========================================================
    # Konwersja zwyklej wartosci na inlineStr
    # ========================================================

    def _set_inline_string(
        self,
        cell,
        text: str,
    ) -> None:
        """
        Ustawia wynik anonimizacji jako inlineStr.

        Zachowuje atrybuty komorki, np. styl.
        """

        for child in list(cell):
            if child.tag in {
                f"{SNS}v",
                f"{SNS}is",
            }:
                cell.remove(child)

        cell.set(
            "t",
            "inlineStr",
        )

        inline = etree.SubElement(
            cell,
            f"{SNS}is",
        )

        text_node = etree.SubElement(
            inline,
            f"{SNS}t",
        )

        text_node.text = text

        self._update_xml_space(
            text_node
        )

    # ========================================================
    # ANONIMIZACJA
    # ========================================================

    def anonymize(
        self,
        xlsx_bytes: bytes,
        findings: List[Dict],
    ) -> bytes:
        """
        Anonimizuje zatwierdzone findings.

        Kluczowe zasady:

        1. inlineStr jest zmieniany tylko w konkretnej komorce.
        2. sharedString jest KLONOWANY przed modyfikacja.
        3. Nie zmieniamy oryginalnego shared string globalnie.
        4. Formuly sa pozostawiane bez zmian.
        """

        try:
            zf = open_ooxml_package(
                xlsx_bytes
            )
        except SecurityError as exc:
            raise ValueError(
                "Blad bezpieczenstwa: "
                f"{exc}"
            ) from exc

        # ----------------------------------------------------
        # Grupujemy findingi wedlug konkretnej komorki.
        # ----------------------------------------------------

                grouped: Dict[
            Tuple[str, str],
            List[Tuple[str, str]],
        ] = {}

        def add_finding_target(
            finding: Dict[str, Any],
        ) -> None:
            """
            Dodaje jedno konkretne wystąpienie findingu
            do listy komórek przeznaczonych do anonimizacji.
            """

            raw_value = str(
                finding.get(
                    "raw_value",
                    "",
                )
            )

            marker = str(
                finding.get(
                    "marker",
                    "",
                )
            )

            if (
                not raw_value
                or not marker
            ):
                return

            (
                part_name,
                cell_ref,
            ) = self._finding_target(
                finding
            )

            if (
                not part_name
                or not cell_ref
            ):
                logger.warning(
                    "Finding XLSX bez lokalizacji: %s",
                    finding.get(
                        "entity_type",
                        "?",
                    ),
                )
                return

            grouped.setdefault(
                (
                    part_name,
                    cell_ref,
                ),
                [],
            ).append(
                (
                    raw_value,
                    marker,
                )
            )

        # ----------------------------------------------------
        # Findings widoczne w UI są grupowane po:
        #
        #   entity_type + raw_value
        #
        # Jeden wiersz może więc odpowiadać kilku komórkom.
        #
        # app_factory przechowuje je w:
        #
        #   occurrences = [...]
        # ----------------------------------------------------

        for finding in findings:
            occurrences = finding.get(
                "occurrences"
            )

            if (
                isinstance(
                    occurrences,
                    list,
                )
                and occurrences
            ):
                for occurrence in occurrences:
                    if not isinstance(
                        occurrence,
                        dict,
                    ):
                        continue

                    expanded = dict(
                        finding
                    )

                    # Lokalizacja konkretnego wystąpienia
                    # nadpisuje lokalizację pierwszego findingu.
                    expanded.update(
                        occurrence
                    )

                    add_finding_target(
                        expanded
                    )

            else:
                # Kompatybilność z findingami, które nie były
                # grupowane.
                add_finding_target(
                    finding
                )

        if not grouped:
            return xlsx_bytes

        modifications: Dict[
            str,
            bytes,
        ] = {}

        worksheet_trees = {}

        changed_parts = set()

        # ----------------------------------------------------
        # SharedStrings
        # ----------------------------------------------------

        (
            shared_tree,
            _shared_values,
        ) = self._load_shared_strings(
            zf
        )

        shared_modified = False

        # ----------------------------------------------------
        # Kazda zatwierdzona komorka
        # ----------------------------------------------------

        for (
            part_name,
            cell_ref,
        ), replacements in grouped.items():

            if (
                part_name
                not in zf.namelist()
            ):
                logger.warning(
                    "Nie znaleziono arkusza XLSX: %s",
                    part_name,
                )
                continue

            if part_name not in worksheet_trees:
                worksheet_trees[
                    part_name
                ] = read_xml_part(
                    zf,
                    part_name,
                )

            tree = worksheet_trees[
                part_name
            ]

            cell = self._find_cell(
                tree,
                cell_ref,
            )

            if cell is None:
                logger.warning(
                    "Nie znaleziono komorki XLSX: %s!%s",
                    part_name,
                    cell_ref,
                )
                continue

            cell_type = cell.get("t")

            # =================================================
            # INLINE STRING
            # =================================================

            if cell_type == "inlineStr":
                text_nodes = list(
                    cell.iter(
                        f"{SNS}t"
                    )
                )

                if self._replace_in_text_nodes(
                    text_nodes,
                    replacements,
                ):
                    changed_parts.add(
                        part_name
                    )

                continue

            # =================================================
            # SHARED STRING
            # =================================================

            if cell_type == "s":
                if shared_tree is None:
                    logger.warning(
                        "Komorka %s!%s odwoluje sie do "
                        "sharedStrings, ale brak tabeli.",
                        part_name,
                        cell_ref,
                    )
                    continue

                value_node = cell.find(
                    f"{SNS}v"
                )

                if (
                    value_node is None
                    or value_node.text is None
                ):
                    continue

                try:
                    old_index = int(
                        value_node.text
                    )
                except ValueError:
                    continue

                shared_items = list(
                    shared_tree.iter(
                        f"{SNS}si"
                    )
                )

                if not (
                    0
                    <= old_index
                    < len(shared_items)
                ):
                    continue

                # ---------------------------------------------
                # WAŻNE:
                #
                # Nie modyfikujemy shared_items[old_index].
                #
                # Tworzymy kopie tylko dla tej konkretnej
                # komorki.
                # ---------------------------------------------

                cloned_item = deepcopy(
                    shared_items[
                        old_index
                    ]
                )

                text_nodes = list(
                    cloned_item.iter(
                        f"{SNS}t"
                    )
                )

                if not self._replace_in_text_nodes(
                    text_nodes,
                    replacements,
                ):
                    continue

                shared_tree.append(
                    cloned_item
                )

                new_index = len(
                    shared_items
                )

                value_node.text = str(
                    new_index
                )

                # uniqueCount jest opcjonalne.
                if (
                    shared_tree.get(
                        "uniqueCount"
                    )
                    is not None
                ):
                    shared_tree.set(
                        "uniqueCount",
                        str(
                            new_index + 1
                        ),
                    )

                shared_modified = True

                changed_parts.add(
                    part_name
                )

                continue

            # =================================================
            # STRING / NUMBER
            # =================================================

            if (
                cell_type == "str"
                or cell_type in (
                    None,
                    "n",
                )
            ):
                # Nie modyfikujemy formul.
                if cell.find(
                    f"{SNS}f"
                ) is not None:
                    logger.warning(
                        "Pominieto formule w %s!%s",
                        part_name,
                        cell_ref,
                    )
                    continue

                value_node = cell.find(
                    f"{SNS}v"
                )

                old_text = (
                    value_node.text
                    if (
                        value_node is not None
                        and value_node.text is not None
                    )
                    else ""
                )

                new_text = old_text

                for (
                    raw_value,
                    marker,
                ) in replacements:
                    new_text = (
                        new_text.replace(
                            raw_value,
                            marker,
                        )
                    )

                if new_text != old_text:
                    self._set_inline_string(
                        cell,
                        new_text,
                    )

                    changed_parts.add(
                        part_name
                    )

                continue

        # ----------------------------------------------------
        # Serializacja tylko faktycznie zmienionych arkuszy.
        # ----------------------------------------------------

        for part_name in changed_parts:
            tree = worksheet_trees[
                part_name
            ]

            modifications[
                part_name
            ] = etree.tostring(
                tree,
                encoding="UTF-8",
                xml_declaration=True,
            )

        # ----------------------------------------------------
        # Shared Strings tylko gdy rzeczywiscie zmodyfikowane.
        # ----------------------------------------------------

        if (
            shared_modified
            and shared_tree is not None
        ):
            modifications[
                "xl/sharedStrings.xml"
            ] = etree.tostring(
                shared_tree,
                encoding="UTF-8",
                xml_declaration=True,
            )

        return rewrite_ooxml_package(
            xlsx_bytes,
            modifications,
        )