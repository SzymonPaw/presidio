import io
from typing import List, Dict, Any

import fitz  # PyMuPDF


class PdfAdapter:
    """Adapter do analizy i anonimizacji dokumentow PDF z warstwa tekstowa."""

    def get_full_text(self, pdf_bytes: bytes) -> str:
        """Zwraca pelny tekst PDF(do analizy)."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        return "\n".join(parts)

    def get_page_preview(self, pdf_bytes: bytes, page_num: int, findings: List[Dict[str, Any]], active_keys: set = None, highlight_key: tuple = None) -> bytes:
        """Renderuje stronę PDF do obrazka PNG z naniesionymi ramkami."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if page_num < 0 or page_num >= doc.page_count:
            doc.close()
            return b""

        page = doc[page_num]

        # Rysujemy ramki bezpośrednio na stronie PDF przed wyrenderowaniem do pixmapy
        for f in findings:
            if f.get("page") == page_num and f.get("bbox"):
                rect = fitz.Rect(f["bbox"])
                key = (f["entity_type"], f["raw_value"])

                if highlight_key and key == highlight_key:
                    # Podświetlenie wybranego elementu na NIEBIESKO (grubsza linia)
                    page.draw_rect(rect, color=(0, 0.4, 1), width=3, fill=(0, 0.4, 1), fill_opacity=0.35)
                elif active_keys is None or key in active_keys:
                    # Rysowanie aktywnego elementu na CZERWONO
                    page.draw_rect(rect, color=(1, 0, 0), width=2, fill=(1, 0, 0), fill_opacity=0.2)

        # Renderyzacja - zoom 2x dla lepszej czytelności
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)

        img_data = pix.tobytes("png")
        doc.close()
        return img_data

    def anonymize(self, pdf_bytes: bytes, findings: List[Dict]) -> bytes:
        """Trwale redaguje PDF i wstawia znanczniki."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        replacements: dict[str, str] = {}
        for f in findings:
            raw = f.get("raw_value", "").strip()
            marker = f.get("marker", "")
            if raw and marker:
                replacements[raw] = marker

        if not replacements:
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            buf.seek(0)
            return buf.read()

        for page in doc:
            for raw_value, marker in replacements.items():
                hits = page.search_for(raw_value)
                for rect in hits:
                    page.add_redact_annot(
                        quad=rect,
                        text=marker,
                        fontname="Helv",
                        fontsize=max(4.0, rect.height * 0.75),
                        align=fitz.TEXT_ALIGN_LEFT,
                        fill=(1, 1, 1),
                        text_color=(0, 0, 0),
                    )
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        buf = io.BytesIO()
        doc.save(buf, deflate=True, garbage=3)
        doc.close()
        buf.seek(0)
        return buf.read()
