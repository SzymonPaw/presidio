from typing import List, Dict, Any
from src.anonymization.rule_engine import DeterministicAnalyzer
from src.anonymization.marker_registry import MarkerRegistry

class AnonymizationService:
    def __init__(self):
        self.analyzer = DeterministicAnalyzer()
        self.marker_registry = MarkerRegistry()

    def analyze_text(self, text: str) -> List[Dict[str, Any]]:
        """Zwraca liste findings w tekscie."""
        results = self.analyzer.analyze(text)
        findings = []

        for r in results:
            raw_value = text[r.start:r.end]
            marker = self.marker_registry.get_marker(r.entity_type, raw_value)

            findings.append({
                "entity_type": r.entity_type,
                "marker": marker,
                "score": r.score,
                "reason": "Reguła regex", # Uproszczenie MVP
                "start": r.start,
                "end": r.end,
                "raw_value": raw_value,
                "count": 1 # Na etapie tego pipeline liczniki zbieramy na koncu
            })
        return findings
