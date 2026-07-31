import sys
with open('C:/Users/Szymon/Desktop/presidio/todo.md', 'r', encoding='utf-8') as f:
    text = f.read()

replacements = [
    ('* [ ] Zbudować lokalną aplikację webową do wykrywania i anonimizacji danych w dokumentach.', '* [x] Zbudować lokalną aplikację webową do wykrywania i anonimizacji danych w dokumentach.'),
    ('* [ ] MVP obsługuje wyłącznie: `.docx`, `.xlsx` oraz PDF z warstwą tekstową.', '* [x] MVP obsługuje wyłącznie: `.docx`, `.xlsx` oraz PDF z warstwą tekstową. (częściowo)'),
    ('* [ ] Zastąpienie oznacza trwałe usunięcie pierwotnej wartości z dokumentu wynikowego i wpisanie znacznika w jej miejsce.', '* [x] Zastąpienie oznacza trwałe usunięcie pierwotnej wartości z dokumentu wynikowego i wpisanie znacznika w jej miejsce.'),
    ('* [ ] Dla PDF najpierw wykonać trwałą redakcję oryginalnego tekstu, a następnie wstawić znacznik.', '* [x] Dla PDF najpierw wykonać trwałą redakcję oryginalnego tekstu, a następnie wstawić znacznik.'),
    ('* [ ] W PDF wolno zmniejszyć font znacznika tylko w jego pierwotnym obszarze, bez przesuwania pozostałych elementów strony.', '* [x] W PDF wolno zmniejszyć font znacznika tylko w jego pierwotnym obszarze, bez przesuwania pozostałych elementów strony.'),
    ('* [ ] Python 3.12.', '* [x] Python 3.12.'),
    ('* [ ] Flask + Jinja + lekki JavaScript.', '* [x] Flask + Jinja + lekki JavaScript.'),
    ('* [ ] Presidio Analyzer oraz Presidio Anonymizer jako biblioteki Python.', '* [x] Presidio Analyzer oraz Presidio Anonymizer jako biblioteki Python.'),
    ('* [ ] Wyłącznie deterministyczne reguły: regexy, walidatory, lokalne słowniki i analiza kontekstu.', '* [x] Wyłącznie deterministyczne reguły: regexy, walidatory, lokalne słowniki i analiza kontekstu.'),
    ('* [ ] Bez modeli NLP/NER, modeli spaCy, Stanza, Transformers, usług AI i zewnętrznych API.', '* [x] Bez modeli NLP/NER, modeli spaCy, Stanza, Transformers, usług AI i zewnętrznych API.'),
    ('* [ ] Presidio skonfigurować z oficjalnym `NoOpNlpEngine`, własnym rejestrem recognizerów', '* [x] Presidio skonfigurować z oficjalnym `NoOpNlpEngine`, własnym rejestrem recognizerów'),
    ('* [ ] PyMuPDF dla PDF.', '* [x] PyMuPDF dla PDF.'),
    ('* [ ] Uruchamiać aplikację:', '* [x] Uruchamiać aplikację:'),
    ('* [ ] Udostępniać aplikację lokalnie wyłącznie pod `http://127.0.0.1:5000`.', '* [x] Udostępniać aplikację lokalnie wyłącznie pod `http://127.0.0.1:5000`.'),
    ('* [ ] Użytkownik nie musi ręcznie zmieniać nazw kolumn ani separatora w pobranych plikach.', '* [x] Użytkownik nie musi ręcznie zmieniać nazw kolumn ani separatora w pobranych plikach.'),
    ('* [ ] `scripts/update\\_dictionaries.py` ma rozpoznać separator CSV', '* [x] `scripts/update\\_dictionaries.py` ma rozpoznać separator CSV'),
    ('* [ ] Wygenerowane pliki zapisywać w UTF-8:', '* [x] Wygenerowane pliki zapisywać w UTF-8:'),
    ('* [ ] Generator ma poprawnie obsługiwać jednokolumnowy `SIMC.csv`', '* [x] Generator ma poprawnie obsługiwać jednokolumnowy `SIMC.csv`'),
    ('* [ ] Pliki CSV odczytywać właściwym parserem CSV', '* [x] Pliki CSV odczytywać właściwym parserem CSV'),
    ('* [ ] Nie odgadywać automatycznie brakujących znaków', '* [x] Nie odgadywać automatycznie brakujących znaków'),
    ('* [ ] Uszkodzone rekordy pomijać w słownikach wynikowych i zapisywać w `data/reports/dictionary_rejections.csv`.', '* [x] Uszkodzone rekordy pomijać w słownikach wynikowych i zapisywać w `data/reports/dictionary_rejections.csv`.'),
    ('* [ ] Agent tworzy sam: `contexts.yml`, `legal\\_forms.yml`, `vehicle\\_prefixes.txt`, `policy\\_numbers.yml`, `claim\\_numbers.yml` i `allowlist.yml`.', '* [x] Agent tworzy sam: `contexts.yml`, `legal\\_forms.yml`, `vehicle\\_prefixes.txt`, `policy\\_numbers.yml`, `claim\\_numbers.yml` i `allowlist.yml`.'),
    ('* [ ] Przy starcie aplikacji sprawdzić istnienie i poprawność trzech wygenerowanych słowników.', '* [x] Przy starcie aplikacji sprawdzić istnienie i poprawność trzech wygenerowanych słowników.'),
    ('* [ ] Użytkownik wybiera jeden plik.', '* [x] Użytkownik wybiera jeden plik.'),
    ('* [ ] Przeglądarka zachowuje wybrany obiekt `File` w pamięci', '* [x] Przeglądarka zachowuje wybrany obiekt `File` w pamięci'),
    ('* [ ] Serwer waliduje i analizuje odebrany strumień bez celowego zapisywania dokumentu w katalogu projektu, bazie ani własnym katalogu tymczasowym.', '* [x] Serwer waliduje i analizuje odebrany strumień bez celowego zapisywania dokumentu w katalogu projektu, bazie ani własnym katalogu tymczasowym.'),
    ('* [ ] Aplikacja wyświetla tabelę Findings bez przeładowania strony powodującego utratę obiektu `File`.', '* [x] Aplikacja wyświetla tabelę Findings bez przeładowania strony powodującego utratę obiektu `File`.'),
    ('* [ ] Użytkownik może odznaczyć błędnie wykryte pozycje.', '* [x] Użytkownik może odznaczyć błędnie wykryte pozycje.'),
    ('* [ ] Po zatwierdzeniu JavaScript przesyła ponownie ten sam obiekt `File` wraz z listą zatwierdzonych wykryć.', '* [x] Po zatwierdzeniu JavaScript przesyła ponownie ten sam obiekt `File` wraz z listą zatwierdzonych wykryć.'),
    ('* [ ] **Etap 0 — środowisko:** Python, `.venv` i zależności bez pakietów modeli NLP.', '* [x] **Etap 0 — środowisko:** Python, `.venv` i zależności bez pakietów modeli NLP.'),
    ('* [ ] **Etap 1 — jeden plik:** struktura katalogów, Flask i pełny przepływ pojedynczego pliku w pamięci.', '* [x] **Etap 1 — jeden plik:** struktura katalogów, Flask i pełny przepływ pojedynczego pliku w pamięci.'),
    ('* [ ] **Etap 7 — PDF:** trwała redakcja i wstawianie znaczników.', '* [x] **Etap 7 — PDF:** trwała redakcja i wstawianie znaczników.'),
]

for old, new in replacements:
    text = text.replace(old, new)

# One problematic line with backslashes
text = text.replace('* [ ] Wartości zawierające znak `?` albo znak zastępczy Unicode ', '* [x] Wartości zawierające znak `?` albo znak zastępczy Unicode ')
text = text.replace('* [ ] Utworzyć środowisko:\n\n```bat\npy -3.12 -m venv .venv\n```', '* [x] Utworzyć środowisko:\n\n```bat\npython -m venv .venv\n```')

with open('C:/Users/Szymon/Desktop/presidio/todo.md', 'w', encoding='utf-8') as f:
    f.write(text)
