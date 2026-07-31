import fitz
from typing import List, Dict, Any
from src.anonymization.rule_engine import DeterministicAnalyzer
from src.anonymization.marker_registry import MarkerRegistry

class AnonymizationService:
    def __init__(self):
        self.analyzer = DeterministicAnalyzer()
        self.marker_registry = MarkerRegistry()

    def analyze_pdf(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Analizuje PDF strona po stronie."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_findings = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            results = self.analyzer.analyze(text)

            for r in results:
                raw_value = text[r.start:r.end]
                # Wyszukaj bbox dla tego dopasowania
                # (Proste szukanie na stronie)
                hits = page.search_for(raw_value)
                # KONSEKWENCJA BŁĘDU: konwersja Rect na krotke/liste, by JSON mógł to sparsować
                bbox = tuple(hits[0]) if hits else None

                marker = self.marker_registry.get_marker(r.entity_type, raw_value)

                all_findings.append({
                    "entity_type": r.entity_type,
                    "marker": marker,
                    "score": r.score,
                    "reason": "Reguła z silnika",
                    "raw_value": raw_value,
                    "page": page_num,
                    "bbox": bbox, # tuple: (x0, y0, x1, y1)
                    "count": 1
                })
        doc.close()
        return all_findings
