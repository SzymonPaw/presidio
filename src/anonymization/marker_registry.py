import yaml
from pathlib import Path
from src.settings import RECOGNIZERS_DIR

class MarkerRegistry:
    def __init__(self):
        # type -> { normalized_value : int_suffix }
        self.registry: dict[str, dict[str, int]] = {}
        # type -> current max suffix
        self.counters: dict[str, int] = {}
        self.entity_types = self._load_entity_types()

    def _load_entity_types(self) -> dict[str, str]:
        # W MVP format moze byc na sztywno, ale uzywamy entity_types.yaml
        config_path = RECOGNIZERS_DIR.parent / "entity_types.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "entity_types" in data:
                    return data["entity_types"]
        # Fallback
        return {
            "PERSON": "[OSOBA_{}]",
            "ORGANIZATION": "[FIRMA_{}]",
            "ADDRESS": "[ADRES_{}]",
            "EMAIL_ADDRESS": "[EMAIL_{}]",
            "PHONE_NUMBER": "[TELEFON_{}]",
            "PL_NIP": "[NIP_{}]",
            "PL_KRS": "[KRS_{}]",
            "PL_REGON": "[REGON_{}]",
            "PL_PESEL": "[PESEL_{}]",
            "BANK_ACCOUNT": "[RACHUNEK_{}]",
            "LICENSE_PLATE": "[REJESTRACJA_{}]",
            "PL_ID_CARD": "[DOWOD_{}]",
            "PL_PASSPORT": "[PASZPORT_{}]",
            "POLICY_NUMBER": "[POLISA_{}]",
            "CLAIM_NUMBER": "[SZKODA_{}]",
        }

    def get_marker(self, entity_type: str, raw_value: str) -> str:
        """Zwraca znacznik dla wartosci, normalizujac ja przed przypisaniem ID."""
        if entity_type not in self.registry:
            self.registry[entity_type] = {}
            self.counters[entity_type] = 0

        # Bardzo prosta normalizacja
        normalized = raw_value.strip().lower()

        if normalized not in self.registry[entity_type]:
            self.counters[entity_type] += 1
            self.registry[entity_type][normalized] = self.counters[entity_type]

        suffix = self.registry[entity_type][normalized]
        marker_template = self.entity_types.get(entity_type, f"[{entity_type}_{{}}]")
        return marker_template.format(suffix)
