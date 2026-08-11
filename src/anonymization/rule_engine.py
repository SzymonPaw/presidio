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
    PatternRecognizer,
    Pattern,
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
    if not forms:
        forms = ["sp. z o.o.", "s.a.", "spółka akcyjna", "sp. k."]
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
    _PATTERN = re.compile(
        r"(?<!\d)"
        r"("
        r"\d(?:[\s\r\n-]?\d){9}"
        r")"
        r"(?!\d)"
    )

    _CONTEXT = [
        "nip",
        "n.i.p.",
        "numer identyfikacji podatkowej",
    ]

    def __init__(self):
        super().__init__(
            supported_entities=["PL_NIP"],
            supported_language="pl",
            name="NipRecognizer",
        )

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
    ):
        results = []

        for match in self._PATTERN.finditer(text):
            raw = match.group(1)

            digits = re.sub(
                r"[\s\r\n-]",
                "",
                raw,
            )

            # Musi być dokładnie 10 cyfr.
            if len(digits) != 10:
                continue

            # Niepoprawna suma kontrolna = odrzucamy.
            if not validate_nip(digits):
                continue

            has_context = _has_context_near(
                text,
                match.start(1),
                self._CONTEXT,
                window_chars=200,
            )

            # Poprawny NIP z jednoznaczną etykietą.
            if has_context:
                score = 0.99

            # Poprawny checksum, ale brak kontekstu.
            # Nie wyrzucamy go — pokazujemy do weryfikacji.
            else:
                score = 0.80

            results.append(
                RecognizerResult(
                    "PL_NIP",
                    match.start(1),
                    match.end(1),
                    score,
                )
            )

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
    _PATTERN = re.compile(
        r"(?<!\d)"
        r"("
        r"\d(?:[ \t-]?\d){9}"
        r")"
        r"(?!\d)"
    )

    _CONTEXT = [
        "krs",
        "krajowy rejestr sądowy",
        "rejestr sądowy",
        "nr krs",
        "numer krs",
    ]

    def __init__(self):
        super().__init__(
            supported_entities=["PL_KRS"],
            supported_language="pl",
            name="KrsRecognizer",
        )

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
    ):
        results = []

        for match in self._PATTERN.finditer(text):
            raw = match.group(1)

            digits = re.sub(
                r"[ \t-]",
                "",
                raw,
            )

            if len(digits) != 10:
                continue

            if validate_nip(digits):
                continue

            has_context = _has_context_near(
                text,
                match.start(1),
                self._CONTEXT,
                window_chars=300,
            )

            if has_context:
                score = 0.98

            else:
                if not digits.startswith("0"):
                    continue

                score = 0.80

            results.append(
                RecognizerResult(
                    "PL_KRS",
                    match.start(1),
                    match.end(1),
                    score,
                )
            )

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
    _PATTERN_PL = re.compile(r"\bPL[\s\r\n]*\d{2}[\s\r\n]?(?:\d{4}[\s\r\n]?){6}\b", re.IGNORECASE)
    _PATTERN_NRB = re.compile(r"\b(\d{2}[\s\r\n]?(?:\d{4}[\s\r\n]?){6})\b")
    _CONTEXT = ["rachunek", "konto", "iban", "nrb", "przelew", "nr konta", "wypłaty"]

    def __init__(self):
        super().__init__(supported_entities=["BANK_ACCOUNT"], supported_language="pl", name="IbanRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        # IBAN z PL
        for m in self._PATTERN_PL.finditer(text):
            raw = re.sub(r'[\s\r\n]', '', m.group(0)).upper()
            if validate_iban(raw):
                results.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), 1.00))
        # NRB bez PL
        for m in self._PATTERN_NRB.finditer(text):
            raw = re.sub(r'[\s\r\n]', '', m.group(1))
            if len(raw) == 26 and validate_iban(raw):
                score = 0.99 if _has_context_near(text, m.start(), self._CONTEXT, 155) else 0.60
                results.append(RecognizerResult("BANK_ACCOUNT", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 6. Recognizer Telefon
# ---------------------------------------------------------------------------
class PhoneRecognizer(EntityRecognizer):
    _PATTERN_INTL = re.compile(r"\+48[\s\r\n.-]?(?:\d[\s\r\n().-]?){9}")
    _PATTERN_LOCAL = re.compile(
        r"(?<!\d)("
        r"\d{3}[\s.-]?\d{3}[\s.-]?\d{3}"
        r"|"
        r"\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}"
        r")(?!\d)"
    )
    _CONTEXT = ["tel", "telefon", "kom.", "komórka", "kontakt", "fax", "mobile", "tel."]

    def __init__(self):
        super().__init__(supported_entities=["PHONE_NUMBER"], supported_language="pl", name="PhoneRecognizer")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN_INTL.finditer(text):
            results.append(RecognizerResult("PHONE_NUMBER", m.start(), m.end(), 0.95))
        for m in self._PATTERN_LOCAL.finditer(text):
            raw_digits = re.sub(r"[\s.-]", "", m.group(1))
            # Nie pozwalamy na false positives z NIP/REGON
            if validate_nip(raw_digits) or validate_regon(raw_digits) or validate_pesel(raw_digits):
                continue
            if _has_context_near(text, m.start(), self._CONTEXT, 120):
                results.append(RecognizerResult("PHONE_NUMBER", m.start(), m.end(), 0.85))
        return results


# ---------------------------------------------------------------------------
# 7. Recognizer Dowodów i Paszportów
# ---------------------------------------------------------------------------
class IdentityDocumentsRecognizer(EntityRecognizer):
    _PATTERN_ID = re.compile(r"(?<![A-Z0-9])([A-Z]{3}[\s\r\n]*\d{6})(?![A-Z0-9])")
    _PATTERN_PASSPORT = re.compile(r"(?<![A-Z0-9])([A-Z]{2}[\s\r\n]*\d{7})(?![A-Z0-9])")
    _CONTEXT_PASSPORT = ["paszport", "paszportu", "nr paszportu", "seria i numer"]

    def __init__(self):
        super().__init__(
            supported_entities=["PL_ID_CARD", "PL_PASSPORT"],
            supported_language="pl",
            name="IdentityDocumentsRecognizer"
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._PATTERN_ID.finditer(text):
            clean = re.sub(r"[\s\r\n]", "", m.group(1))
            if validate_id_card(clean):
                results.append(RecognizerResult("PL_ID_CARD", m.start(1), m.end(1), 0.99))
        for m in self._PATTERN_PASSPORT.finditer(text):
            if _has_context_near(text, m.start(1), self._CONTEXT_PASSPORT, 150):
                results.append(RecognizerResult("PL_PASSPORT", m.start(1), m.end(1), 0.90))
            else:
                results.append(RecognizerResult("PL_PASSPORT", m.start(1), m.end(1), 0.60))
        return results


# ---------------------------------------------------------------------------
# 8. Recognizer Tablic Rejestracyjnych
# ---------------------------------------------------------------------------
class LicensePlateRecognizer(EntityRecognizer):
    # OSTRZEJSZY WZORZEC: litery MUSZĄ być WIELKIE
    _PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z]{2,3})[ -]?([A-Z0-9]{4,5})(?![A-Z0-9])")
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
            score = 0.90 if _has_context_near(text, m.start(), self._CONTEXT, 150) else 0.60
            results.append(RecognizerResult("LICENSE_PLATE", m.start(), m.end(), score))
        return results


# ---------------------------------------------------------------------------
# 9. Recognizer Polis i Szkód (Reguły dynamiczne)
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
        for compiled_re in self.policy_rules:
            for m in compiled_re.finditer(text):
                gstart = m.start(1) if compiled_re.groups >= 1 else m.start()
                gend = m.end(1) if compiled_re.groups >= 1 else m.end()
                results.append(RecognizerResult("POLICY_NUMBER", gstart, gend, 0.90))
        for compiled_re in self.claim_rules:
            for m in compiled_re.finditer(text):
                gstart = m.start(1) if compiled_re.groups >= 1 else m.start()
                gend = m.end(1) if compiled_re.groups >= 1 else m.end()
                results.append(RecognizerResult("CLAIM_NUMBER", gstart, gend, 0.90))
        return results


# ---------------------------------------------------------------------------
# 10. Recognizer Firmy
# ---------------------------------------------------------------------------
class OrganizationRecognizer(EntityRecognizer):
    def __init__(self):
        super().__init__(supported_entities=["ORGANIZATION"], supported_language="pl", name="OrganizationRecognizer")
        self.legal_forms = _load_legal_forms()
        sorted_forms = sorted(self.legal_forms, key=len, reverse=True)
        escaped_postfix = [re.escape(f).replace(r"\ ", r"[\s\n\r]+") for f in sorted_forms]
        escaped_forms = "|".join(escaped_postfix)

        # Regex: wyłapuje formę prawną na końcu nazwy (z obsługą łamania linii)
        self._form_pattern = re.compile(
            rf"([A-ZĄĆĘŁŃÓŚŹŻ0-9_\-+&\'\"„”][A-ZĄĆĘŁŃÓŚŹŻ0-9_\-+&\'\"„”a-ząćęłńóśźż\s\r\n]{{2,100}})[\s\n\r]+({escaped_forms})",
            re.IGNORECASE | re.DOTALL,
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        for m in self._form_pattern.finditer(text):
            results.append(RecognizerResult("ORGANIZATION", m.start(), m.end(), 0.92))
        return results


# ---------------------------------------------------------------------------
# 11. Recognizer Adresu
# ---------------------------------------------------------------------------
class AddressRecognizer(EntityRecognizer):
    """
    Deterministyczny recognizer polskich adresów.

    Najpierw wykrywa:
    - ulicę / aleję / plac / osiedle z numerem,
    - kod pocztowy i miejscowość,

    a następnie łączy sąsiadujące elementy w jeden wynik ADDRESS.
    Miejscowość musi występować w lokalnym localities.txt.
    """

    _WS = r"[ \t\r\n]+"

    _PREFIX = (
        r"(?:"
        r"ul\.?"
        r"|al\.?"
        r"|aleja"
        r"|aleje"
        r"|pl\.?"
        r"|plac"
        r"|os\.?"
        r"|osiedle"
        r"|rondo"
        r"|skwer"
        r"|bulwar"
        r")"
    )

    _WORD = (
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]"
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż'’.-]*"
    )

    # Obsługuje m.in.:
    # ul. 3 Maja
    # ul. Jana Pawła II
    # al. gen. Władysława Sikorskiego
    _NUMERIC_NAME = (
        rf"(?:"
        rf"\d{{1,4}}"
        rf"(?:-[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)?"
        rf"{_WS}"
        rf")?"
    )

    _STREET_NAME = (
        rf"{_NUMERIC_NAME}"
        rf"{_WORD}"
        rf"(?:{_WS}{_WORD}){{0,7}}"
    )

    # 12, 12A, 12/4, 12A/4, 12-14
    _BUILDING = (
        r"\d{1,4}[A-Za-z]?"
        r"(?:[-/]\d{1,4}[A-Za-z]?)?"
    )

    # m. 4, mieszkanie 4, lok. 2, lokal 2
    _UNIT = (
        rf"(?:"
        rf"[ \t]*,?[ \t]*"
        rf"(?:m(?:ieszkanie)?\.?|lok(?:al)?\.?)"
        rf"{_WS}"
        rf"\d{{1,4}}[A-Za-z]?"
        rf")?"
    )

    _PATTERN_STREET = re.compile(
        rf"(?<!\w)"
        rf"(?P<street>"
        rf"{_PREFIX}"
        rf"{_WS}"
        rf"{_STREET_NAME}"
        rf"{_WS}"
        rf"{_BUILDING}"
        rf"{_UNIT}"
        rf")"
        rf"(?![\w/])",
        re.IGNORECASE,
    )

    # Kandydat może obejmować kilka słów lub wierszy,
    # ale dokładny koniec miejscowości zostanie ustalony
    # na podstawie localities.txt.
    _PATTERN_POSTAL_CANDIDATE = re.compile(
        r"(?<!\d)"
        r"(?P<postal>\d{2}-\d{3})"
        r"[ \t\r\n]+"
        r"(?P<city>"
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]"
        r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż'’ \t\r\n-]{1,79}"
        r")"
    )

    # Dozwolone znaki między ulicą a kodem pocztowym.
    _JOINER = re.compile(
        r"^[ \t\r\n,;]*"
        r"(?:"
        r"kod(?:[ \t]+pocztowy)?"
        r"[ \t]*:?[ \t]*"
        r")?"
        r"$",
        re.IGNORECASE,
    )

    _CONTEXT = [
        "adres",
        "adresem",
        "zamieszkały",
        "zamieszkania",
        "zameldowania",
        "siedziba",
        "siedziby",
        "adres korespondencyjny",
        "miejsce zdarzenia",
    ]

    def __init__(self):
        super().__init__(
            supported_entities=["ADDRESS"],
            supported_language="pl",
            name="AddressRecognizer",
        )

        # _load_simple_txt zapisuje wartości wielkimi literami.
        self.localities = _load_simple_txt("localities.txt")

    @staticmethod
    def _normalize_locality(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" ,;").upper()

    def _longest_locality_prefix(self, candidate: str) -> str | None:
        """
        Z kandydata np.:
            'Kraków\\njan'
        wybiera:
            'Kraków'

        pod warunkiem, że wartość istnieje w localities.txt.
        """
        candidate = candidate.strip()

        possible_ends = {len(candidate)}
        possible_ends.update(
            index
            for index, character in enumerate(candidate)
            if character.isspace()
        )

        for end in sorted(possible_ends, reverse=True):
            prefix = candidate[:end].strip(" ,;")

            if not prefix:
                continue

            normalized = self._normalize_locality(prefix)

            if normalized in self.localities:
                return prefix

        return None

    def _postal_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []

        for match in self._PATTERN_POSTAL_CANDIDATE.finditer(text):
            locality = self._longest_locality_prefix(
                match.group("city")
            )

            if not locality:
                continue

            start = match.start("postal")
            end = match.start("city") + len(locality)

            spans.append((start, end))

        return spans

    def _can_join(
        self,
        text: str,
        left_end: int,
        right_start: int,
    ) -> bool:
        if right_start < left_end:
            return False

        gap = text[left_end:right_start]

        # Adres może zostać podzielony przez przecinek,
        # spacje lub pojedyncze przejście do nowego wiersza.
        return (
            len(gap) <= 40
            and bool(self._JOINER.fullmatch(gap))
        )

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
    ):
        street_spans = [
            (
                match.start("street"),
                match.end("street"),
            )
            for match in self._PATTERN_STREET.finditer(text)
        ]

        postal_spans = self._postal_spans(text)

        used_streets: set[int] = set()
        used_postals: set[int] = set()

        results: List[RecognizerResult] = []

        # Najczęstszy układ:
        # ul. Testowa 1, 00-001 Warszawa
        for street_index, (
            street_start,
            street_end,
        ) in enumerate(street_spans):
            for postal_index, (
                postal_start,
                postal_end,
            ) in enumerate(postal_spans):
                if postal_index in used_postals:
                    continue

                if self._can_join(
                    text,
                    street_end,
                    postal_start,
                ):
                    results.append(
                        RecognizerResult(
                            "ADDRESS",
                            street_start,
                            postal_end,
                            0.97,
                        )
                    )

                    used_streets.add(street_index)
                    used_postals.add(postal_index)
                    break

        # Rzadziej spotykany układ:
        # 00-001 Warszawa
        # ul. Testowa 1
        for postal_index, (
            postal_start,
            postal_end,
        ) in enumerate(postal_spans):
            if postal_index in used_postals:
                continue

            for street_index, (
                street_start,
                street_end,
            ) in enumerate(street_spans):
                if street_index in used_streets:
                    continue

                if self._can_join(
                    text,
                    postal_end,
                    street_start,
                ):
                    results.append(
                        RecognizerResult(
                            "ADDRESS",
                            postal_start,
                            street_end,
                            0.97,
                        )
                    )

                    used_postals.add(postal_index)
                    used_streets.add(street_index)
                    break

        # Sama ulica z numerem.
        for index, (start, end) in enumerate(street_spans):
            if index in used_streets:
                continue

            score = (
                0.92
                if _has_context_near(
                    text,
                    start,
                    self._CONTEXT,
                    180,
                )
                else 0.78
            )

            results.append(
                RecognizerResult(
                    "ADDRESS",
                    start,
                    end,
                    score,
                )
            )

        # Sam kod pocztowy i miejscowość.
        for index, (start, end) in enumerate(postal_spans):
            if index in used_postals:
                continue

            score = (
                0.90
                if _has_context_near(
                    text,
                    start,
                    self._CONTEXT,
                    220,
                )
                else 0.82
            )

            results.append(
                RecognizerResult(
                    "ADDRESS",
                    start,
                    end,
                    score,
                )
            )

        return sorted(
            results,
            key=lambda result: result.start,
        )

# ---------------------------------------------------------------------------
# Recognizer TERYT: wojewodztwa, powiaty, gminy i miejscowosci
# ---------------------------------------------------------------------------

class TerytDictionaryRecognizer(EntityRecognizer):
    """
    Rozpoznaje jednostki terytorialne i miejscowosci
    na podstawie lokalnych slownikow TERYT.

    Zrodla:
    - voivodeships.txt -> wojewodztwa
    - counties.txt     -> powiaty
    - communes.txt     -> gminy
    - localities.txt   -> miejscowosci (SIMC)

    Wszystkie trafienia zwracane sa jako ADDRESS,
    dzieki czemu nie trzeba zmieniac MarkerRegistry,
    UI ani listy wspieranych encji.

    Recognizer jest celowo konserwatywny:
    wartosc TERYT musi stanowic samodzielna linie tekstu.

    Jest to szczegolnie przydatne w formularzach PDF,
    gdzie etykieta np. "Wojewodztwo" albo "Miejscowosc"
    moze byc obrazem, a wpisana wartosc normalnym tekstem.
    """

    def __init__(self):
        super().__init__(
            supported_entities=["ADDRESS"],
            supported_language="pl",
            name="TerytDictionaryRecognizer",
        )

        self.voivodeships = _load_simple_txt(
            "voivodeships.txt"
        )

        self.counties = _load_simple_txt(
            "counties.txt"
        )

        self.communes = _load_simple_txt(
            "communes.txt"
        )

        self.localities = _load_simple_txt(
            "localities.txt"
        )

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Normalizacja tylko do porownania ze slownikiem.

        Nie modyfikujemy oryginalnego tekstu dokumentu,
        dlatego offsety start/end pozostaja prawidlowe.
        """

        value = value.replace(
            "\u00a0",
            " ",
        )

        value = re.sub(
            r"[ \t]+",
            " ",
            value,
        )

        return value.strip().upper()

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
    ):
        results = []

        if not text:
            return results

        offset = 0

        for line in text.splitlines(
            keepends=True
        ):
            # Usuwamy tylko znaki konca linii.
            visible_line = line.rstrip(
                "\r\n"
            )

            candidate = visible_line.strip()

            if not candidate:
                offset += len(line)
                continue

            normalized = self._normalize(
                candidate
            )

            score = None

            # ------------------------------------------------
            # Wojewodztwo
            # ------------------------------------------------

            if normalized in self.voivodeships:
                score = 0.96

            # ------------------------------------------------
            # Powiat
            # ------------------------------------------------

            elif normalized in self.counties:
                score = 0.94

            # ------------------------------------------------
            # Gmina
            #
            # Obejmuje rowniez aliasy generowane przez
            # update_dictionaries.py, np.:
            #
            # M.GDANSK
            # M. GDANSK
            # ------------------------------------------------

            elif normalized in self.communes:
                score = 0.92

            # ------------------------------------------------
            # Miejscowosc / SIMC
            #
            # Najnizszy score, bo slownik miejscowosci jest
            # duzy i zawiera nazwy, ktore potencjalnie moga
            # wystapic rowniez w zwyklym tekscie.
            #
            # Wymog calej linii mocno ogranicza false-positive.
            # ------------------------------------------------

            elif normalized in self.localities:
                score = 0.82

            if score is not None:
                leading_whitespace = (
                    len(visible_line)
                    - len(
                        visible_line.lstrip()
                    )
                )

                start = (
                    offset
                    + leading_whitespace
                )

                end = (
                    start
                    + len(candidate)
                )

                results.append(
                    RecognizerResult(
                        "ADDRESS",
                        start,
                        end,
                        score,
                    )
                )

            offset += len(line)

        return results

# ---------------------------------------------------------------------------
# 12. Recognizer Email
# ---------------------------------------------------------------------------
class EmailRecognizer(EntityRecognizer):
    _PATTERN = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}")

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
    _CANDIDATE = re.compile(r"\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:[\s\r\n\-]+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+){1,3})\b")

    def __init__(self):
        super().__init__(supported_entities=["PERSON"], supported_language="pl", name="PersonDictionaryRecognizer")
        self.first_names = _load_name_set("first_names.csv")
        self.surnames = _load_name_set("surnames.csv")

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None):
        results = []
        if not self.first_names or not self.surnames:
            return results
        for m in self._CANDIDATE.finditer(text):
            parts = re.split(r"[\s\r\n\-]+", m.group(1))
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
            TerytDictionaryRecognizer(),
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

    def _resolve_overlaps(self, results: List[RecognizerResult]) -> List[RecognizerResult]:
        """Nadaje priorytety: NIP/REGON/KRS mają najwyższy, potem PESEL/ID, a na końcu Telefon/Adres/Osoba."""
        priority = {
            "PL_NIP": 100,
            "PL_REGON": 100,
            "PL_KRS": 100,

            "PL_PESEL": 95,

            "PL_ID_CARD": 90,
            "PL_PASSPORT": 90,

            "BANK_ACCOUNT": 85,
            "EMAIL_ADDRESS": 80,
            "PHONE_NUMBER": 75,

            "LICENSE_PLATE": 70,
            "POLICY_NUMBER": 70,
            "CLAIM_NUMBER": 70,
            "ADDRESS": 60,

            "ORGANIZATION": 50,
            "PERSON": 40,
        }
        sorted_res = sorted(results, key=lambda r: (priority.get(r.entity_type, 0), r.end - r.start), reverse=True)
        final = []
        for r in sorted_res:
            if not any(max(r.start, f.start) < min(r.end, f.end) for f in final):
                final.append(r)
        return sorted(final, key=lambda r: r.start)
