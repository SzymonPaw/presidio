Pracujesz nad repozytorium:

https://github.com/SzymonPaw/presidio

Najpierw przeczytaj CAŁE repozytorium, w szczególności:

- todo.md
- reguly_wykrywania.md
- requirements.txt
- src/app_factory.py
- src/settings.py
- src/anonymization/rule_engine.py
- src/anonymization/service.py
- src/anonymization/marker_registry.py
- src/documents/pdf_adapter.py
- config/recognizers/*
- static/js/app.js
- templates/index.html
- scripts/update_dictionaries.py

Nie zaczynaj implementacji, zanim nie zrozumiesz obecnego przepływu:
upload -> analiza -> Findings -> ręczne zatwierdzenie -> anonimizacja -> wynik.

CEL
===

Dodaj do istniejącej aplikacji bezpieczną, lokalną obsługę:

1. DOCX — obowiązkowo.
2. XLSX — również zaimplementuj w ramach tego zadania, jeżeli można to zrobić bez naruszania wymagań bezpieczeństwa i zachowania dokumentu.

PDF ma nadal działać dokładnie tak jak obecnie.

NIE implementuj teraz:
- .doc
- .xls
- .docm
- .xlsm
- .xlsb

Formaty legacy .doc/.xls pozostaw jako przyszły etap i opisz to w todo.md.

Nie używaj:
- modeli LLM;
- modeli NLP/NER;
- spaCy model;
- Stanza;
- Transformers;
- zewnętrznych API;
- Microsoft Office COM;
- LibreOffice;
- konwerterów online;
- usług chmurowych.

Całe przetwarzanie dokumentu musi odbywać się lokalnie.

==================================================
1. KLUCZOWA ZASADA — NIE TWÓRZ NOWYCH REGUŁ PII
==================================================

NIE twórz nowego systemu wykrywania danych dla DOCX/XLSX.

DOCX i XLSX MUSZĄ korzystać z dokładnie tego samego:

- DeterministicAnalyzer;
- wszystkich obecnych recognizerów;
- validatorów;
- regexów;
- config/recognizers/*.yml;
- first_names.csv;
- surnames.csv;
- localities.txt;
- allowlist;
- MarkerRegistry;
- mechanizmu rozstrzygania konfliktów

które są już używane przez PDF.

Nie kopiuj recognizerów do adapterów dokumentów.

Adapter dokumentu ma odpowiadać wyłącznie za:

1. bezpieczne wydobycie tekstu i jego lokalizacji;
2. przekazanie tekstu do istniejącego DeterministicAnalyzer;
3. mapowanie start/end z wyników analyzera na elementy dokumentu;
4. trwałe zastąpienie zatwierdzonej wartości markerem;
5. zachowanie pozostałej struktury dokumentu.

Jeżeli wykrywanie jakiegoś typu PII jest błędne, nie naprawiaj tego osobnym regexem w adapterze DOCX/XLSX.

==================================================
2. BIBLIOTEKA
==================================================

Do parsowania i modyfikacji XML wykorzystaj:

lxml==6.1.1

Do obsługi pakietu OOXML wykorzystaj wyłącznie biblioteki standardowe:

- zipfile
- io.BytesIO

Nie używaj python-docx jako głównego mechanizmu zapisu DOCX.

Nie używaj openpyxl do ponownego zapisywania istniejącego XLSX.

Powód:
aplikacja ma modyfikować tylko konkretne elementy XML i zachowywać wszystkie inne elementy pakietu możliwie bez zmian.

Dodaj lxml==6.1.1 do requirements.txt.

Nie aktualizuj bez potrzeby wersji Presidio ani istniejących bibliotek.

==================================================
3. WSPÓLNA WARSTWA OOXML
==================================================

Utwórz wspólny moduł, np.:

src/documents/ooxml_utils.py

Odpowiadający za:

- otwieranie pakietu ZIP z bytes/BytesIO;
- walidację struktury ZIP;
- bezpieczne czytanie części XML;
- bezpieczny parser lxml;
- ponowne składanie pakietu w pamięci.

NIE wypakowuj dokumentów na dysk.

NIE używaj:
ZipFile.extract()
ZipFile.extractall()

Wszystkie operacje wykonuj w pamięci.

Parser XML musi być skonfigurowany defensywnie:

- resolve_entities=False
- load_dtd=False
- no_network=True
- huge_tree=False
- recover=False

Dodatkowo odrzucaj XML zawierający niedozwolone DTD/ENTITY,
jeżeli ich obecność może tworzyć ryzyko.

Dodaj ochronę przed ZIP bomb:

- maksymalna liczba wpisów ZIP;
- maksymalny rozmiar pojedynczej zdekompresowanej części;
- maksymalny łączny rozmiar po dekompresji;
- limit współczynnika kompresji;
- odrzucanie podejrzanych nazw ścieżek;
- brak path traversal;
- brak niekontrolowanej dekompresji.

Limity umieść w src/settings.py.

Podczas ponownego zapisu:
- niezmodyfikowane części pakietu pozostaw z oryginalną zawartością;
- modyfikuj wyłącznie XML, który rzeczywiście wymaga anonimizacji.

==================================================
4. DOCX ADAPTER
==================================================

Dodaj:

src/documents/docx_adapter.py

DOCX traktuj jako ZIP/OOXML.

Zweryfikuj przynajmniej:
- poprawny ZIP;
- [Content_Types].xml;
- obecność word/document.xml;
- zgodność rozszerzenia ze strukturą.

Odrzucaj pliki zaszyfrowane lub niebędące prawdziwym DOCX.

Analizuj wszystkie istotne źródła tekstu, nie tylko document.xml.

Minimum:

- word/document.xml
- word/header*.xml
- word/footer*.xml
- word/footnotes.xml
- word/endnotes.xml
- word/comments.xml
- tekst tabel
- tekst w hyperlinkach
- tekst w textboxach / w:txbxContent
- tekst ukryty
- tekst śledzenia zmian
- w:t
- w:delText
- odpowiednie w:instrText, jeśli mogą zawierać dane użytkownika

Uwzględnij również metadane:

- docProps/core.xml
- docProps/custom.xml
- właściwości autora / lastModifiedBy itp.

Komentarze:
analizuj zarówno treść komentarza, jak i tekstowe metadane autora,
jeżeli zawierają PII.

TRACK CHANGES:

To jest wymaganie bezpieczeństwa.

Nie wolno pozostawić oryginalnej wartości w:
- w:delText;
- w:ins;
- rewizjach;
- komentarzach.

Dokument po anonimizacji nie może umożliwiać odzyskania wartości
przez włączenie "Pokaż wszystkie zmiany".

==================================================
5. ŁĄCZENIE RUNÓW W DOCX
==================================================

Nie analizuj każdego w:t osobno.

Dane mogą być podzielone przez Word np.:

<w:r><w:t>Jan</w:t></w:r>
<w:r><w:t> Kowalski</w:t></w:r>

Analyzer ma zobaczyć:

Jan Kowalski

Zbuduj dla każdego logicznego fragmentu/story:

- jeden ciąg tekstowy;
- mapę character offset -> XML node + offset wewnątrz node.

Następnie przekaż cały logiczny tekst do istniejącego
DeterministicAnalyzer.

Po otrzymaniu start/end:
zmapuj zakres z powrotem na odpowiednie w:t/w:delText.

Podmiany wykonuj OD KOŃCA TEKSTU DO POCZĄTKU,
żeby wcześniejsze offsety nie przesuwały się.

Jeżeli znalezienie obejmuje kilka runów:

- marker wpisz do pierwszego elementu obejmującego finding;
- z kolejnych elementów usuń wyłącznie część należącą do finding;
- zachowaj tekst znajdujący się przed i za finding;
- nie usuwaj run properties;
- nie scalaj runów bez potrzeby;
- marker ma odziedziczyć format pierwszego zastępowanego runa.

Obsłuż xml:space="preserve" prawidłowo.

Nie używaj paragraph.text = "...".

==================================================
6. EMBEDDED OBJECTS I NIEZNANE CZĘŚCI DOCX
==================================================

Wykrywaj między innymi:

- word/embeddings/*
- ActiveX
- customXml
- nietypowe części pakietu
- obiekty OLE
- podpisy cyfrowe

Jeżeli część może zawierać dane, których aplikacja nie analizuje,
NIE przedstawiaj dokumentu jako w pełni sprawdzonego.

Dla elementów wysokiego ryzyka preferuj fail-closed:
odrzuć anonimizację z czytelnym komunikatem.

Dla elementów niższego ryzyka zwróć wyraźne warnings.

Nie próbuj uruchamiać osadzonych obiektów.

Nie wykonuj żadnych zewnętrznych hyperlinków ani relacji.

==================================================
7. XLSX ADAPTER
==================================================

Dodaj:

src/documents/xlsx_adapter.py

Analogicznie XLSX traktuj jako ZIP/OOXML.

Zweryfikuj:
- poprawny ZIP;
- [Content_Types].xml;
- xl/workbook.xml;
- strukturę arkuszy.

Analizuj co najmniej:

- xl/sharedStrings.xml;
- inlineStr w worksheet XML;
- stringowe wartości komórek;
- komentarze;
- threaded comments, jeśli występują i można je bezpiecznie obsłużyć;
- nagłówki i stopki;
- wszystkie arkusze, także hidden i veryHidden;
- docProps/core.xml;
- docProps/custom.xml.

Findings XLSX powinny zawierać lokalizację:
- nazwa arkusza;
- adres komórki.

Nie używaj openpyxl do save() istniejącego skoroszytu.

==================================================
8. SHARED STRINGS — WAŻNE
==================================================

Pamiętaj, że jeden wpis sharedStrings może być używany przez wiele komórek.

Nie wolno zmienić shared string globalnie,
jeżeli użytkownik zatwierdził anonimizację tylko jednej konkretnej komórki.

W takim przypadku:
- sklonuj odpowiedni shared-string entry;
- zanonimizuj kopię;
- zmień indeks shared string tylko w zatwierdzonej komórce.

Zachowaj rich text runs i ich formatowanie.

Tak samo jak dla DOCX:
łącz tekst rozbity na wiele rich-text runów przed analizą,
a potem mapuj finding do konkretnych węzłów.

==================================================
9. FORMUŁY I ELEMENTY NIEOBSŁUGIWANE
==================================================

Nie niszcz formuł.

Nie konwertuj formuł na wartości.

Jeżeli formuła lub inny element zawiera PII i bezpieczna podmiana
mogłaby zmienić semantykę dokumentu:
- wykryj taki przypadek;
- zwróć warning albo przerwij anonimizację;
- nie twierdź, że dokument jest bezpiecznie zanonimizowany.

Wszystkie nieobsługiwane przypadki mają być jawne.

==================================================
10. SERVICE
==================================================

Rozszerz src/anonymization/service.py.

Nie twórz nowych instancji nowych recognizerów.

Dodaj odpowiednią obsługę:

- analyze_pdf()
- analyze_docx()
- analyze_xlsx()

albo bezpiecznie uogólnij API, jeżeli kod będzie czytelniejszy.

Każdy adapter musi używać:

self.analyzer = DeterministicAnalyzer()

oraz istniejącego:

MarkerRegistry

Zachowaj obecny format findings w możliwie dużym stopniu.

Dodaj pola lokalizacji właściwe formatowi:
- PDF: page/bbox;
- DOCX: część/story + opcjonalnie paragraph;
- XLSX: sheet + cell.

==================================================
11. APP_FACTORY
==================================================

Zmień src/app_factory.py.

Obecnie aplikacja:
- analizuje prawidłowo PDF;
- inne pliki próbuje decode("utf-8");
- anonimizację dopuszcza tylko dla PDF.

Usuń ten fallback dla dokumentów binarnych.

Dodaj jawny routing:

.pdf  -> PdfAdapter
.docx -> DocxAdapter
.xlsx -> XlsxAdapter

Nie wybieraj formatu WYŁĄCZNIE na podstawie rozszerzenia.

Zweryfikuj również sygnaturę/strukturę pliku.

MIME:

PDF:
application/pdf

DOCX:
application/vnd.openxmlformats-officedocument.wordprocessingml.document

XLSX:
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

Dla nieobsługiwanych:
.doc
.xls
.docm
.xlsm
.xlsb

zwróć czytelny błąd HTTP 400.

==================================================
12. UI
==================================================

Zaktualizuj:

templates/index.html
static/js/app.js

Pole wyboru pliku powinno jasno przyjmować:
- PDF
- DOCX
- XLSX

Nie implementuj podglądu strony Word/Excel jako obrazka.

Obecny preview PDF ma nadal działać dla PDF.

Dla DOCX/XLSX:
- Findings mają działać normalnie;
- przycisk/podgląd strony PDF ma być ukryty lub nieaktywny;
- UI nie może próbować wywoływać /preview_page.

Nie przebudowuj całego interfejsu.

==================================================
13. BEZPIECZEŃSTWO
==================================================

Bezwzględnie zachowaj zasady projektu:

- wszystko lokalnie;
- zero zewnętrznych requestów;
- zero uploadów do API;
- zero telemetrycznej integracji dodawanej przez nowe biblioteki;
- dokumenty nie są celowo zapisywane na dysku;
- praca przez bytes / BytesIO;
- brak nazw i treści dokumentów w logach;
- brak PII w exception logs;
- brak plików tymczasowych;
- brak automatycznego uruchamiania Office;
- brak makr;
- brak external entity resolution;
- brak pobierania zewnętrznych relacji.

Nie wyłączaj SSL/TLS, mechanizmów bezpieczeństwa ani walidacji
w celu "obejścia" problemu.

==================================================
14. TESTY
==================================================

Dodaj katalog tests/, jeśli jeszcze nie istnieje.

Przygotuj automatyczne testy syntetyczne bez prawdziwych danych PII.

DOCX:

1. zwykły paragraph;
2. PERSON w jednym runie;
3. PERSON podzielony na 2-4 runy;
4. PESEL podzielony między runy;
5. adres podzielony między runy;
6. tabela;
7. header;
8. footer;
9. textbox;
10. comment;
11. comment author;
12. footnote;
13. endnote;
14. hidden text;
15. tracked insertion;
16. tracked deletion / w:delText;
17. hyperlink;
18. metadata author/lastModifiedBy;
19. kilka wystąpień tej samej wartości -> ten sam marker;
20. różne wartości -> kolejne markery.

Po anonimizacji test ma otworzyć wynikowy DOCX jako ZIP
i przeszukać WSZYSTKIE części pakietu.

ORYGINALNA WARTOŚĆ NIE MOŻE wystąpić w żadnej części XML,
w której miała zostać zanonimizowana.

XLSX:

1. sharedStrings;
2. inlineStr;
3. rich text;
4. hidden sheet;
5. veryHidden sheet;
6. comment;
7. header/footer;
8. metadata;
9. ta sama shared string użyta w wielu komórkach;
10. selektywna anonimizacja tylko jednej z tych komórek;
11. zachowanie formuły;
12. zachowanie stylu;
13. zachowanie merge;
14. zachowanie workbook structure.

Dodaj także testy bezpieczeństwa:

- nieprawidłowy ZIP;
- fałszywy DOCX;
- fałszywy XLSX;
- path traversal entry;
- podejrzana liczba wpisów;
- ZIP bomb / wysoki compression ratio;
- DTD;
- ENTITY;
- encrypted Office file;
- embedded OLE;
- macro-enabled file.

==================================================
15. TEST REGRESJI PDF
==================================================

Przed zakończeniem zadania uruchom testy/regresję PDF.

Dodanie DOCX/XLSX nie może zmienić:
- recognizerów;
- regexów;
- walidatorów;
- markerów;
- zachowania PDF.

Nie poprawiaj przy okazji obecnych regexów.

To jest osobne zadanie.

==================================================
16. REQUIREMENTS.TXT
==================================================

Dodaj:

lxml==6.1.1

Nie dodawaj bez potrzeby:
- python-docx;
- openpyxl;
- pandas;
- LibreOffice wrapper;
- Aspose;
- pywin32.

Przypnij wersję nowej zależności.

Sprawdź pip check.

Nie aktualizuj automatycznie wszystkich istniejących zależności.

==================================================
17. TODO.MD
==================================================

Zaktualizuj todo.md zgodnie z FAKTYCZNIE wykonanym zakresem.

Nie oznaczaj elementu jako ukończony, jeśli implementacja pokrywa go
tylko częściowo.

Zaktualizuj informację o środowisku:
docelowym środowiskiem tego projektu jest Python 3.13.14,
nie Python 3.12.

Po implementacji oznacz odpowiednie punkty DOCX/XLSX jako:
- wykonane;
- częściowo wykonane;
- pozostawione na później.

Pozostaw .doc/.xls jako późniejszy etap.

==================================================
18. REGULY_WYKRYWANIA.MD
==================================================

Nie zmieniaj istniejących reguł PII bez konieczności.

Nie twórz osobnych reguł dla Worda/Excela.

Jeżeli trzeba dopisać informację architektoniczną,
wyraźnie zaznacz, że DOCX/XLSX korzystają z tego samego
DeterministicAnalyzer i tych samych słowników/reguł co PDF.

==================================================
19. INNE PLIKI
==================================================

Zaktualizuj wszystkie inne pliki, które są rzeczywiście potrzebne,
np.:

- src/settings.py
- src/documents/__init__.py
- templates/index.html
- static/js/app.js
- ewentualne pliki testowe

Nie twórz nowych warstw abstrakcji bez potrzeby.

Preferowana struktura:

src/documents/
    pdf_adapter.py
    docx_adapter.py
    xlsx_adapter.py
    ooxml_utils.py

==================================================
20. KRYTERIA AKCEPTACJI
==================================================

Zadanie jest ukończone dopiero gdy:

1. istniejący PDF nadal działa;
2. DOCX można przeanalizować;
3. Findings z DOCX korzystają z tych samych recognizerów;
4. zatwierdzone PII można trwale zastąpić markerami w DOCX;
5. dokument wynikowy otwiera się w Microsoft Word;
6. style i struktura dokumentu pozostają zachowane;
7. PII nie pozostaje w rewizjach, komentarzach ani metadanych;
8. XLSX można przeanalizować i zanonimizować analogicznie;
9. wynikowy XLSX otwiera się w Excelu;
10. formuły i elementy nieedytowane pozostają zachowane;
11. nie powstają dokumenty tymczasowe;
12. nie wykonywane są requesty sieciowe;
13. testy przechodzą;
14. pip check przechodzi;
15. todo.md odpowiada stanowi implementacji;
16. requirements.txt zawiera przypięte nowe zależności.

==================================================
21. NA KONIEC
==================================================

Po zakończeniu NIE rób automatycznie commita ani pusha.

Najpierw pokaż:

1. listę zmienionych/utworzonych plików;
2. krótkie uzasadnienie każdej zmiany;
3. listę nowych zależności;
4. wyniki testów;
5. wynik pip check;
6. listę nadal nieobsługiwanych elementów;
7. ryzyka bezpieczeństwa, których nie udało się całkowicie usunąć;
8. dokładne komendy PowerShell do ręcznego przetestowania:
   - DOCX;
   - XLSX;
   - PDF regresji.

Jeżeli w trakcie implementacji okaże się, że któregoś wymagania
nie da się spełnić bez przebudowania lub utraty danych dokumentu,
NIE obchodź problemu.
Zatrzymaj się i jasno opisz problem oraz proponowane opcje.