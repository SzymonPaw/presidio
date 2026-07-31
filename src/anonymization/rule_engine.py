"""Deterministyczny silnik analizy tekstu oparty na Presidio z NoOpNlpEngine.

Wszystkie recognizery są oparte wyłącznie na:
- wyrażeniach regularnych
- sumach kontrolnych (NIP, REGON, PESEL, ID_CARD, IBAN)
- lokalnych słownikach (imiona, nazwiska, miejscowości)
- jawnych słowach kontekstowych analizowanych w oknie lines
"""
import csv
import re
from pathlib import Path
from typing import List, Set

import yaml
from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)

from src.anonymization.noop import NoOpNlpEngine
from src.anonymization.validators import (
    validate_nip,
    validate_regon,
    validate_pesel,
    validate_iban,
    validate_id_card,
)
from src.settings import RECOGNIZERS_DIR


# ---------------------------------------------------------------------------
# Pomocnicze: ładowanie konfiguracji i słowników
# ---------------------------------------------------------------------------
def _load_name_set(filename: str) -> Set[str]:
    path = RECOGNIZERS_DIR / filename
    names = set()
    if not path.exists():
        return names
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row:
                val = list(row.values())[0]
                if val:
                    names.add(val.strip().upper())
    return names


def _load_simple_txt(filename: str) -> Set[str]:
    path = RECOGNIZERS_DIR / filename
    items = set()
    if not path.exists():
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            val = line.strip()
            if val:
                items.add(val.upper())
    return items


def _load_legal_forms() -> list:
    path = RECOGNIZERS_DIR / "legal_forms.yml"
    forms = []
    if not path.exists():
        return forms
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and "legal_forms" in data:
                for entry in data["legal_forms"]:
                    for name in entry.get("names", []):
                        forms.append(name)
    except Exception:
        pass
    # Fallback
    if not forms:
        forms = ["sp. z o.o.", "s.a.", "spólka akcyjna", "spółka z o.o.", "sp. k."]
    return forms


def _load_allowlist() -> Set[str]:
    path = RECOGNIZERS_DIR / "allowlist.yml"
    allowlist = set()
    if not path.exists():
        return allowlist
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and "allowlist" in data:
                for item in data["allowlist"]:
                    if item:
                        allowlist.add(item.strip().lower())
    except Exception:
        pass
    return allowlist


def _load_custom_rules(filename: str) -> list:
    """Wczytuje reguły regex z pliku policy_numbers.yml lub claim_numbers.yml."""
    path = RECOGNIZERS_DIR / filename
    rules = []
    if not path.exists():
        return rules
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and "rules" in data:
                for rule in data["rules"]:
                    if "regex" in rule:
                        rules.append(re.compile(rule["regex"]))
    except Exception:
        pass
    return rules


# ---------------------------------------------------------------------------
# Pomocnicze: analiza kontekstu
# ---------------------------------------------------------------------------
def _has_context_near(text: str, pos: int, keywords: list, window_chars: int = 150) -> bool:
    start = max(0, pos - window_chars)
    end = min(len(text), pos + window_chars)
    snippet = text[start:end].lower()
    return any(kw.lower() in snippet for kw in keywords)


# ---------------------------------------------------------------------------
# 1. Recognizer NIP
# ---------------------------------------------------------------------------
class NipRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"\b(\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d[\s-]?\d)\b")
    _CONTEXT = ["nip", "n.i.p.", "numer identyfikacji podatkowej"]

    def __init__(self):
        super().__init__(supported_entities=["PL_NIP"], supported_language="pl", name="NipRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN.finditer(text):
            raw = m.group(1)
            digits = re.sub(r"[\s-]", "", raw)
            if len(digits) != 10 or not validate_nip(digits):
                continue
            # NIP zazwyczaj wymaga choćby minimalnego kontekstu podatkowego
            if _has_context_near(text, m.start(), self._CONTEXT, window_chars=200):
                results.append(RecognizerResult("PL_NIP", m.start(), m.end(), 0.99))
        return results


# ---------------------------------------------------------------------------
# 2. Recognizer REGON
# ---------------------------------------------------------------------------
class RegonRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"\b(\d{9}|\d{14})\b")
    _CONTEXT = ["regon", "r.e.g.o.n.", "rejestr podmiotów"]

    def __init__(self):
        super().__init__(supported_entities=["PL_REGON"], supported_language="pl", name="RegonRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN.finditer(text):
            raw = m.group(1)
            if not validate_regon(raw):
                continue
            if _has_context_near(text, m.start(), self._CONTEXT, window_chars=250):
                results.append(RecognizerResult("PL_REGON", m.start(), m.end(), 0.99))
        return results


# ---------------------------------------------------------------------------
# 3. Recognizer KRS
# ---------------------------------------------------------------------------
class KrsRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"\b(\d{10})\b")
    _CONTEXT = ["krs", "krajowy rejestr sądowy", "rejestr sądowy"]

    def __init__(self):
        super().__init__(supported_entities=["PL_KRS"], supported_language="pl", name="KrsRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN.finditer(text):
            raw = m.group(1)
            if not _has_context_near(text, m.start(), self._CONTEXT, window_chars=300):
                continue
            results.append(RecognizerResult("PL_KRS", m.start(), m.end(), 0.98))
        return results


# ---------------------------------------------------------------------------
# 4. Recognizer PESEL
# ---------------------------------------------------------------------------
class PeselRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"\b(\d{11})\b")
    _CONTEXT = ["pesel", "nr pesel", "numer pesel"]

    def __init__(self):
        super().__init__(supported_entities=["PL_PESEL"], supported_language="pl", name="PeselRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN.finditer(text):
            raw = m.group(1)
            if not validate_pesel(raw):
                continue
            score = 0.99 if _has_context_near(text, m.start(), self._CONTEXT, 150) else 0.60
            results.append(RecognizerResult("PL_PESEL", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 5. Recognizer IBAN / NRB
# ---------------------------------------------------------------------------
class IbanRecognizer(EntityRecognizer):
    _PATTERN_PL = re.compile(r"\bPL\s*\d{2}[\s]?(?:\d{4}[\s]?){6}\b", re.IGNORECASE)
    _PATTERN_NRB = re.compile(r"\b(\d{2}[\s]?(?:\d{4}[\s]?){6})\b")
    _CONTEXT = ["rachunek", "konto", "iban", "nrb", "przelew", "nr konta"]

    def __init__(self):
        super().__init__(supported_entities=["BANK_ACCOUNT"], supported_language="pl", name="IbanRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        # IBAN z PL
        for m in self._PATTERN_PL.finditer(text):
            raw = m.group(0).upper().replace(" ", "")
            if validate_iban(raw):
                results.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 1.00))
        # NRB bez PL
        for m in self._PATTERN_NRB.finditer(text):
            raw = m.group(1).replace(" ", "")
            if len(raw) == 26 and validate_iban(raw):
                score = 0.99 if _has_context_near(text, m.start(), self._CONTEXT, 155) else 0.60
                results.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 6. Recognizer Telefon
# ---------------------------------------------------------------------------
class PhoneRecognizer(EntityRecognizer):
    _PATTERN_INTL = re.compile(r"\+48[\s.-]?(?:\d[\s().-]?){9}")
    _PATTERN_LOCAL = re.compile(r"(?<!\d)(\d{3}[\s.-]?\d{3}[\s.-]?\d{3})(?!\d)")
    _CONTEXT = ["tel", "telefon", "kom.", "komórka", "kontakt", "fax", "mobile", "tel."]

    def __init__(self):
        super().__init__(supported_entities=["PHONE_NUMBER"], supported_language="pl", name="PhoneRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN_INTL.finditer(text):
            results.append(RecognizerResult("PHONE_NUMBER", m.start(), m.end(), 0.95))
        for m in self._PATTERN_LOCAL.finditer(text):
            if _has_context_near(text, m.start(), self._CONTEXT, 120):
                results.append(RecognizerResult("PHONE_NUMBER", m.start(), m.end(), 0.85))
        return results


# ---------------------------------------------------------------------------
# 7. Recognizer Dowodów i Paszportów
# ---------------------------------------------------------------------------
class IdentityDocumentsRecognizer(EntityRecognizer):
    # Dowód osobisty: 3 litery + 6 cyfr
    _PATTERN_ID = re.compile(r"(?<![A-Z0-9])([A-Z]{3}\s?\d{6})(?![A-Z0-9])", re.IGNORECASE)
    # Paszport: 2 litery + 7 cyfr
    _PATTERN_PASSPORT = re.compile(r"(?<![A-Z0-9])([A-Z]{2}\s?\d{7})(?![A-Z0-9])", re.IGNORECASE)

    _CONTEXT_ID = ["dowód", "dowodu", "tożsamości", "seria", "numer dowodu", "id card"]
    _CONTEXT_PASSPORT = ["paszport", "paszportu", "nr paszportu", "seria i numer"]

    def __init__(self):
        super().__init__(
            supported_entities=["PL_ID_CARD", "PL_PASSPORT"],
            supported_language="pl",
            name="IdentityDocumentsRecognizer"
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        # Dowód osobisty
        for m in self._PATTERN_ID.finditer(text):
            raw = m.group(1)
            clean = raw.replace(" ", "")
            if validate_id_card(clean):
                results.append(RecognizerResult("PL_ID_CARD", m.start(1), m.end(1), 0.99))
        # Paszport
        for m in self._PATTERN_PASSPORT.finditer(text):
            raw = m.group(1)
            # Paszport wymaga kontekstu, by nie było False Positives (np. kody, oznaczenia)
            if _has_context_near(text, m.start(1), self._CONTEXT_PASSPORT, 150):
                results.append(RecognizerResult("PL_PASSPORT", m.start(1), m.end(1), 0.90))
            else:
                results.append(RecognizerResult("PL_PASSPORT", m.start(1), m.end(1), 0.60))
        return results


# ---------------------------------------------------------------------------
# 8. Recognizer Tablic Rejestracyjnych
# ---------------------------------------------------------------------------
class LicensePlateRecognizer(EntityRecognizer):
    # Wzorzec ogólny tablicy: 2-3 litery + 4-5 cyfr/liter
    _PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z]{2,3})[ -]?([A-Z0-9]{4,5})(?![A-Z0-9])", re.IGNORECASE)
    _CONTEXT = ["nr rejestracyjny", "nr rej.", "rejestracja", "pojazd", "samochód", "tablica"]

    def __init__(self):
        super().__init__(supported_entities=["LICENSE_PLATE"], supported_language="pl", name="LicensePlateRecognizer")
        self.prefixes = _load_simple_txt("vehicle_prefixes.txt")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN.finditer(text):
            prefix = m.group(1).upper()
            if prefix not in self.prefixes:
                continue
            # Sprawdzenie obecności kontekstu
            score = 0.90 if _has_context_near(text, m.start(), self._CONTEXT, 150) else 0.60
            results.append(RecognizerResult("LICENSE_PLATE", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 9. Recognizer Polis i Szkód (Reguły dynamiczne z plików YML/YAML)
# ---------------------------------------------------------------------------
class PolicyClaimRecognizer(EntityRecognizer):
    def __init__(self):
        super().__init__(
            supported_entities=["POLICY_NUMBER", "CLAIM_NUMBER"],
            supported_language="pl",
            name="PolicyClaimRecognizer"
        )
        self.policy_rules = _load_custom_rules("policy_numbers.yml")
        self.claim_rules = _load_custom_rules("claim_numbers.yml")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        # Polisa
        for compiled_re in self.policy_rules:
            for m in compiled_re.finditer(text):
                # Jeśli we wzorcu jest grupa przechwytująca (szukany numer),
                # to redagujemy tylko ten numer, a nie całą etykietę.
                if compiled_re.groups >= 1:
                    results.append(RecognizerResult("POLICY_NUMBER", m.start(1), m.end(1), 0.90))
                else:
                    results.append(RecognizerResult("POLICY_NUMBER", m.start(), m.end(), 0.90))
        # Szkoda
        for compiled_re in self.claim_rules:
            for m in compiled_re.finditer(text):
                if compiled_re.groups >= 1:
                    results.append(RecognizerResult("CLAIM_NUMBER", m.start(1), m.end(1), 0.90))
                else:
                    results.append(RecognizerResult("CLAIM_NUMBER", m.start(), m.end(), 0.90))
        return results


# ---------------------------------------------------------------------------
# 10. Recognizer Firmy
# ---------------------------------------------------------------------------
class OrganizationRecognizer(EntityRecognizer):
    def __init__(self):
        super().__init__(supported_entities=["ORGANIZATION"], supported_language="pl", name="OrganizationRecognizer")
        self.legal_forms = _load_legal_forms()
        sorted_forms = sorted(self.legal_forms, key=len, reverse=True)
        # Zamieniamy zwykłą spację na \s+, aby obsłużyć złamania linii wewnątrz formy prawnej w PDF
        escaped = [re.escape(f).replace(r"\ ", r"\s+") for f in sorted_forms]
        escaped_forms = "|".join(escaped)
        self._form_pattern = re.compile(
            f"([A-ZĄĆĘŁŃÓŚŹŻ0-9_\\-+&\\'\\\"\\s]{{2,100}})\\s+({escaped_forms})",
            re.IGNORECASE,
        ) if escaped else None

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        if not self._form_pattern:
            return results
        for m in self._form_pattern.finditer(text):
            # Zwracamy caly zakres
            results.append(RecognizerResult("ORGANIZATION", m.start(), m.end(), 0.92))
        return results


# ---------------------------------------------------------------------------
# 11. Recognizer Adresu
# ---------------------------------------------------------------------------
class AddressRecognizer(EntityRecognizer):
    _PATTERN_POSTAL = re.compile(r"\b\d{2}-\d{3}\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-ząćęłńóśźż\s-]{2,30}\b")
    # Kod pocztowy + nazwa ulicy z numerem budynku
    _PATTERN_STREET_PREF = re.compile(
        r"\b(?:ul\.|al\.|plac|pl\.|os\.)\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźżA-Z0-9\s.\-,\']{2,40}\s+\d+[a-zA-Z]?(?:[/\\]\d+)?\b",
        re.IGNORECASE
    )
    # Sama nazwa + numer (bez prefiksu), ale rygorystycznie: Wielka litera, słowo, numer.
    _PATTERN_STREET_NOPREF = re.compile(
        r"\b[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźżA-Z0-9\-]+[ \t]+\d+[a-zA-Z]?(?:[/\\]\d+)?\b"
    )
    _CONTEXT = ["adres", "siedziba", "zamieszkały", "zamieszkania", "adres korespondencyjny", "miejsce", "w"]

    def __init__(self):
        super().__init__(supported_entities=["ADDRESS"], supported_language="pl", name="AddressRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        # Ulica z prefiksem
        for m in self._PATTERN_STREET_PREF.finditer(text):
            score = 0.90 if _has_context_near(text, m.start(), self._CONTEXT, 150) else 0.70
            results.append(RecognizerResult("ADDRESS", m.start(), m.end(), score))
        # Ulica bez prefiksu (ostrzejsza filtracja: MUSI być kontekst)
        for m in self._PATTERN_STREET_NOPREF.finditer(text):
            if _has_context_near(text, m.start(), self._CONTEXT, 60):
                results.append(RecognizerResult("ADDRESS", m.start(), m.end(), 0.80))
        # Kod pocztowy i miasto
        for m in self._PATTERN_POSTAL.finditer(text):
            score = 0.92 if _has_context_near(text, m.start(), self._CONTEXT, 200) else 0.70
            results.append(RecognizerResult("ADDRESS", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 12. Recognizer Email
# ---------------------------------------------------------------------------
class EmailRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![\w.-])")

    def __init__(self):
        super().__init__(supported_entities=["EMAIL_ADDRESS"], supported_language="pl", name="EmailRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        return [
            RecognizerResult("EMAIL_ADDRESS", m.start(), m.end(), 0.98)
            for m in self._PATTERN.finditer(text)
        ]


# ---------------------------------------------------------------------------
# 13. Recognizer Osób
# ---------------------------------------------------------------------------
class PersonDictionaryRecognizer(EntityRecognizer):
    _CANDIDATE = re.compile(r"\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:[ -][A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+){1,3})\b")

    def __init__(self):
        super().__init__(supported_entities=["PERSON"], supported_language="pl", name="PersonDictionaryRecognizer")
        self.first_names = _load_name_set("first_names.csv")
        self.surnames = _load_name_set("surnames.csv")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        if not self.first_names or not self.surnames:
            return results
        for m in self._CANDIDATE.finditer(text):
            parts = re.split(r"[ -]+", m.group(1))
            if parts[0].upper() not in self.first_names:
                continue
            if parts[-1].upper() not in self.surnames:
                continue
            results.append(RecognizerResult("PERSON", m.start(), m.end(), 0.70))
        return results


# ---------------------------------------------------------------------------
# Główna klasa silnika
# ---------------------------------------------------------------------------
class DeterministicAnalyzer:
    SUPPORTED_ENTITIES = [
        "PL_NIP", "PL_REGON", "PL_KRS", "PL_PESEL",
        "BANK_ACCOUNT", "PHONE_NUMBER", "EMAIL_ADDRESS",
        "ORGANIZATION", "ADDRESS", "PERSON", "PL_ID_CARD",
        "PL_PASSPORT", "LICENSE_PLATE", "POLICY_NUMBER",
        "CLAIM_NUMBER"
    ]

    def __init__(self):
        nlp_engine = NoOpNlpEngine()
        self.registry = RecognizerRegistry()
        self._register_recognizers()
        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            registry=self.registry,
            supported_languages=["pl"],
        )
        self.allowlist = _load_allowlist()

    def _register_recognizers(self):
        for rec in [
            NipRecognizer(),
            RegonRecognizer(),
            KrsRecognizer(),
            PeselRecognizer(),
            IbanRecognizer(),
            PhoneRecognizer(),
            EmailRecognizer(),
            OrganizationRecognizer(),
            AddressRecognizer(),
            PersonDictionaryRecognizer(),
            IdentityDocumentsRecognizer(),
            LicensePlateRecognizer(),
            PolicyClaimRecognizer(),
        ]:
            self.registry.add_recognizer(rec)

    def analyze(self, text: str) -> List[RecognizerResult]:
        if not text:
            return []
        results = self.analyzer.analyze(
            text=text,
            entities=self.SUPPORTED_ENTITIES,
            language="pl",
        )
        # Filtrujemy allowlist
        filtered_results = []
        for r in results:
            val = text[r.start:r.end].strip().lower()
            if val in self.allowlist:
                continue
            filtered_results.append(r)

        # Usunięcie nakładań
        resolved = self._resolve_overlaps(sorted(filtered_results, key=lambda r: r.start))
        return resolved

    @staticmethod
    def _resolve_overlaps(results: List[RecognizerResult]) -> List[RecognizerResult]:
        final = []
        for r in results:
            if not final:
                final.append(r)
                continue
            prev = final[-1]
            if r.start < prev.end:
                if r.score > prev.score or (r.score == prev.score and (r.end - r.start) > (prev.end - prev.start)):
                    final[-1] = r
            else:
                final.append(r)
        return final
