import pytest
import io
import zipfile
from src.documents.ooxml_utils import read_xml_part, SecurityError, open_ooxml_package

def test_dtd_protection():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Deklaracja DTD z encją rozwijajacą system files
        zf.writestr("word/document.xml", b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>""")

    buf.seek(0)
    data = buf.read()
    
    zf = open_ooxml_package(data)
    with pytest.raises(SecurityError) as exc_info:
        read_xml_part(zf, "word/document.xml")
    
    assert "zawiera DTD/ENTITY" in str(exc_info.value)
