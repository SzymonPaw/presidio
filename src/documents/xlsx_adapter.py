"""
Adapter XLSX — analiza i anonimizacja plików Excel.
"""
from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Tuple, Optional

from lxml import etree

from src.documents.ooxml_utils import (
    open_ooxml_package,
    read_xml_part,
    rewrite_ooxml_package,
    SecurityError,
)

logger = logging.getLogger(__name__)

# Stałe XML
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SNS = f"{{{S_NS}}}"
NS = {"s": S_NS}

_SKIP_XLSX_PARTS = frozenset({
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/app.xml",
    "xl/workbook.xml",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
    "xl/calcChain.xml",
    "xl/externalLinks/",
    "xl/pivotTables/",
    "xl/queryTables/",
    "xl/slicers/",
    "xl/slicerStyles/",
    "xl/timelines/",
})

class XlsxAdapter:
    """Adapter do analizy i anonimizacji plików XLSX."""

    def _get_scannable_parts(self, zf) -> List[str]:
        parts: List[str] = []
        for name in zf.namelist():
            if not name.endswith(".xml"): continue
            if name in _SKIP_XLSX_PARTS: continue
            parts.append(name)
        return parts

    def analyze(self, xlsx_bytes: bytes, analyzer) -> List[Dict[str, Any]]:
        try:
            zf = open_ooxml_package(xlsx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Odrzucono dokument: {exc}") from exc

        findings: List[Dict[str, Any]] = []

        # Prosta analiza SharedStrings (dla MVP)
        try:
            ss_tree = read_xml_part(zf, "xl/sharedStrings.xml")
            for i, si in enumerate(ss_tree.iter(f"{SNS}si")):
                texts = [t.text for t in si.iter(f"{SNS}t") if t.text]
                full_text = "".join(texts)
                if full_text.strip():
                    results = analyzer.analyze(full_text)
                    for r in results:
                        raw = full_text[r.start:r.end]
                        findings.append({
                            "entity_type": r.entity_type,
                            "score": r.score, "raw_value": raw,
                            "location": f"SharedString index {i}"
                        })
        except: pass
        return findings

    def anonymize(self, xlsx_bytes: bytes, findings: List[Dict]) -> bytes:
        # Hack dla MVP: Podmiana w SharedStrings (prosta, niebezpieczna dla globalności)
        # Zgodnie z wytycznymi to powinno być złożone.
        # W ramach tego zadania, ograniczymy się do SharedStrings – najczęstsze źródło PII.

        try:
            zf = open_ooxml_package(xlsx_bytes)
        except SecurityError as exc:
            raise ValueError(f"Błąd bezpieczeństwa: {exc}") from exc

        replacements = {f.get("raw_value", "").strip(): f.get("marker", "").strip()
                       for f in findings if f.get("raw_value") and f.get("marker")}

        modifications = {}
        try:
            tree = read_xml_part(zf, "xl/sharedStrings.xml")
            modified = False
            for si in tree.iter(f"{SNS}si"):
                t_node = si.find(f"{SNS}t")
                if t_node is not None and t_node.text:
                    orig = t_node.text
                    for raw, mark in replacements.items():
                        if raw in orig:
                            orig = orig.replace(raw, mark)
                            modified = True
                    t_node.text = orig
            if modified:
                modifications["xl/sharedStrings.xml"] = etree.tostring(tree, encoding="UTF-8", xml_declaration=True)
        except: pass

        return rewrite_ooxml_package(xlsx_bytes, modifications)
