"""Serwis anonimizacji — orkiestruje analizę tekstu z dokumentów za pomocą DeterministicAnalyzer."""
import fitz
from typing import List, Dict, Any

from src.anonymization.rule_engine import DeterministicAnalyzer
from src.anonymization.marker_registry import MarkerRegistry


class AnonymizationService:
    """Centralna usługa analizy tekstu w dokumentach PDF, DOCX i XLSX."""

    @staticmethod
    def _extract_pdf_body_text(
        page: fitz.Page,
        footer_ratio: float = 0.08,
        min_band_height: float = 24.0,
        max_band_height: float = 80.0,
    ) -> str:
        """Buduje tekst analityczny PDF bez stopki, ale z naglowkiem."""

        page_rect = page.rect
        band_height = max(
            min_band_height,
            min(
                max_band_height,
                page_rect.height * footer_ratio,
            ),
        )

        bottom_cutoff = page_rect.y1 - band_height

        words = page.get_text("words", sort=True) or []
        filtered_words = [
            word for word in words
            if len(word) >= 5 and word[3] <= bottom_cutoff
        ]

        if not filtered_words:
            return ""

        lines: list[str] = []
        current_key = None
        current_words: list[str] = []

        for word in filtered_words:
            block_no = word[5]
            line_no = word[6]
            key = (block_no, line_no)

            if current_key is None:
                current_key = key
            elif key != current_key:
                if current_words:
                    lines.append(" ".join(current_words).strip())
                current_words = []
                current_key = key

            current_words.append(str(word[4]))

        if current_words:
            lines.append(" ".join(current_words).strip())

        return "\n".join(line for line in lines if line)

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

        try:
            for page_num, page in enumerate(doc):
                text = self._extract_pdf_body_text(page)
                results = self.analyzer.analyze(text)
                hits_by_value: Dict[str, List[Any]] = {}
                grouped_indexes: Dict[str, int] = {}

                for r in results:
                    raw_value = text[r.start : r.end]
                    if not raw_value:
                        continue

                    if raw_value not in hits_by_value:
                        hits_by_value[raw_value] = page.search_for(raw_value)

                    occurrence_index = grouped_indexes.get(raw_value, 0)
                    grouped_indexes[raw_value] = occurrence_index + 1

                    hit_list = hits_by_value.get(raw_value, [])
                    bbox = tuple(hit_list[occurrence_index]) if occurrence_index < len(hit_list) else None

                    all_findings.append(
                        self._make_finding(r.entity_type, raw_value, r.score, page_num, bbox)
                    )
        finally:
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
            finding = self._make_finding(
                rf["entity_type"],
                rf["raw_value"],
                rf["score"],
                page=rf.get("location", "XLSX"),
                bbox=None,
                location=rf.get("location"),
            )
            for field in (
                "xlsx_part",
                "xlsx_cell",
                "xlsx_storage",
                "xlsx_shared_index",
            ):
                if rf.get(field) is not None:
                    finding[field] = rf[field]
            all_findings.append(finding)
        return all_findings
