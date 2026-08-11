from pathlib import Path

import fitz

from src.anonymization.rule_engine import (
    DeterministicAnalyzer,
    PersonDictionaryRecognizer,
)


# ------------------------------------------------------------
# UZUPELNIJ
# ------------------------------------------------------------

PDF = Path("dev.pdf")

TARGET = "Katarzyna Lelińska"

PAGE_NUMBER = 26


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------

doc = fitz.open(
    stream=PDF.read_bytes(),
    filetype="pdf",
)

page = doc[
    PAGE_NUMBER - 1
]

text = page.get_text()

pos = text.find(
    TARGET
)

if pos < 0:
    raise SystemExit(
        f"Nie znaleziono TARGET w tekscie: {TARGET!r}"
    )

target_start = pos
target_end = (
    pos + len(TARGET)
)


print("=" * 80)
print("TARGET")
print("=" * 80)

print(
    "TARGET:",
    repr(TARGET),
)

print(
    "START:",
    target_start,
)

print(
    "END:",
    target_end,
)


# ------------------------------------------------------------
# 1. Direct PersonRecognizer
# ------------------------------------------------------------

print()
print("=" * 80)
print("1. PERSON RECOGNIZER BEZPOSREDNIO")
print("=" * 80)


person = PersonDictionaryRecognizer()

direct = person.analyze(
    text,
    ["PERSON"],
)

for result in direct:
    raw = text[
        result.start:
        result.end
    ]

    if (
        result.end > target_start
        and result.start < target_end
    ):
        print(
            result.entity_type,
            result.score,
            result.start,
            result.end,
            repr(raw),
        )


# ------------------------------------------------------------
# 2. DeterministicAnalyzer + registry
# ------------------------------------------------------------

analyzer = DeterministicAnalyzer()


print()
print("=" * 80)
print("2. ZAREJESTROWANE RECOGNIZERY")
print("=" * 80)


recognizers = getattr(
    analyzer.registry,
    "recognizers",
    [],
)

for recognizer in recognizers:
    print(
        getattr(
            recognizer,
            "name",
            recognizer.__class__.__name__,
        )
    )


person_registered = any(
    isinstance(
        recognizer,
        PersonDictionaryRecognizer,
    )
    for recognizer in recognizers
)

print()
print(
    "PersonDictionaryRecognizer zarejestrowany:",
    person_registered,
)


# ------------------------------------------------------------
# 3. Surowy wynik Presidio AnalyzerEngine
# ------------------------------------------------------------

print()
print("=" * 80)
print("3. RAW PRESIDIO RESULTS")
print("=" * 80)


raw_results = analyzer.analyzer.analyze(
    text=text,
    entities=analyzer.SUPPORTED_ENTITIES,
    language="pl",
)


overlapping_raw = []

for result in raw_results:
    if (
        result.end > target_start
        and result.start < target_end
    ):
        overlapping_raw.append(
            result
        )

        print(
            "ENTITY:",
            result.entity_type,
        )

        print(
            "SCORE :",
            result.score,
        )

        print(
            "START :",
            result.start,
        )

        print(
            "END   :",
            result.end,
        )

        print(
            "RAW   :",
            repr(
                text[
                    result.start:
                    result.end
                ]
            ),
        )

        print(
            "OVERLAP:",
            (
                max(
                    result.start,
                    target_start,
                ),
                min(
                    result.end,
                    target_end,
                ),
            ),
        )

        print()


if not overlapping_raw:
    print(
        "BRAK RAW RESULTS nachodzacych na TARGET"
    )


# ------------------------------------------------------------
# 4. Allowlist
# ------------------------------------------------------------

print()
print("=" * 80)
print("4. ALLOWLIST")
print("=" * 80)


target_normalized = (
    TARGET
    .strip()
    .lower()
)

print(
    "TARGET:",
    repr(
        target_normalized
    ),
)

print(
    "Czy caly TARGET jest w allowlist:",
    target_normalized
    in analyzer.allowlist,
)


# ------------------------------------------------------------
# 5. Reprodukcja filtrowania allowlist
# ------------------------------------------------------------

filtered = []

for result in raw_results:
    value = (
        text[
            result.start:
            result.end
        ]
        .strip()
        .lower()
    )

    if value in analyzer.allowlist:
        continue

    filtered.append(
        result
    )


print()
print("=" * 80)
print("5. PO ALLOWLIST")
print("=" * 80)


for result in filtered:
    if (
        result.end > target_start
        and result.start < target_end
    ):
        print(
            result.entity_type,
            result.score,
            result.start,
            result.end,
            repr(
                text[
                    result.start:
                    result.end
                ]
            ),
        )


# ------------------------------------------------------------
# 6. Nasz resolver overlapow
# ------------------------------------------------------------

print()
print("=" * 80)
print("6. PO _resolve_overlaps")
print("=" * 80)


sorted_results = sorted(
    filtered,
    key=lambda result: result.start,
)

resolved = analyzer._resolve_overlaps(
    sorted_results
)


target_survived = False


for result in resolved:
    if (
        result.end > target_start
        and result.start < target_end
    ):
        print(
            result.entity_type,
            result.score,
            result.start,
            result.end,
            repr(
                text[
                    result.start:
                    result.end
                ]
            ),
        )

        if (
            result.entity_type
            == "PERSON"
        ):
            target_survived = True


print()
print(
    "PERSON przetrwal pipeline:",
    target_survived,
)


# ------------------------------------------------------------
# 7. Finalne DeterministicAnalyzer.analyze()
# ------------------------------------------------------------

print()
print("=" * 80)
print("7. FINAL analyzer.analyze()")
print("=" * 80)


final_results = analyzer.analyze(
    text
)


for result in final_results:
    if (
        result.end > target_start
        and result.start < target_end
    ):
        print(
            result.entity_type,
            result.score,
            repr(
                text[
                    result.start:
                    result.end
                ]
            ),
        )


doc.close()