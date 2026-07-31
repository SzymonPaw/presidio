# Reguły wykrywania danych — bez modeli AI

## 1\. Zasady wspólne

* Używać wyłącznie kodu: regexów, sum kontrolnych, lokalnych słowników i jawnego kontekstu.
* Nie instalować ani nie uruchamiać modeli spaCy, Stanza, Transformers, Torch, modeli NER ani zewnętrznych API.
* Biblioteka spaCy może zostać zainstalowana wyłącznie jako techniczna zależność oficjalnego pakietu Presidio Analyzer. Nie wolno pobierać ani ładować modeli spaCy ani wykorzystywać spaCy do NER, analizy językowej lub rozpoznawania danych.
* Presidio skonfigurować z własnym rejestrem recognizerów oraz oficjalnym silnikiem `NoOpNlpEngine`.
* Nie ładować domyślnych recognizerów wymagających modeli NLP.
* Słowa kontekstowe analizować własnym, deterministycznym mechanizmem działającym na surowym tekście i strukturze dokumentu.
* Nie polegać na standardowym `LemmaContextAwareEnhancer`, tokenach ani lematach generowanych przez silnik NLP.
* Mechanizm kontekstowy ma sprawdzać zdefiniowane okno znaków lub słów przed i po kandydacie oraz relacje strukturalne, takie jak ta sama komórka, sąsiednia komórka, ten sam wiersz, akapit lub pole formularza.
* Wielkość okna kontekstowego i lista etykiet mają być konfigurowalne w `contexts.yml`.
* Każdy wynik zawiera: `entity\_type`, zakres tekstu, wartość znormalizowaną, `rule\_score` i opis reguły.
* `rule\_score` jest stałą siłą reguły, a nie wynikiem modelu AI:

  * `0.90–1.00` — poprawny format i walidacja;
  * `0.75–0.89` — format oraz mocny kontekst;
  * `0.55–0.74` — dopasowanie niejednoznaczne, wymagające zatwierdzenia w Findings.
* Ta sama znormalizowana wartość otrzymuje ten sam znacznik w całej partii plików.
* Reguły i słowniki przechowywać lokalnie w YAML/TXT, aby można je było rozbudowywać bez zmiany kodu.

## 2\. Pliki słownikowe i ich przygotowanie

### 2.1. Pliki dostarczane przez użytkownika

Użytkownik zapisuje wyłącznie trzy surowe pliki:

```text
data/source/
├── first\_names\_source.csv
├── surnames\_source.csv
└── SIMC.csv
```

* `first\_names\_source.csv` — wykaz imion;
* `surnames\_source.csv` — wykaz nazwisk;
* `SIMC.csv` — pełny wykaz miejscowości SIMC/TERYT.
* Pliki mogą używać separatora `;`, `,` albo tabulatora i mogą zawierać dodatkowe kolumny.
* Użytkownik nie musi ręcznie przerabiać oficjalnych plików źródłowych.

### 2.2. Pliki generowane przez aplikację

Skrypt `scripts/update\_dictionaries.py` generuje:

```text
config/recognizers/
├── first\_names.csv
├── surnames.csv
└── localities.txt
```

Docelowy format `first\_names.csv`:

```csv
name;count
JAN;504123
ANNA;489210
```

Docelowy format `surnames.csv`:

```csv
surname;count
NOWAK;203456
KOWALSKI;137981
```

Docelowy format `localities.txt`:

```text
warszawa
kraków
nowy sącz
```

Zasady generatora:

* zapisywać pliki w UTF-8;
* rozpoznawać separator `;`, `,` lub tabulator;
* dla imion szukać kolumn odpowiadających nazwom `name`, `imie`, `imię`;
* dla nazwisk szukać kolumn `surname`, `nazwisko`;
* dla liczby wystąpień szukać `count`, `liczba`, `liczba\_wystapien`; brak wartości zastąpić `0`;
* dla SIMC odnaleźć kolumnę zawierającą nazwę miejscowości, ignorując pozostałe kolumny;
* usuwać puste rekordy, duplikaty i nadmiarowe spacje;
* imiona i nazwiska zapisywać wielkimi literami, miejscowości małymi literami;
* zachować polskie znaki; nie usuwać łączników ani apostrofów.
* używać parsera CSV obsługującego poprawne cytowanie i cudzysłowy wewnątrz wartości; nie przetwarzać plików przez zwykłe dzielenie wiersza po separatorze;
* obsłużyć jednokolumnowy `SIMC.csv`; jeżeli plik zawiera jedną rozpoznaną kolumnę z nazwą miejscowości, brak separatora nie jest błędem;
* wykrywać wartości zawierające znak `?` albo znak zastępczy Unicode ``;
* nie próbować automatycznie odtwarzać brakujących znaków;
* pomijać uszkodzone rekordy w słowniku wynikowym;
* zapisywać odrzucone rekordy wraz z nazwą pliku, numerem wiersza, wartością źródłową i powodem odrzucenia do `data/reports/dictionary\_rejections.csv`;
* wyświetlać podsumowanie liczby rekordów poprawnych, zduplikowanych, pustych i odrzuconych.

Jeżeli skrypt nie rozpozna wymaganej kolumny albo znajdzie więcej niż jedną równie prawdopodobną kolumnę, ma zakończyć działanie jasnym błędem z nazwą pliku i listą znalezionych kolumn. Pojedyncze uszkodzone rekordy nie blokują wygenerowania słownika, ale muszą zostać pominięte i zapisane w raporcie odrzuceń.

### 2.3. Pliki tworzone przez agenta

Agent tworzy i uzupełnia:

```text
config/recognizers/
├── contexts.yml
├── legal\_forms.yml
├── vehicle\_prefixes.txt
├── policy\_numbers.yml
├── claim\_numbers.yml
└── allowlist.yml
```

* `contexts.yml` — etykiety pól, słowa kontekstowe, kierunek wyszukiwania, dopuszczalna odległość oraz zakres strukturalny, np. ta sama komórka, sąsiednia komórka, ten sam wiersz, akapit lub pole;
* `legal\_forms.yml` — pełne nazwy i skróty form prawnych;
* `vehicle\_prefixes.txt` — polskie prefiksy tablic;
* `policy\_numbers.yml` i `claim\_numbers.yml` — reguły ogólne oraz późniejsze wzorce konkretnych ubezpieczycieli;
* `allowlist.yml` — świadomie pomijane wartości; początkowo pusta lista.

### 2.4. Kontrola przy starcie

* Wczytać wygenerowane słowniki do zbiorów `set`.
* Jeżeli `first\_names.csv`, `surnames.csv` lub `localities.txt` nie istnieje, automatycznie spróbować uruchomić `update\_dictionaries.py`.
* Jeżeli brakuje pliku źródłowego albo generator zwróci błąd, nie uruchamiać aplikacji i pokazać dokładną instrukcję, który plik należy umieścić w `data/source/`.
* Liczbę wystąpień wykorzystywać jedynie do obniżenia siły bardzo rzadkich i niejednoznacznych dopasowań; nie traktować jej jako warunku koniecznego.


## 2.5. Deterministyczna analiza kontekstu

* Analiza kontekstu nie może zależeć od modelu NLP, lem taktyzacji ani rozpoznawania części mowy.
* Każdy recognizer wymagający kontekstu otrzymuje:
* &#x20; surowy tekst analizowanego fragmentu;
* &#x20; pozycję początku i końca kandydata;
* &#x20; informację o miejscu w dokumencie;
* &#x20; informacje strukturalne przekazane przez adapter dokumentu.
* Mechanizm sprawdza słowa i etykiety przed oraz po kandydacie w konfigurowalnym oknie.
* Dopasowanie słowa kontekstowego ma uwzględniać wielkość liter, polskie znaki, typowe skróty oraz interpunkcję zgodnie z konfiguracją.
* Kontekst w tej samej komórce, polu lub bezpośrednio po etykiecie ma pierwszeństwo przed kontekstem znajdującym się dalej w akapicie.
* Adaptery DOCX, XLSX i PDF powinny przekazywać strukturę dokumentu, aby możliwe było rozróżnienie tekstu z tej samej komórki, wiersza, akapitu lub strony.
* Samo wystąpienie słowa kontekstowego w odległej części dokumentu nie może zwiększać `rule\_score`.

## 3\. Imiona i nazwiska

**Typ:** `PERSON` — **znacznik:** `\[OSOBA\_1]`

Stosować trzy poziomy reguł:

### A. Pola jednoznaczne — automatyczna podmiana

Wykrywać tekst po etykietach lub w sąsiedniej komórce tabeli:

* `imię`, `nazwisko`, `imię i nazwisko`;
* `ubezpieczony`, `ubezpieczająca`, `poszkodowany`;
* `pełnomocnik`, `reprezentowany przez`, `osoba kontaktowa`;
* `pracownik`, `kierowca`, `właściciel`, `podpis`.

Reguły:

* po `Imię:` zaakceptować jeden wyraz znajdujący się w `first\_names.csv`;
* po `Nazwisko:` zaakceptować jeden lub dwa wyrazy znajdujące się w `surnames.csv`;
* po etykiecie osoby zaakceptować 2–4 człony, jeśli pierwszy jest imieniem, a ostatni nazwiskiem;
* `Jan` i `Kowalski` znajdujące się w sąsiednich polach tego samego wiersza/sekcji otrzymują ten sam znacznik;
* tytuły `Pan`, `Pani`, `dr`, `mgr`, `mec.` pozostają w dokumencie i nie wchodzą do zakresu podmiany.

`rule\_score = 0.90–0.98`.

### B. Imię + nazwisko w zwykłym tekście — Findings

Kandydat musi spełnić wszystkie warunki:

1. zawiera 2–4 człony;
2. pierwszy człon występuje w `first\_names.csv`;
3. ostatni człon występuje w `surnames.csv`;
4. człony są zapisane jako `Jan Kowalski`, `JAN KOWALSKI` albo zawierają poprawny łącznik, np. `Anna Maria Nowak-Kowalska`;
5. kandydat nie zawiera formy prawnej, prefiksu adresowego ani słowa z allowlisty.

Bez etykiety: `rule\_score = 0.65–0.74` i obowiązkowe zatwierdzenie w Findings.

### C. Odmiany fleksyjne

W MVP nie próbować automatycznie zgadywać wszystkich odmian, np. `Jana Kowalskiego`. Taki zapis wykrywać tylko przy mocnym kontekście osobowym albo pozostawić do ręcznego wskazania. Nie stosować agresywnego dopasowania końcówek, ponieważ generuje dużo fałszywych wyników.

## 4\. Nazwy firm

**Typ:** `ORGANIZATION` — **znacznik:** `\[FIRMA\_1]`

W `legal\_forms.yml` przechowywać co najmniej:

```yaml
- names: \["spółka jawna", "sp. j.", "sp.j.", "sp j"]
- names: \["spółka partnerska", "sp. p.", "sp.p.", "sp p"]
- names: \["spółka komandytowa", "sp. k.", "sp.k.", "sp k"]
- names: \["spółka komandytowo-akcyjna", "S.K.A.", "S.K.A", "SKA", "sp.k.a."]
- names: \["spółka z ograniczoną odpowiedzialnością", "sp. z o.o.", "sp. z o.o", "sp z o.o.", "sp z oo"]
- names: \["prosta spółka akcyjna", "P.S.A.", "P.S.A", "PSA"]
- names: \["spółka akcyjna", "S.A.", "S.A", "SA"]
```

Dodatkowo można zachować: `fundacja`, `stowarzyszenie`, `TUW`, `TUiR`.

### Reguła z formą prawną

* znaleźć formę prawną bez względu na wariant kropek i spacji;
* pobrać nazwę z tego samego wiersza, akapitu lub komórki;
* domyślnie pobrać maksymalnie 12 wyrazów przed formą prawną;
* zatrzymać zakres na: początku pola, nowej linii, średniku, etykiecie `NIP/KRS/REGON/adres`, dwukropku rozpoczynającym inne pole;
* dopuścić litery, cyfry, cudzysłowy, `\&`, `+`, myślniki i apostrofy;
* jeżeli forma prawna występuje na początku, pobrać nazwę po niej tylko przy etykiecie `firma`, `nazwa`, `spółka` albo w osobnym polu tabeli;
* nie podmieniać samej formy prawnej bez nazwy.

Nazwa + forma prawna: `rule\_score = 0.92`.

### Reguła bez formy prawnej

Wykrywać tylko:

* wartość po `firma`, `nazwa firmy`, `ubezpieczyciel`, `kontrahent`, `sprzedawca`, `nabywca`;
* nazwę znajdującą się w tym samym bloku co NIP, KRS lub REGON.

Bez formy prawnej, ale z mocną etykietą: `0.82–0.88`. Bez etykiety i bez formy prawnej — nie wykrywać automatycznie.

## 5\. Adresy i lokalizacje

### Słownik miejscowości

`localities.txt` nie powinien zawierać tylko największych miast. Powinien być generowany z pełnego aktualnego wykazu SIMC/TERYT i zawierać unikalne, znormalizowane nazwy miast, wsi, osad i innych miejscowości.

Przykład zawartości:

```text
warszawa
kraków
nowy sącz
zalesie
stara wieś
...
```

Plik `SIMC.csv` zachować jako źródło aktualizacji, a `localities.txt` generować skryptem. Sama obecność wyrazu w słowniku nie wystarcza do automatycznej anonimizacji, ponieważ część nazw miejscowości jest także zwykłymi słowami lub nazwiskami.

### Adres

**Typ:** `ADDRESS` — **znacznik:** `\[ADRES\_1]`

Łączyć sąsiadujące elementy:

* prefiks: `ul.`, `al.`, `aleja`, `pl.`, `plac`, `os.`, `osiedle`, `rondo`, `skwer`, `bulwar`;
* nazwa ulicy;
* numer budynku/lokalu: `12`, `12A`, `12/4`, `lok. 4`, `m. 4`;
* kod pocztowy `NN-NNN`;
* miejscowość obecna w `localities.txt`.

Mocny kontekst: `adres`, `zamieszkały`, `siedziba`, `adres korespondencyjny`, `miejsce zdarzenia`.

* pełny adres z ulicą i numerem: `0.92`;
* kod pocztowy + miejscowość: `0.90`;
* miejscowość po etykiecie adresowej: `0.85`;
* sama miejscowość w zwykłym zdaniu: maks. `0.60`, tylko Findings.

### Lokalizacja

**Typ:** `LOCATION` — **znacznik:** `\[LOKALIZACJA\_1]`

Automatycznie wykrywać nazwę ze słownika tylko po etykietach `miejscowość`, `miejsce zdarzenia`, `lokalizacja`, `województwo` albo jako część kompletnego adresu. Nie anonimizować każdej nazwy miasta znalezionej w swobodnym tekście.

## 6\. Adresy e-mail

**Typ:** `EMAIL\_ADDRESS` — **znacznik:** `\[EMAIL\_1]`

```regex
(?i)(?<!\[\\w.+-])\[A-Z0-9.\_%+-]+@\[A-Z0-9.-]+\\.\[A-Z]{2,63}(?!\[\\w.-])
```

* Usunąć z zakresu końcową interpunkcję.
* Normalizacja: małe litery.
* `rule\_score = 0.98`.

## 7\. Numery telefonów

**Typ:** `PHONE\_NUMBER` — **znacznik:** `\[TELEFON\_1]`

```regex
(?<!\\d)(?:\\+48\[\\s.-]?)?(?:\\d\[\\s().-]?){9}(?!\\d)
```

* Po normalizacji zaakceptować dokładnie 9 cyfr albo `+48` + 9 cyfr.
* Numer bez `+48` wymaga kontekstu: `tel`, `telefon`, `kom.`, `kontakt`, `fax`.
* Odrzucać kandydatów będących częścią PESEL, NIP, REGON, KRS, rachunku lub daty.
* Z `+48`: `0.95`; bez prefiksu, ale z kontekstem: `0.85`.

## 8\. NIP, KRS i REGON

### NIP

**Typ:** `PL\_NIP` — **znacznik:** `\[NIP\_1]`

* 10 cyfr, opcjonalnie ze spacjami lub myślnikami.
* Wagi: `6,5,7,2,3,4,5,6,7`.
* `suma % 11` musi równać się ostatniej cyfrze; wynik `10` jest błędny.
* Poprawny: `0.99`; błędny odrzucić.

### KRS

**Typ:** `PL\_KRS` — **znacznik:** `\[KRS\_1]`

```regex
(?i)\\bKRS\\s\*\[:#-]?\\s\*(\\d{10})\\b
```

* Dokładnie 10 cyfr i obowiązkowy kontekst `KRS`/`Krajowy Rejestr Sądowy`.
* `rule\_score = 0.95`.

### REGON

**Typ:** `PL\_REGON` — **znacznik:** `\[REGON\_1]`

* 9 albo 14 cyfr.
* REGON 9: wagi `8,9,2,3,4,5,6,7`.
* REGON 14: wagi `2,4,8,5,0,9,7,3,6,1,2,4,8`.
* Reszta `10` oznacza cyfrę kontrolną `0`.
* Poprawny: `0.99`; błędny odrzucić.

## 9\. PESEL

**Typ:** `PL\_PESEL` — **znacznik:** `\[PESEL\_1]`

* Dokładnie 11 cyfr.
* Sprawdzić zakodowaną datę i kod stulecia.
* Wagi: `1,3,7,9,1,3,7,9,1,3`.
* Cyfra kontrolna: `(10 - suma % 10) % 10`.
* Poprawna data i suma: `rule\_score = 1.00`; błędny odrzucić.

## 10\. IBAN i numery rachunków

**Typ:** `BANK\_ACCOUNT` — **znacznik:** `\[RACHUNEK\_1]`

* Polski IBAN: `PL` + 26 cyfr.
* NRB: 26 cyfr bez `PL`.
* Usunąć spacje, zamienić litery na wielkie i walidować `mod 97`.
* NRB walidować po dodaniu `PL`.
* NRB bez `PL` wymaga kontekstu `rachunek`, `konto`, `IBAN`, `NRB`, `przelew`.
* Poprawny: `rule\_score = 1.00`.

## 11\. Tablice rejestracyjne

**Typ:** `LICENSE\_PLATE` — **znacznik:** `\[REJESTRACJA\_1]`

```regex
(?<!\[A-Z0-9])\[A-Z]{2,3}\[ -]?\[A-Z0-9]{4,5}(?!\[A-Z0-9])
```

* Sprawdzić początek względem lokalnego `vehicle\_prefixes.txt`.
* Automatycznie zaakceptować tylko przy etykiecie `nr rejestracyjny`, `nr rej.`, `rejestracja` lub kontekście `pojazd`, `samochód`, `tablica`.
* Z prawidłowym prefiksem i kontekstem: `0.90`; bez kontekstu: maks. `0.60`, tylko Findings.

## 12\. Dowody osobiste i paszporty

### Dowód osobisty

**Typ:** `PL\_ID\_CARD` — **znacznik:** `\[DOWOD\_1]`

```regex
(?<!\[A-Z0-9])\[A-Z]{3}\\s?\\d{6}(?!\[A-Z0-9])
```

* Mapowanie liter `A=10 ... Z=35`.
* Wagi: `7,3,1,9,7,3,1,7,3`.
* Suma ważona podzielna przez 10.
* Poprawny: `0.99`.

### Paszport

**Typ:** `PL\_PASSPORT` — **znacznik:** `\[PASZPORT\_1]`

```regex
(?<!\[A-Z0-9])\[A-Z]{2}\\s?\\d{7}(?!\[A-Z0-9])
```

* Wymaga etykiety `paszport`, `nr paszportu`, `dokument paszportowy` lub `seria i numer` w polu paszportowym.
* Z kontekstem: `0.90`; bez kontekstu tylko Findings z `0.60`.

## 13\. Numery polis i szkód

Nie ma jednego uniwersalnego formatu. Reguły przechowywać w YAML według ubezpieczyciela.

### Polisa

**Typ:** `POLICY\_NUMBER` — **znacznik:** `\[POLISA\_1]`

Fallback wyłącznie po etykiecie:

```regex
(?i)\\b(?:polisa|nr polisy|numer polisy)\\s\*\[:#-]?\\s\*(\[A-Z0-9]\[A-Z0-9./\_-]{4,30})\\b
```

### Szkoda

**Typ:** `CLAIM\_NUMBER` — **znacznik:** `\[SZKODA\_1]`

```regex
(?i)\\b(?:szkoda|nr szkody|numer szkody|roszczenie)\\s\*\[:#-]?\\s\*(\[A-Z0-9]\[A-Z0-9./\_-]{4,30})\\b
```

* Jeżeli wartość pasuje do obu typów, wygrywa najbliższa etykieta.
* Odrzucać daty, NIP, PESEL, telefon, e-mail i URL.
* Nowe formaty dodawać w YAML, bez zmiany kodu.

## 14\. Priorytet implementacji

1. PESEL, NIP, REGON, IBAN/NRB, dowód — regex + walidator.
2. E-mail, telefon, KRS, paszport — regex + kontekst.
3. Polisy, szkody i tablice — konfigurowalne reguły.
4. Adresy — składanie elementów i słownik miejscowości.
5. Osoby i firmy — pola, etykiety, słowniki i ręczna weryfikacja niejednoznacznych wyników.

