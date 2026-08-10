from collections import Counter
from zipfile import ZipFile
from lxml import etree
import sys

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

NS = {
    "x": XLSX_NS,
}

path = sys.argv[1]

with ZipFile(path) as zf:
    print("WORKSHEETS")
    print("==========")

    for name in sorted(zf.namelist()):
        if not (
            name.startswith("xl/worksheets/sheet")
            and name.endswith(".xml")
        ):
            continue

        root = etree.fromstring(zf.read(name))

        types = Counter(
            cell.get("t", "<brak>")
            for cell in root.xpath("//x:c", namespaces=NS)
        )

        print(name, dict(types))

    print()
    print("SHARED STRINGS")
    print("==============")

    if "xl/sharedStrings.xml" in zf.namelist():
        root = etree.fromstring(
            zf.read("xl/sharedStrings.xml")
        )

        values = []

        for item in root.xpath("//x:si", namespaces=NS):
            text = "".join(
                item.xpath(
                    ".//x:t/text()",
                    namespaces=NS,
                )
            )
            values.append(text)

        print("Liczba:", len(values))

        for index, value in enumerate(values):
            print(index, repr(value))
    else:
        print("Brak sharedStrings.xml")