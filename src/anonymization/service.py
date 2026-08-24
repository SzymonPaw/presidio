"""Serwis anonimizacji — orkiestruje analizę tekstu z dokumentów za pomocą DeterministicAnalyzer."""
import fitz
from typing import List, Dict, Any

from src.anonymization.rule_engine import DeterministicAnalyzer
from src.anonymization.marker_registry import MarkerRegistry


class AnonymizationService:
    """Centralna usługa analizy tekstu w dokumentach PDF, DOCX i XLSX."""

    def __init__(self):
        self.analyzer = DeterministicAnalyzer()
        self.marker_registry = MarkerRegistry()

    def _make_finding(
        self,
        entity_type: str,
        raw_value: str,
        score: float,
        page: Any = None,
        bbox: Any = None,
        reason: str = "Reguła z silnika",
        part: Any = None,
        location: Any = None,
    ) -> Dict[str, Any]:
        """Tworzy ujednolicony słownik finding z automatycznym przypisaniem markera."""
        marker = self.marker_registry.get_marker(entity_type, raw_value)
        finding = {
            "entity_type": entity_type,
            "marker": marker,
            "score": score,
            "reason": reason,
            "raw_value": raw_value,
            "page": page,
            "bbox": bbox,
            "count": 1,
        }
        if part is not None:
            finding["part"] = part
        if location is not None:
            finding["location"] = location
        return finding

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def analyze_pdf(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Analizuje PDF strona po stronie."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_findings: List[Dict[str, Any]] = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            results = self.analyzer.analyze(text)

            for r in results:
                raw_value = text[r.start : r.end]
                hits = page.search_for(raw_value)
                bbox = tuple(hits[0]) if hits else None
                all_findings.append(
                    self._make_finding(r.entity_type, raw_value, r.score, page_num, bbox)
                )

        doc.close()
        return all_findings

    # ------------------------------------------------------------------
    # DOCX
    # ------------------------------------------------------------------

    def analyze_docx(self, docx_bytes: bytes) -> List[Dict[str, Any]]:
        """Analizuje DOCX — deleguje wydobycie tekstu do DocxAdapter, analizę do DeterministicAnalyzer."""
        from src.documents.docx_adapter import DocxAdapter

        adapter = DocxAdapter()
        raw_findings, warnings = adapter.analyze(docx_bytes, self.analyzer)

        all_findings: List[Dict[str, Any]] = []
        for rf in raw_findings:
            all_findings.append(
                self._make_finding(
                    rf["entity_type"],
                    rf["raw_value"],
                    rf["score"],
                    page=rf.get("part", "DOCX"),
                    bbox=rf.get("location"),
                    part=rf.get("part"),
                    location=rf.get("location"),
                )
            )
        return all_findings

    # ------------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------------

    def analyze_xlsx(self, xlsx_bytes: bytes) -> List[Dict[str, Any]]:
        """Analizuje XLSX — deleguje wydobycie tekstu do XlsxAdapter, analizę do DeterministicAnalyzer."""
        from src.documents.xlsx_adapter import XlsxAdapter

        adapter = XlsxAdapter()
        raw_findings = adapter.analyze(xlsx_bytes, self.analyzer)

        all_findings: List[Dict[str, Any]] = []
        for rf in raw_findings:
            all_findings.append(
                self._make_finding(
                    rf["entity_type"],
                    rf["raw_value"],
                    rf["score"],
                    page=rf.get("location", "XLSX"),
                    bbox=None,
                )
            )
        return all_findings
