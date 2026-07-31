"""Fabryka aplikacji Flask z walidacja slownikow przy starcie."""
import sys
import subprocess
from pathlib import Path

from flask import Flask

from src.settings import (
    REQUIRED_GENERATED_DICTS,
    REQUIRED_SOURCE_FILES,
    SOURCE_DIR,
    RECOGNIZERS_DIR,
    ensure_directories,
    DATABASE_URL,
    FLASK_DEBUG,
    MAX_CONTENT_LENGTH,
    SECRET_KEY,
)


# ---------------------------------------------------------------------------
# Walidatory startowe
# ---------------------------------------------------------------------------
def _check_source_files() -> list[str]:
    """Sprawdza czy istnieja wszystkie trzy pliki zrodlowe.

    Zwraca liste brakujacych plikow (pusta jesli wszystkie obecne).
    """
    missing: list[str] = []
    for file_path in REQUIRED_SOURCE_FILES:
        if not file_path.exists():
            missing.append(str(file_path))
    return missing


def _check_or_generate_dicts() -> list[str]:
    """Sprawdza wygenerowane slowniki, probuje uruchomic generator jesli braki.

    Zwraca liste brakujacych slownikow, ktorych nie udalo sie wygenerowac.
    """
    missing: list[str] = []
    for dict_path in REQUIRED_GENERATED_DICTS:
        if not dict_path.exists():
            missing.append(str(dict_path))

    if missing:
        print("Brakuje wygenerowanych slownikow. Próba uruchomienia generatora...")
        print(f"  Brakujace pliki: {missing}")
        _run_dict_generator()

        missing = []
        for dict_path in REQUIRED_GENERATED_DICTS:
            if not dict_path.exists():
                missing.append(str(dict_path))

    return missing


def _run_dict_generator() -> None:
    """Uruchamia scripts/update_dictionaries.py jako podproces."""
    base_dir = Path(__file__).resolve().parent.parent
    script_path = base_dir / "scripts" / "update_dictionaries.py"
    if not script_path.exists():
        print(f"BLAD: Nie znaleziono skryptu generatora: {script_path}")
        print("Umiesc skrypt update_dictionaries.py w katalogu scripts/.")
        print("Mozesz tez wygenerowac slowniki recznie, uruchamiajac:")
        print(f"  .venv\\Scripts\\python.exe {script_path}")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(base_dir),
        )
        print(result.stdout)
        if result.stderr:
            print(f"Stderr: {result.stderr}")
        if result.returncode != 0:
            print(f"Generator slowników zakonczyl sie bledem (kod: {result.returncode}).")
    except Exception as exc:
        print(f"Nie udalo sie uruchomic generatora slownikow: {exc}")


def _print_missing_files_hint(missing_source: list[str], missing_dicts: list[str]) -> None:
    """Wypisuje czytelny komunikat pomocy o brakujacych plikach."""
    print("\n" + "=" * 60)
    print(" BLAD: Brak wymaganych plików - aplikacja nie zostanie uruchomiona.")
    print("=" * 60)

    if missing_source:
        print("\nBrakujace pliki zrodlowe w data/source/:")
        for f in missing_source:
            name = Path(f).name
            print(f"  - {name}")
        print("\nUmiesc te pliki w katalogu:")
        print(f"  {SOURCE_DIR}")
        print("\nPliki zrodlowe to:")
        print("  first_names_source.csv  - wykaz imion (np. z gov.pl)")
        print("  surnames_source.csv     - wykaz nazwisk (np. z gov.pl)")
        print("  SIMC.csv                - wykaz miejscowosci (np. z gov.pl/TERYT)")

    if missing_dicts:
        print("\nBrakujace wygenerowane slowniki w config/recognizers/:")
        for f in missing_dicts:
            print(f"  - {Path(f).name}")
        print("\nUruchom generator recznie, aby je utworzyc:")
        print(f"  .venv\\Scripts\\python.exe scripts\\update_dictionaries.py")
        print(f"  .venv\\Scripts\\python.exe {Path(__file__).resolve().parent.parent / 'scripts' / 'update_dictionaries.py'}")

    print("\n" + "=" * 60)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Fabryka aplikacji
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    """Tworzy i konfiguruje aplikacje Flask."""
    ensure_directories()

    # --- Walidacja startowa ---
    missing_source = _check_source_files()
    missing_dicts = _check_or_generate_dicts()

    if missing_source or missing_dicts:
        _print_missing_files_hint(missing_source, missing_dicts)

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent.parent / "static"),
    )

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["DEBUG"] = FLASK_DEBUG
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Rejestracja tras
    _register_routes(app)

    return app


def _register_routes(app: Flask) -> None:
    """Rejestruje podstawowe trasy."""
    import json
    import io
    from flask import render_template, send_file, request, jsonify

    from src.documents.pdf_adapter import PdfAdapter
    from src.anonymization.service import AnonymizationService

    pdf_adapter = PdfAdapter()
    anonymizer_service = AnonymizationService()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return {"status": "ok", "message": "Anonimizator dziala"}

    def _get_findings_for_file(file_bytes: bytes, filename: str) -> list[dict]:
        """Ekstrahuje findings z pliku i grupuje je."""
        if filename.lower().endswith(".pdf"):
            raw_findings = anonymizer_service.analyze_pdf(file_bytes)
        else:
            # MVP obsłuży inne formaty później, teraz fallback na tekst
            text = file_bytes.decode("utf-8", errors="ignore")
            raw_findings = anonymizer_service.analyze_text(text)

        # Grupowanie unikalnych znalezisk po (typ, wartosc)
        # Aby kazda unikalna wartosc miala jeden wiersz w tabeli i jeden licznik
        grouped: dict[tuple[str, str], dict] = {}
        for f in raw_findings:
            key = (f["entity_type"], f["raw_value"])
            if key not in grouped:
                grouped[key] = {
                    "entity_type": f["entity_type"],
                    "marker": f["marker"],
                    "score": f["score"],
                    "reason": f["reason"],
                    "raw_value": f["raw_value"],
                    "page": f.get("page", 0),
                    "bbox": f.get("bbox", None),
                    "count": 0
                }
            grouped[key]["count"] += 1

        # Nadajemy identyfikatory i zamieniamy w liste
        result = []
        for idx, (key, value) in enumerate(grouped.items(), start=1):
            value["id"] = str(idx)
            result.append(value)

        return result

    @app.route("/analyze", methods=["POST"])
    def analyze():
        """Prawdziwa trasa analizy pliku."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Pusta nazwa pliku"}), 400

        # Odczyt pliku do pamieci bez zapisu na dysku
        file_bytes = file.read()

        try:
            findings = _get_findings_for_file(file_bytes, file.filename)
            return jsonify({"findings": findings})
        except Exception as exc:
            return jsonify({"error": f"Blad podczas analizy: {str(exc)}"}), 500

    @app.route("/anonymize", methods=["POST"])
    def anonymize():
        """Prawdziwa trasa anonimizacji pliku."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        confirmed_ids_raw = request.form.get("confirmed_ids", "[]")

        try:
            confirmed_ids = json.loads(confirmed_ids_raw)
        except Exception:
            return jsonify({"error": "Niepoprawny format confirmed_ids"}), 400

        # Odczyt pliku do pamieci bez zapisu na dysku
        file_bytes = file.read()

        try:
            # Ponownie analizujemy, aby dostac te same klucze wejsciowe
            findings = _get_findings_for_file(file_bytes, file.filename)

            # Filtrujemy tylko zatwierdzone przez uzytkownika
            confirmed_findings = [f for f in findings if f["id"] in confirmed_ids]

            # Wywolanie odpowiedniego adaptera do modyfikacji dokumentu
            if file.filename.lower().endswith(".pdf"):
                out_bytes = pdf_adapter.anonymize(file_bytes, confirmed_findings)
                mimetype = "application/pdf"
            else:
                # Fallback lub brak wsparcia
                return jsonify({"error": "Obslugiwane sa w tym momencie wylacznie pliki PDF"}), 400

            # Przeslanie gotowego pliku ze zmieniona nazwa
            out_io = io.BytesIO(out_bytes)
            return send_file(
                out_io,
                mimetype=mimetype,
                as_attachment=True,
                download_name=file.filename
            )
        except Exception as exc:
            return jsonify({"error": f"Blad podczas anonimizacji: {str(exc)}"}), 500

    @app.route("/preview_page", methods=["POST"])
    def preview_page():
        """Renderuje podglad strony PDF z zaznaczonymi znaleziskami."""
        if "file" not in request.files or "page" not in request.form:
            return jsonify({"error": "Brak danych"}), 400

        file = request.files["file"]
        page_num = int(request.form.get("page", 0))

        # Pobieramy listy aktywnych i podswietlonych ID z żądania
        active_ids_raw = request.form.get("active_ids", "[]")
        highlight_id = request.form.get("highlight_id", "")

        try:
            active_ids = json.loads(active_ids_raw)
        except Exception:
            active_ids = []

        file_bytes = file.read()

        import traceback
        try:
            # Ponowna analiza aby miec findings z bboxami
            findings = anonymizer_service.analyze_pdf(file_bytes)

            # Rejestrujemy powiazanie ID z kluczem (entity_type, raw_value)
            # Uzyskujemy ujednolicone ID poprzez wywolanie _get_findings_for_file
            grouped_findings = _get_findings_for_file(file_bytes, file.filename)
            id_to_key = {}
            for gf in grouped_findings:
                id_to_key[gf["id"]] = (gf["entity_type"], gf["raw_value"])

            # Budujemy zestawy aktywnych i wybranego klucza
            active_keys = set(id_to_key[aid] for aid in active_ids if aid in id_to_key)
            highlight_key = id_to_key.get(highlight_id, None)

            # Renderowanie z filtrami kolorow i aktywnosci
            png_bytes = pdf_adapter.get_page_preview(
                file_bytes,
                page_num,
                findings,
                active_keys=active_keys,
                highlight_key=highlight_key
            )

            return send_file(io.BytesIO(png_bytes), mimetype="image/png")
        except Exception:
            traceback.print_exc()
            return jsonify({"error": "Błąd serwera - sprawdź konsolę"}), 500


# ---------------------------------------------------------------------------
# Punkt wejsciowy dla opcjonalnego uruchomienia bezposredniego
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = create_app()
    app.run(debug=FLASK_DEBUG, host="127.0.0.1", port=5000)