from typing import List, Dict, Any
from presidio_analyzer.nlp_engine import NlpEngine

class NoOpNlpEngine(NlpEngine):
    """Silnik NLP, który nie wykonuje żadnej analizy językowej."""

    def __init__(self):
        super().__init__()

    def load(self, model_name: str = None, lang_code: str = None):
        pass

    def is_loaded(self) -> bool:
        return True

    def nlp_model_name(self, lang_code: str) -> str:
        return "noop"

    def is_nlp_model_available(self, lang_code: str) -> bool:
        return True

    def get_supported_languages(self) -> List[str]:
        return ["pl"]

    def process_text(self, text: str, language: str) -> Dict[str, Any]:
        return {
            "tokens": [],
            "words": [],
            "pos": [],
            "lemmas": [],
            "entities": []
        }

    def process_batch(self, texts: List[str], language: str) -> List[Dict[str, Any]]:
        return [self.process_text(t, language) for t in texts]

    def is_punct(self, text: str, language: str) -> bool:
        return False

    def is_stopword(self, token: str, language: str) -> bool:
        return False

    def get_supported_entities(self) -> List[str]:
        return []
