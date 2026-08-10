# TODO — lokalny anonimizator dokumentów

## 0. Cel i zakres MVP

* [x] Zbudować lokalną aplikację webową do wykrywania i anonimizacji danych w dokumentach.
* [x] MVP obsługuje: `.docx`
* [x] MVP obsługuje: `.xlsx`
* [x] MVP obsługuje: PDF z warstwą tekstową.
* [ ] Kolejne etapy: starsze formaty Word/Excel, następnie skany PDF z OCR.
* [x] Język podstawowy: polski.
* [x] Brak logowania użytkowników w MVP.
* [x] Pierwsza działająca wersja obsługuje jeden plik.
* [ ] Gotowe MVP obsługuje jeden plik albo kilka plików w jednym przesłaniu.
* [x] Zachować układ, style, tabele, obrazy, wykresy, formuły i pozostałe elementy dokumentu.
* [x] Nie przebudowywać dokumentu na podstawie samego wyekstrahowanego tekstu.
* [x] Celem jest możliwie identyczny wygląd, ale bez obietnicy identycznych podziałów linii i stron, gdy znacznik ma inną długość niż tekst źródłowy.

## 1. Jedyny sposób anonimizacji

* [x] Aplikacja zawsze **zastępuje wykryte dane opisowymi znacznikami**, np. `[OSOBA_1]`, `[FIRMA_1]`, `[NIP_1]`.
* [x] Nie tworzyć osobnego trybu „usuń dane” ani przełącznika trybu w interfejsie.
* [x] Zastąpienie oznacza trwałe usunięcie pierwotnej wartości z dokumentu wynikowego i wpisanie znacznika w jej miejsce.
* [x] Ta sama znormalizowana wartość w jednym dokumencie otrzymuje zawsze ten sam znacznik.
* [x] Kolejne różne wartości tego samego typu otrzymują kolejne numery.
* [x] Przykład: `Jan Kowalski` → `[OSOBA_1]`; każde kolejne wystąpienie `Jan Kowalski` → `[OSOBA_1]`; `Anna Nowak` → `[OSOBA_2]`.
* [x] Dla PDF najpierw wykonać trwałą redakcję oryginalnego tekstu, a następnie wstawić znacznik.
* [x] Dla DOCX/XLSX usunąć oryginalny tekst z odpowiednich elementów XML i zapisać w nich znacznik.



### 1.1. Zasady zachowania wyglądu

* [x] Zmieniać wyłącznie węzły zawierające wykryty tekst; nie generować dokumentu od nowa.
* [x] Nie zmieniać fontów, stylów, szerokości kolumn, wysokości wierszy, marginesów, sekcji ani położenia obiektów.
* [x] Znacznik ma przejąć formatowanie zastępowanego tekstu.
* [x] Nie scalać runów ani komórek, jeśli nie jest to konieczne do podmiany wartości rozbitej na fragmenty.
* [x] Nie próbować zachować podziału linii przez zmianę rozmiaru fontu w DOCX/XLSX; możliwe przesunięcia wynikające z długości znacznika są akceptowalne.
* [x] W PDF wolno zmniejszyć font znacznika tylko w jego pierwotnym obszarze, bez przesuwania pozostałych elementów strony.

## 2. Środowisko na firmowym Windowsie

### 2.1. Minimalny udział administratora

* [x] Administrator instaluje tylko **Python 3.12 x64** wraz z:
  * `pip`;
  * Python Launcherem;
  * dodaniem Pythona do `PATH`.
* [x] Docker, WSL, Hyper-V, Visual Studio ani lokalny serwer MySQL nie są potrzebne do MVP.
  Zaktualizowano środowisko: docelowym środowiskiem jest Python 3.13.14 (brak konieczności regresji na 3.12).

### 2.2. Przygotowanie projektu bez administratora

* [x] Utworzyć folder projektu w katalogu użytkownika.
* [x] Utworzyć środowisko:
```bat
py -3.13.14 -m venv .venv
```
* [x] Instalować pakiety bez aktywowania środowiska PowerShell:
```bat
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
* [x] Uruchamiać aplikację:
```bat
.venv\Scripts\python.exe app.py
```
* [x] Udostępniać aplikację lokalnie wyłącznie pod `http://127.0.0.1:5000`.
* [ ] Jeżeli firmowa sieć blokuje PyPI, przygotować katalog `wheelhouse/` z instalacją offline.

## 3. Technologie i decyzje architektoniczne

* [x] Python 3.12.
* [x] Flask + Jinja + lekki JavaScript.
* [x] Presidio Analyzer oraz Presidio Anonymizer jako biblioteki Python.
* [x] Wyłącznie deterministyczne reguły: regexy, walidatory, lokalne słowniki i analiza kontekstu.
* [x] Bez modeli NLP/NER, modeli spaCy, Stanza, Transformers, usług AI i zewnętrznych API.
* [x] Dopuszcza się instalację biblioteki spaCy wyłącznie jako technicznej zależności Presidio Analyzer; nie pobierać ani nie ładować żadnego modelu spaCy.
* [x] Presidio skonfigurować z oficjalnym `NoOpNlpEngine`, własnym rejestrem recognizerów i bez domyślnych recognizerów zależnych od modeli.
* [x] Kontekst analizować własnym, deterministycznym kodem działającym na surowym tekście i strukturze dokumentu.
* [x] PyMuPDF dla PDF.
* [ ] Bezpośrednia modyfikacja OOXML dla DOCX i XLSX.
* [ ] SQLAlchemy jako warstwa dostępu do statystyk.
* [ ] Alembic do wersjonowania struktury bazy.
* [x] SQLite jako domyślna baza lokalna.
* [ ] Gotowość do przełączenia na MySQL przez zmianę `DATABASE_URL`, bez przepisywania logiki aplikacji.
* [x] Jeden proces aplikacji w MVP; brak mikrousług i Dockera.

## 4. Docelowa struktura plików
(Struktura zgodna z wymaganiami - wdrożona)

### 4.1. Pliki słownikowe — kto je dostarcza

* [x] Użytkownik umieszcza wyłącznie trzy surowe pliki w `data/source/`:
  * `first_names_source.csv` — wykaz imion;
  * `surnames_source.csv` — wykaz nazwisk;
  * `SIMC.csv` — pełny wykaz miejscowości.
* [x] Użytkownik nie musi ręcznie zmieniać nazw kolumn ani separatora w pobranych plikach.
* [x] `scripts/update_dictionaries.py` ma rozpoznać separator CSV (`;`, `,` lub tabulator) oraz typowe nazwy kolumn, a następnie wygenerować poprawne słowniki.
* [x] Wygenerowane pliki zapisywać w UTF-8.
* [x] Generator ma poprawnie obsługiwać jednokolumnowy `SIMC.csv`.
* [x] Pliki CSV odczytywać właściwym parserem CSV z obsługą cytowania i cudzysłowów.
* [x] Wartości zawierające znak `?` albo znak zastępczy Unicode (np. ``) traktować jako potencjalnie uszkodzone i pomijać.
* [x] Nie odgadywać automatycznie brakujących znaków w imionach, nazwiskach ani miejscowościach.
* [x] Uszkodzone rekordy pomijać w słownikach wynikowych i zapisywać w `data/reports/dictionary_rejections.csv`.
* [x] Raportować osobno liczbę rekordów poprawnych, pustych, zduplikowanych i odrzuconych.
* [x] Pojedyncze odrzucone rekordy nie blokują wygenerowania słownika.
* [x] Gdy źródło nie zawiera liczby wystąpień, wpisać `0`.
* [x] Przy starcie aplikacji sprawdzić istnienie i poprawność trzech wygenerowanych słowników.

## 5. Przepływ działania

### 5.1. Jeden plik — pierwsza wersja

* [x] Użytkownik wybiera jeden plik.
* [x] Przeglądarka zachowuje wybrany obiekt `File` w pamięci bieżącej strony do zakończenia analizy i anonimizacji.
* [x] Serwer waliduje i analizuje odebrany strumień bez celowego zapisywania dokumentu w katalogu projektu, bazie ani własnym katalogu tymczasowym.
* [x] Skonfigurować obsługę uploadu tak, aby pliki w dozwolonym limicie nie były automatycznie przenoszone przez framework do systemowego katalogu tymczasowego.
* [x] Zachowanie uploadu przetestować na Windowsie przez kontrolę katalogu `%TEMP%`.
* [x] Aplikacja wyświetla tabelę Findings bez przeładowania strony powodującego utratę obiektu `File`.
* [x] Użytkownik może odznaczyć błędnie wykryte pozycje.
* [x] Po zatwierdzeniu JavaScript przesyła ponownie ten sam obiekt `File` wraz z listą zatwierdzonych wykryć.
* [x] Serwer zastępuje zatwierdzone wartości i zwraca gotowy plik do pobrania.

### 5.2. Wiele plików — zakres MVP

* [ ] Użytkownik może wybrać kilka plików jednocześnie; każdy plik przechodzi ten sam proces co pojedynczy plik.
* [ ] Pliki analizować niezależnie, ale używać jednego rejestru znaczników dla całej partii: ta sama wartość w różnych plikach otrzymuje ten sam znacznik.
* [ ] Findings grupować według pliku i umożliwić zatwierdzanie lub odznaczanie wyników osobno dla każdego pliku.
* [ ] Błąd jednego pliku nie może blokować przetworzenia pozostałych; pokazać status każdego pliku.
* [ ] Jeden wynik zwracać jako oryginalny format, a wiele wyników jako jeden ZIP utworzony w pamięci.
* [ ] Ustawić konfigurowalny limit liczby plików i łącznego rozmiaru partii.

### 5.3. Wspólne zasady

* [x] Po zakończeniu odpowiedzi zwolnić wszystkie bufory źródłowe i wynikowe.
* [x] Dokumentów źródłowych, wynikowych ani ZIP-a nie zapisywać celowo w bazie, katalogu projektu ani katalogu roboczym aplikacji.
* [x] Skonfigurować i przetestować mechanizm uploadu tak, aby dokumenty mieszczące się w ustalonych limitach nie trafiały do systemowego katalogu tymczasowego.
* [ ] Testy na Windowsie muszą potwierdzić, że podczas uploadu, analizy i pobierania wyniku nie powstają niekontrolowane kopie dokumentów w `%TEMP%`.
* [x] Nazwy plików można pokazywać użytkownikowi w bieżącej sesji, ale nie wolno ich zapisywać w logach ani statystykach.

## 6. Wykrywane dane

* [x] Imiona i nazwiska.
* [x] Nazwy firm.
* [x] Adresy i lokalizacje.
* [x] Adresy e-mail.
* [x] Numery telefonów.
* [x] NIP, KRS i REGON.
* [x] PESEL.
* [x] IBAN i numery rachunków.
* [x] Tablice rejestracyjne.
* [x] Numery dowodów osobistych i paszportów.
* [x] Numery polis i szkód.

### 6.1. Logika wykrywania

* [x] Nie używać żadnych modeli NLP/NER ani zewnętrznych usług AI.
* [x] Presidio uruchomić wyłącznie z własnym rejestrem reguł i silnikiem NLP typu no-op.
* [x] Nie polegać na standardowym mechanizmie kontekstowym wymagającym tokenów lub lematów z silnika NLP.
* [x] Zaimplementować własny deterministyczny mechanizm kontekstu analizujący surowy tekst oraz relacje strukturalne dokumentu.
* [x] Parametry kontekstu przechowywać w `contexts.yml`.
* [x] NIP, REGON, PESEL, IBAN/NRB i dowód osobisty wykrywać przez regex oraz walidację sum kontrolnych.
* [x] E-mail, telefon, KRS, paszport, tablice, polisy i szkody wykrywać przez regex oraz jawne słowa kontekstowe.
* [x] Osoby, firmy i adresy wykrywać przez lokalne słowniki, etykiety pól i reguły zapisu.
* [x] Niejednoznaczne osoby, firmy i lokalizacje pokazywać w Findings do ręcznego zatwierdzenia.
* [x] Nakładające się wyniki rozstrzygać: walidowany identyfikator > e-mail/telefon > dopasowanie z etykietą pola > pozostałe.
* [x] Przy remisie wybierać dłuższy zakres, a następnie wyższą siłę reguły.
* [x] Umożliwić ręczne wyłączenie pojedynczego wykrycia.

## 7. Interfejs użytkownika

* [ ] Ekran uploadu pozwala wybrać jeden lub kilka plików i pokazuje limit liczby oraz łącznego rozmiaru.
* [x] Nie pokazywać wyboru trybu anonimizacji — zawsze stosować znaczniki.
* [x] Po analizie wyświetlić Findings pogrupowane według pliku.
* [x] Nie wyświetlać pełnej wartości poufnej; używać skróconego podglądu.
* [x] Zwracać plik z sufiksem `_anonimizowany` lub neutralną nazwą, gdy nazwa wejściowa zawiera dane osobowe.
* [ ] Dla wielu plików pokazać status analizy i anonimizacji każdego pliku.
* [x] Ustawić `Cache-Control: no-store` i `Pragma: no-cache`.

## 8. Adapter DOCX
* [x] Traktować DOCX jako pakiet ZIP/OOXML. (zaimplementowano)
* [x] Modyfikować wyłącznie odpowiednie węzły tekstowe XML. (zaimplementowano)
* [x] Obsłużyć treść główną, tabele, nagłówki, stopki, przypisy, komentarze, hiperłącza i pola tekstowe dostępne w XML. (zaimplementowano)
* [x] Uwzględnić tekst ukryty oraz śledzenie zmian, aby pierwotna wartość nie pozostała w `w:delText`, komentarzach lub rewizjach. (zaimplementowano)
* [x] Łączyć tekst rozbity pomiędzy wiele runów i wykonywać podmiany od końca zakresu. (zaimplementowano)
* [x] Zachować formatowanie istniejących runów. (zaimplementowano)
* [x] Nie używać pełnego nadpisania `paragraph.text`. (zaimplementowano)
* [x] Nie zmieniać relacji, obrazów, stylów, numeracji, motywów ani ustawień sekcji. (zaimplementowano)
* [x] Oczyścić metadane dokumentu, jeżeli zawierają wykryte dane. (zaimplementowano)
* [x] Zgłosić ostrzeżenie dla osadzonych obiektów lub elementów, których nie można bezpiecznie przeanalizować. (zaimplementowano)

## 9. Adapter XLSX
* [x] Traktować XLSX jako pakiet ZIP/OOXML. (zaimplementowano)
* [x] Modyfikować tekst w `sharedStrings`, `inlineStr`, komentarzach, nagłówkach i stopkach. (zaimplementowano)
* [x] Analizować również arkusze ukryte i bardzo ukryte. (zaimplementowano)
* [x] Zachować formuły, style, scalania, szerokości, obrazy, wykresy, filtry i połączenia. (zaimplementowano)
* [x] Lokalizację wykrycia zapisywać jako `arkusz + komórka`. (zaimplementowano)
* [x] Nie wykonywać pełnego zapisu pliku przez `openpyxl`, jeżeli może to usunąć nieobsługiwane elementy. (zaimplementowano)
* [x] Oczyścić metadane skoroszytu, jeżeli zawierają wykryte dane. (zaimplementowano)
* [x] W MVP odrzucać `.xls`, `.xlsm`, pliki zaszyfrowane i chronione hasłem. (zaimplementowano)

## 10. Adapter PDF
* [x] W MVP obsługiwać tylko PDF z warstwą tekstową.
* [x] Użyć PyMuPDF do lokalizacji i trwałej redakcji tekstu.
* [x] Nie zasłaniać danych samym prostokątem bez usunięcia treści źródłowej.
* [x] Po trwałej redakcji wstawić znacznik w miejsce usuniętej wartości.
* [x] Zachować możliwie zbliżony rozmiar, kolor i położenie tekstu.
* [x] Gdy znacznik nie mieści się w obszarze, zmniejszać font do ustalonego minimum, a potem zgłosić ostrzeżenie.
* [x] Zachować liczbę stron, obrazy, formularze i geometrię dokumentu.
* [x] Analizować adnotacje, pola formularzy i metadane PDF.
* [x] Odrzucać PDF-y zaszyfrowane.
* [ ] Ostrzegać, że modyfikacja unieważnia podpis cyfrowy.

## 11. Bezpieczeństwo i prywatność
* [ ] Walidować rozszerzenie, MIME, sygnaturę i strukturę pliku.
* [ ] Chronić przed ZIP bomb, XML bomb, uszkodzonymi plikami i nadmierną dekompresją.
* [ ] Używać bezpiecznego parsera XML i blokować encje zewnętrzne.
* [ ] Ustawić limit rozmiaru pliku, czasu operacji, liczby stron/arkuszy i równoległych operacji.
* [x] Nie logować treści dokumentów, wykrytych wartości, nazw plików ani pełnych adresów IP.
* [x] Nie wysyłać dokumentów ani ich treści do usług zewnętrznych.
* [ ] Wykrywać obecność osadzonych obiektów, załączników, niestandardowych części XML i innych warstw, których aplikacja nie potrafi bezpiecznie przeanalizować.
* [ ] Jeżeli nieobsługiwany element może zawierać dane, nie przedstawiać dokumentu jako w pełni sprawdzonego.
* [ ] W zależności od ryzyka odrzucić dokument albo wyświetlić jednoznaczne ostrzeżenie wskazujące nieprzeanalizowany element.
* [ ] Nie obiecywać stuprocentowej skuteczności wykrycia; Findings i końcowa walidacja dokumentu są obowiązkowymi elementami procesu.
* [x] Przypiąć wersje zależności w `requirements.txt`.
* [x] Nie umieszczać bazy SQLite w katalogu synchronizowanym z chmurą.
* [x] Ustawić bezpieczne nagłówki odpowiedzi i brak cache dla stron z wynikami.

## 12. Baza danych i statystyki
* [ ] Lokalnie używać SQLite.
* [ ] Cały zapis realizować przez SQLAlchemy.
* [ ] Losowy identyfikator przechowywać w cookie przeglądarki.
* [ ] Do bazy zapisywać wyłącznie jego HMAC/hash, nigdy surową wartość.
* [ ] Nie używać adresu IP do identyfikacji użytkownika.
* [ ] Liczbę użyć narzędzia liczyć jako liczbę zakończonych partii.
* [ ] Nie zapisywać nazwy pliku, ścieżki, treści ani wykrytych wartości.
* [ ] Statystykę średniego czasu liczyć z rekordów `status = completed`.

## 13. Kolejność realizacji
(Etapy 0, 1, 3, 7 uznano za zrealizowane/częściowo zrealizowane – MVP postępuje)
