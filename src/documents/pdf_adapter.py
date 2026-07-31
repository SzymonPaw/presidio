import io
from typing import List, Dict

import fitz  # PyMuPDF


class PdfAdapter:
    """Adapter do analizy i anonimizacji dokumentow PDF z warstwa tekstowa.

    Zgodnie z todo.md sekcja 10:
    - Uzywamy PyMuPDF do lokalizacji i trwalej redakcji tekstu.
    - Nie zaslaniamy danych prostokątem bez usunięcia treści źródłowej.
    - Po trwalej redakcji wstawiamy znacznik w miejsce usuniętej wartości.
    - Zachowujemy liczbe stron, obrazy, formularze i geometrie dokumentu.
    """

    def get_full_text(self, pdf_bytes: bytes) -> str:
        """Zwraca pelny tekst PDF jako jeden ciag znakow (do analizy)."""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        return "\n".join(parts)

    def anonymize(self, pdf_bytes: bytes, findings: List[Dict]) -> bytes:
        """Trwale redaguje PDF i wstawia znaczniki w miejsce wykrytych danych.

        Dla kazdego finding:
          1. Wyszukaj wszystkie wystapienia raw_value na kazdej stronie.
          2. Dodaj adnotacje redakcji (add_redact_annot) z tekstem znacznika.
          3. Wywolaj apply_redactions() - fisica usuwa tekst i wstawia znacznik.

        Args:
            pdf_bytes: Bajty oryginalnego pliku PDF.
            findings:  Lista slownikow [{raw_value, marker, ...}, ...].

        Returns:
            Bajty zmodyfikowanego pliku PDF.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Zbierz unikalne pary (wartosc_do_usuniecia -> znacznik)
        replacements: dict[str, str] = {}
        for f in findings:
            raw = f.get("raw_value", "").strip()
            marker = f.get("marker", "")
            if raw and marker:
                replacements[raw] = marker

        if not replacements:
            # Nic do zamiany - zwroc oryginal
            buf = io.BytesIO()
            doc.save(buf)
            doc.close()
            buf.seek(0)
            return buf.read()

        for page in doc:
            for raw_value, marker in replacements.items():
                hits = page.search_for(raw_value, quads=False)
                for rect in hits:
                    # Wyznacz rozmiar fontu dopasowany do wysokosci obiektu
                    font_size = max(4.0, rect.height * 0.75)

                    # add_redact_annot: usuwa oryginalny tekst i opcjonalnie wstawia text
                    page.add_redact_annot(
                        quad=rect,
                        text=marker,
                        fontname="Helv",
                        fontsize=font_size,
                        align=fitz.TEXT_ALIGN_LEFT,
                        fill=(1, 1, 1),       # biale tlo (zamiast czarnego prostokatu)
                        text_color=(0, 0, 0), # czarny tekst znacznika
                    )
            # Zastosuj wszystkie redakcje na tej stronie jednorazowo
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        buf = io.BytesIO()
        doc.save(buf, deflate=True, garbage=3)
        doc.close()
        buf.seek(0)
        return buf.read()
