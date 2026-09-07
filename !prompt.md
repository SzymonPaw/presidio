Przeanalizuj całe repozytorium i wdroż kompleksowo obsługę PDF zgodnie z poniższymi wymaganiami.

CEL:
Rozwiązać docelowo 3 problemy:

1. obsługa skanów/obrazów w PDF przez lokalny OCR,
2. poprawne i stabilne wyświetlanie automatycznie wykrytych danych wrażliwych bez przesunięć zaznaczeń,
3. ręczne zaznaczanie tekstu w podglądzie PDF i dodawanie go do anonimizacji (na sam koniec).

ARCHITEKTURA DOCELOWA:

* PDF.js pozostaje viewerem PDF i obsługuje zoom, scroll oraz zaznaczanie tekstu,
* PyMuPDF jest jedynym źródłem geometrii danych, bboxów/quadów oraz wykonuje finalną redakcję,
* Tesseract OCR działa całkowicie lokalnie i tylko dla stron bez użytecznej warstwy tekstowej,
* obecne deterministyczne reguły/Presidio nadal odpowiadają za wykrywanie danych,
* żadnych zewnętrznych API ani usług OCR.

KROKI:

1. Otwórz plik `PDF_IMPLEMENTATION_PLAN.md`.
2. Opisz w nim plan zmian, pliki do modyfikacji, status każdego etapu.
3. Po KAŻDEJ wykonanej zmianie aktualizuj ten plik: co wykonano, co zostało i czy pojawiły się problemy.
4. Przeanalizuj obecny PDF.js/PyMuPDF flow.
5. Usuń zależność pozycjonowania zaznaczeń od wyszukiwania tekstu w `textLayer`/DOM. Automatyczne zaznaczenia mają być rysowane bezpośrednio z bboxów/quadów backendu po konwersji przez viewport PDF.js.
6. Każde wystąpienie findingu PDF ma posiadać co najmniej: `page`, `bbox/quads`, `source`, `raw_value`, `marker`, `enabled`.
7. Finalna anonimizacja ma używać dokładnie bboxów/quadów zaakceptowanych findingów. Nie wykonuj ponownie `search_for(raw_value)` podczas zapisu.
8. Dodaj ręczne zaznaczanie tekstu w PDF.js. Zaznaczony fragment ma być możliwy do dodania jako ręczny finding i powiązany z konkretną stroną oraz geometrią.
9. Dodaj lokalny OCR przez Tesseract + PyMuPDF (`get_textpage_ocr()`), język polski.
10. OCR uruchamiaj tylko dla stron bez użytecznej warstwy tekstowej. Użyj oszczędnych ustawień: jeden job jednocześnie, `OMP_THREAD_LIMIT=1`, około 300 DPI, `tessdata_fast/pol`.
11. Wynik OCR musi dostarczać tekst i geometrię, aby automatyczne findings działały dokładnie tak samo jak dla zwykłego PDF.
12. Dla skanów umożliw ręczne zaznaczanie rozpoznanego tekstu poprzez niewidoczną/selectable warstwę OCR nad stroną.
13. Przy redakcji danych pochodzących ze skanu usuń również piksele obrazu w obszarze bbox, a nie tylko warstwę tekstową.
14. Nie zmieniaj istniejącej logiki DOCX/XLSX ani deterministycznych recognizerów, jeśli nie jest to konieczne.
15. Na końcu zaktualizuj `PDF_IMPLEMENTATION_PLAN.md` i oznacz każdy punkt jako DONE / TODO / BLOCKED.

EFEKT FINALNY:
Użytkownik otwiera PDF w normalnym viewerze PDF.js, może zaznaczać tekst ręcznie, automatyczne findings są zawsze wyświetlane dokładnie w odpowiednim miejscu, skany są lokalnie OCR-owane przez Tesseract, a finalna anonimizacja usuwa dokładnie te obszary, które użytkownik widział i zaakceptował.

Nie twórz obejść ani kolejnych niezależnych mechanizmów. Zbuduj jeden spójny pipeline PDF oparty na wspólnej geometrii PyMuPDF.