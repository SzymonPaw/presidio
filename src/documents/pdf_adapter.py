import io
from typing import List, Dict, Any

import fitz  # PyMuPDF
import pikepdf

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

    def detect_digital_signatures(
        self,
        pdf_bytes: bytes,
    ) -> List[Dict[str, Any]]:

        signatures: List[Dict[str, Any]] = []

        doc = fitz.open(
            stream=pdf_bytes,
            filetype="pdf",
        )

        try:
            for page_index in range(
                doc.page_count
            ):
                page = doc.load_page(
                    page_index
                )

                widgets = page.widgets()

                if widgets is None:
                    continue

                for widget in widgets:
                    if (
                        widget.field_type
                        != fitz.PDF_WIDGET_TYPE_SIGNATURE
                    ):
                        continue

                    # Puste pole przeznaczone na przyszly podpis
                    # nie jest dla nas podpisem.
                    if widget.is_signed is not True:
                        continue

                    rect = widget.rect

                    signatures.append(
                        {
                            "page": page_index,
                            "bbox": [
                                float(rect.x0),
                                float(rect.y0),
                                float(rect.x1),
                                float(rect.y1),
                            ],
                            "field_name": (
                                widget.field_name
                                or ""
                            ),
                        }
                    )

        finally:
            doc.close()

        return signatures


    def _remove_digital_signatures(
        self,
        pdf_bytes: bytes,
    ) -> bytes:

        source = io.BytesIO(
            pdf_bytes
        )

        output = io.BytesIO()

        try:
            with pikepdf.open(
                source
            ) as pdf:
                acroform = pdf.acroform

                if not acroform.exists:
                    raise RuntimeError(
                        "Wykryto podpis cyfrowy, ale PDF "
                        "nie posiada dostepnego AcroForm."
                    )

                acroform.disable_digital_signatures()

                pdf.save(
                    output
                )

        except Exception as exc:
            raise RuntimeError(
                "Nie udalo sie usunac podpisu "
                "cyfrowego z dokumentu PDF."
            ) from exc

        result = output.getvalue()

        if not result:
            raise RuntimeError(
                "Usuwanie podpisu zwrocilo pusty PDF."
            )

        # Fail closed:
        # jezeli po operacji nadal widzimy aktywny podpis,
        # nie zwracamy takiego pliku jako poprawnego.
        remaining = self.detect_digital_signatures(
            result
        )

        if remaining:
            raise RuntimeError(
                "Nie wszystkie podpisy cyfrowe "
                "zostaly usuniete."
            )

        return result

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

    def anonymize(
        self,
        pdf_bytes: bytes,
        findings: List[Dict],
    ) -> bytes:

        # ---------------------------------------------------
        # Czy uzytkownik zaznaczyl finding podpisu?
        # ---------------------------------------------------

        remove_signatures = any(
            finding.get("entity_type")
            == "PDF_SIGNATURE"
            for finding in findings
        )

        # ---------------------------------------------------
        # Findings tekstowe.
        #
        # PDF_SIGNATURE nie moze trafic do search_for(),
        # bo nie jest tekstem dokumentu.
        # ---------------------------------------------------

        text_findings = [
            finding
            for finding in findings
            if finding.get("entity_type")
            != "PDF_SIGNATURE"
        ]

        working_bytes = pdf_bytes

        # ---------------------------------------------------
        # Najpierw usuwamy podpis, jezeli zostal zaznaczony.
        # ---------------------------------------------------

        if remove_signatures:
            working_bytes = (
                self._remove_digital_signatures(
                    working_bytes
                )
            )

        replacements: dict[str, str] = {}

        for finding in text_findings:
            raw = finding.get(
                "raw_value",
                "",
            ).strip()

            marker = finding.get(
                "marker",
                "",
            )

            if raw and marker:
                replacements[raw] = marker

        if not replacements:
            return working_bytes

        # ---------------------------------------------------
        # Normalna anonimizacja tekstowa - tak jak dotychczas.
        # ---------------------------------------------------

        doc = fitz.open(
            stream=working_bytes,
            filetype="pdf",
        )

        for page in doc:
            for raw_value, marker in replacements.items():
                hits = page.search_for(
                    raw_value
                )

                for rect in hits:
                    page.add_redact_annot(
                        quad=rect,
                        text=marker,
                        fontname="Helv",
                        fontsize=max(
                            4.0,
                            rect.height * 0.75,
                        ),
                        align=fitz.TEXT_ALIGN_LEFT,
                        fill=(1, 1, 1),
                        text_color=(0, 0, 0),
                    )

            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE
            )

        buf = io.BytesIO()

        doc.save(
            buf,
            deflate=True,
            garbage=3,
        )

        doc.close()

        buf.seek(0)

        return buf.read()