from pathlib import Path
import re

import fitz

from src.anonymization.rule_engine import (
    DeterministicAnalyzer,
    PersonDictionaryRecognizer,
)


# ------------------------------------------------------------
# UZUPELNIJ TYLKO TE 3 RZECZY
# ------------------------------------------------------------

PDF = Path("dev.pdf")

TARGETS = [
    "Katarzyna Lelińska",
    "Hanna Garychowska",
    "Hanna Gary",
]


# ------------------------------------------------------------
# Pomocnicze
# ------------------------------------------------------------

def normalize(value: str) -> str:
    return (
        value
        .replace("\u00a0", " ")
        .strip()
        .upper()
    )


person = PersonDictionaryRecognizer()
analyzer = DeterministicAnalyzer()

doc = fitz.open(
    stream=PDF.read_bytes(),
    filetype="pdf",
)


print("=" * 80)
print("TEST SLOWNIKOW I SAMEGO RECOGNIZERA")
print("=" * 80)


for target in TARGETS:
    parts = target.split()

    first_name = parts[0]
    surname = parts[-1]

    print()
    print("TARGET:", repr(target))

    print(
        "Imie w first_names:",
        normalize(first_name)
        in person.first_names,
    )

    print(
        "Nazwisko w surnames:",
        normalize(surname)
        in person.surnames,
    )

    direct_results = person.analyze(
        target,
        ["PERSON"],
    )

    print(
        "PersonRecognizer bezposrednio:",
        [
            (
                target[r.start:r.end],
                r.score,
            )
            for r in direct_results
        ],
    )


for page_no, page in enumerate(
    doc,
    start=1,
):
    text_normal = page.get_text(
        "text",
        sort=False,
    )

    text_sorted = page.get_text(
        "text",
        sort=True,
    )

    combined_lower = (
        text_normal.lower()
        + "\n"
        + text_sorted.lower()
    )

    interesting = (
        "sporządzi" in combined_lower
        or "nadzór nad księgami" in combined_lower
        or any(
            target.split()[0].lower()
            in combined_lower
            for target in TARGETS
        )
    )

    if not interesting:
        continue

    print()
    print()
    print("=" * 80)
    print(f"STRONA {page_no}")
    print("=" * 80)

    # --------------------------------------------------------
    # 1. Zwykly page.get_text()
    # --------------------------------------------------------

    print()
    print("--- TEXT sort=False ---")

    for line_no, line in enumerate(
        text_normal.splitlines(),
        start=1,
    ):
        lower = line.lower()

        if (
            "sporządzi" in lower
            or "nadzór" in lower
            or any(
                target.split()[0].lower()
                in lower
                for target in TARGETS
            )
        ):
            print(
                f"LINIA {line_no}:",
                repr(line),
            )

    # --------------------------------------------------------
    # 2. sort=True
    # --------------------------------------------------------

    print()
    print("--- TEXT sort=True ---")

    for line_no, line in enumerate(
        text_sorted.splitlines(),
        start=1,
    ):
        lower = line.lower()

        if (
            "sporządzi" in lower
            or "nadzór" in lower
            or any(
                target.split()[0].lower()
                in lower
                for target in TARGETS
            )
        ):
            print(
                f"LINIA {line_no}:",
                repr(line),
            )

    # --------------------------------------------------------
    # 3. Czy pelne nazwiska w ogole istnieja w plain text?
    # --------------------------------------------------------

    print()
    print("--- TARGETY W WARSTWIE TEKSTOWEJ ---")

    for target in TARGETS:
        print()
        print("TARGET:", repr(target))

        print(
            "sort=False:",
            target in text_normal,
        )

        print(
            "sort=True :",
            target in text_sorted,
        )

        first_name = target.split()[0]

        pos = text_normal.lower().find(
            first_name.lower()
        )

        if pos >= 0:
            print(
                "Okolica sort=False:",
                repr(
                    text_normal[
                        max(0, pos - 100):
                        min(
                            len(text_normal),
                            pos + 200,
                        )
                    ]
                ),
            )

    # --------------------------------------------------------
    # 4. Co widzi analyzer na calej stronie?
    # --------------------------------------------------------

    print()
    print("--- PERSON FINDINGS NA STRONIE ---")

    results = analyzer.analyze(
        text_normal
    )

    people = [
        (
            text_normal[
                result.start:
                result.end
            ],
            result.score,
        )
        for result in results
        if result.entity_type == "PERSON"
    ]

    print(people)

    # --------------------------------------------------------
    # 5. Slowa z pozycjami - dolne 30% strony
    # --------------------------------------------------------

    print()
    print("--- SLOWA W DOLNYCH 30% STRONY ---")

    page_height = page.rect.height
    footer_y = page_height * 0.70

    words = page.get_text(
        "words",
        sort=False,
    )

    for word in words:
        x0, y0, x1, y1, value, block, line, word_no = word

        if y0 >= footer_y:
            print(
                repr(value),
                "bbox=",
                (
                    round(x0, 1),
                    round(y0, 1),
                    round(x1, 1),
                    round(y1, 1),
                ),
                "block=",
                block,
                "line=",
                line,
            )

    # --------------------------------------------------------
    # 6. SPANY - pokazuje, czy imie/nazwisko jest rozbite
    # --------------------------------------------------------

    print()
    print("--- SPANY W DOLNYCH 30% STRONY ---")

    data = page.get_text(
        "dict",
        sort=False,
    )

    for block in data.get(
        "blocks",
        [],
    ):
        if block.get("type") != 0:
            continue

        for line in block.get(
            "lines",
            [],
        ):
            for span in line.get(
                "spans",
                [],
            ):
                bbox = span.get(
                    "bbox",
                    (0, 0, 0, 0),
                )

                if bbox[1] < footer_y:
                    continue

                print(
                    "TEXT=",
                    repr(
                        span.get(
                            "text",
                            "",
                        )
                    ),
                    "BBOX=",
                    tuple(
                        round(v, 1)
                        for v in bbox
                    ),
                    "FONT=",
                    span.get("font"),
                    "SIZE=",
                    span.get("size"),
                )


doc.close()