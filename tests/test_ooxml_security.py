import pytest
import io
import zipfile
from src.documents.ooxml_utils import open_ooxml_package, SecurityError

def test_zip_bomb_protection():
    # Tworzenie pliku w pamieci imitującego zip bomb (duży współczynnik kompresji)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", b"A" * (50 * 1024 * 1024)) # 50 MB czystych A

    buf.seek(0)
    data = buf.read()
    
    with pytest.raises(SecurityError) as exc_info:
        open_ooxml_package(data)
    
    assert "limit dekompresji" in str(exc_info.value) or "Podejrzany współczynnik" in str(exc_info.value)

def test_zip_path_traversal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../word/document.xml", b"<xml></xml>")

    buf.seek(0)
    data = buf.read()
    
    with pytest.raises(SecurityError) as exc_info:
        open_ooxml_package(data)
    
    assert "Niedozwolona ścieżka" in str(exc_info.value)
