import pytest
import io
import fitz
import zipfile
from src.documents.pdf_adapter import PdfAdapter
from src.documents.docx_adapter import DocxAdapter
from src.documents.xlsx_adapter import XlsxAdapter
from src.anonymization.service import AnonymizationService
from src.anonymization.rule_engine import OrganizationRecognizer, DeterministicAnalyzer, _normalize_exclusion_value

def test_organization_recognizer_matches_compact_legal_form():
    text = "XYZ BROKERZY UBEZPIECZENIOWI SP.Z O.O."
    results = OrganizationRecognizer().analyze(text, ["ORGANIZATION"])

    assert results
    assert any(r.entity_type == "ORGANIZATION" and text[r.start:r.end] == text for r in results)


def test_organization_recognizer_matches_all_legal_form_variants():
    variants = [
        "XYZ BROKERZY UBEZPIECZENIOWI SP.Z O.O.",
        "XYZ BROKERZY UBEZPIECZENIOWI SP. Z O. O.",
        "XYZ BROKERZY UBEZPIECZENIOWI SP Z O O",
        "XYZ BROKERZY UBEZPIECZENIOWI SP. Z O O",
        "XYZ BROKERZY UBEZPIECZENIOWI SP.Z.O.O.",
        "XYZ BROKERZY UBEZPIECZENIOWI sp. z o. o.",
    ]

    for text in variants:
        results = OrganizationRecognizer().analyze(text, ["ORGANIZATION"])
        assert results, f"Brak rozpoznania dla wariantu: {text}"
        assert any(r.entity_type == "ORGANIZATION" and text[r.start:r.end] == text for r in results), (
            f"Nie rozpoznano całej firmy dla wariantu: {text}"
        )


def test_organization_recognizer_matches_business_activity_forms():
    variants = [
        "ZAKŁAD USŁUGOWO-HANDLOWY 'XYZ'",
        "Zakład produkcyjno-usługowo-handlowy 'XYZ'",
        "Zakład produkcyjno-handlowy XYZ",
        "Przedsiębiorstwo handlowo-usługowe XYZ",
        "Przedsiębiorstwo handlowo-usługowe 'XYZ'",
        "Firma handlowa XYZ",
    ]

    for text in variants:
        results = OrganizationRecognizer().analyze(text, ["ORGANIZATION"])
        assert results, f"Brak rozpoznania dla formy działalności: {text}"
        assert any(r.entity_type == "ORGANIZATION" and text[r.start:r.end] == text for r in results), (
            f"Nie rozpoznano całej firmy dla formy działalności: {text}"
        )


def test_pkd_codes_are_excluded_from_automatic_matches():
    analyzer = DeterministicAnalyzer()
    sample_code = "01.11.Z"
    assert _normalize_exclusion_value(sample_code) in analyzer.pkd_exclusions

    result = analyzer.analyze(sample_code)
    assert result == []


def test_pdf_no_regression():
    # Sprawdzamy czy interfejs pdf_adapter nie spsuł się
    adapter = PdfAdapter()
    
    # Tworzymy pusty plik PDF ze słowem Tajne w pamieci by pyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "Tekst dokumentu zawierający Tajne informacje.")
    
    buf = io.BytesIO()
    doc.save(buf)
    pdf_bytes = buf.getvalue()
    doc.close()
    
    # Przykładowe finding
    findings = [
        {"entity_type": "SECRET", "raw_value": "Tajne", "marker": "[TAJNE]", "page": 0}
    ]
    
    # Dodanie obwiedni recznie pod test
    # (Symulacja znalezienia - w usłudze robimy hits = page.search_for)
    doc_test = fitz.open(stream=pdf_bytes, filetype="pdf")
    hits = doc_test[0].search_for("Tajne")
    findings[0]["bbox"] = tuple(hits[0]) if hits else None
    
    out_pdf = adapter.anonymize(pdf_bytes, findings)
    
    assert len(out_pdf) > 0
    
    doc_out = fitz.open(stream=out_pdf, filetype="pdf")
    text_out = doc_out[0].get_text()
    
    assert "Tajne" not in text_out
    assert "[TAJNE]" in text_out
    doc_out.close()

def test_docx_merge_runs_and_anonymize():
    # Prosty test na integracje docx - mockujac podstawowy DOCX bez rozbudowanych czesci
    from lxml import etree
    
    # Zbudujmy uproszczony document.xml
    xml_content = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>Jan</w:t></w:r>
      <w:r><w:t> Ko</w:t></w:r>
      <w:r><w:t>walski </w:t></w:r>
      <w:r><w:t>to tester.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        zf.writestr("word/document.xml", xml_content)
        
    docx_bytes = buf.getvalue()
    
    adapter = DocxAdapter()
    
    # Udajemy że w serwisie znaleziono to w bloku tekstu
    # Blok: "Jan Kowalski to tester."
    findings = [
        {"entity_type": "PERSON", "raw_value": "Jan Kowalski", "marker": "[OSOBA_1]"}
    ]
    
    out_bytes = adapter.anonymize(docx_bytes, findings)
    
    # Rozpakuj by sprawdzić xml
    with zipfile.ZipFile(io.BytesIO(out_bytes), "r") as zf_out:
        out_xml = zf_out.read("word/document.xml").decode("utf-8")
        
    # Oryginalny tekst Jan Ko/walski musi byc zamieniony
    assert "Jan" not in out_xml
    assert "Ko</w:t>" not in out_xml
    assert "walski" not in out_xml
    assert "[OSOBA_1]" in out_xml
    assert "to tester." in out_xml

def test_xlsx_shared_strings_anonymize():
    import io, zipfile
    xml_content = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">
  <si>
    <t>Jan Kowalski</t>
  </si>
</sst>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""")
        zf.writestr("xl/workbook.xml", b"<workbook></workbook>")
        zf.writestr("xl/sharedStrings.xml", xml_content)
        
    xlsx_bytes = buf.getvalue()
    
    adapter = XlsxAdapter()
    findings = [
        {"entity_type": "PERSON", "raw_value": "Jan Kowalski", "marker": "[OSOBA_X]"}
    ]
    
    out_bytes = adapter.anonymize(xlsx_bytes, findings)
    
    with zipfile.ZipFile(io.BytesIO(out_bytes), "r") as zf_out:
        out_xml = zf_out.read("xl/sharedStrings.xml").decode("utf-8")
        
    assert "Jan Kowalski" not in out_xml
    assert "[OSOBA_X]" in out_xml


def test_xlsx_preview_renders_sheet_tabs_for_multiple_worksheets():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        zf.writestr("xl/workbook.xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Arkusz 1" sheetId="1" r:id="rId1"/>
    <sheet name="Arkusz 2" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""")
        zf.writestr("xl/_rels/workbook.xml.rels", b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>""")
        zf.writestr("xl/worksheets/sheet1.xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Jan Kowalski</t></is></c></row>
  </sheetData>
</worksheet>""")
        zf.writestr("xl/worksheets/sheet2.xml", b"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Anna Nowak</t></is></c></row>
  </sheetData>
</worksheet>""")

    html = XlsxAdapter().build_preview_html(buf.getvalue(), [{"raw_value": "Jan Kowalski", "xlsx_cell": "A1"}], mode="detections")

    assert "xlsx-sheet-tab" in html
    assert "Arkusz 1" in html
    assert "Arkusz 2" in html
    assert html.count("xlsx-sheet-panel") >= 2
    assert 'class="xlsx-hit"' in html

