"""Fabryka aplikacji Flask z walidacja slownikow przy starcie."""
import sys
import subprocess
from datetime import datetime
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

def _build_anonymized_filename(
    original_filename: str,
) -> str:

    suffix = Path(
        original_filename
    ).suffix.lower()

    now = datetime.now()

    timestamp = now.strftime(
        "%d-%m_%H-%M"
    )

    return (
        f"anonimizacja_{timestamp}{suffix}"
    )

def _register_routes(app: Flask) -> None:
    """Rejestruje podstawowe trasy."""
    import json
    import io
    import zipfile
    from flask import render_template, send_file, request, jsonify

    from src.documents.pdf_adapter import PdfAdapter
    from src.documents.docx_adapter import DocxAdapter
    from src.documents.xlsx_adapter import XlsxAdapter
    from src.anonymization.service import AnonymizationService
    from src.documents.metadata_sanitizer import (
        sanitize_document_metadata,
    )

    pdf_adapter = PdfAdapter()
    docx_adapter = DocxAdapter()
    xlsx_adapter = XlsxAdapter()
    anonymizer_service = AnonymizationService()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return {"status": "ok", "message": "Anonimizator dziala"}

    def _get_findings_for_file(file_bytes: bytes, filename: str) -> list[dict]:
        """Ekstrahuje findings z pliku i grupuje je."""
        file_ext = filename.lower()
        if file_ext.endswith(".pdf"):
            raw_findings = (
                anonymizer_service.analyze_pdf(
                    file_bytes
                )
            )

            raw_findings = (
                pdf_adapter.enrich_findings_with_pdf_bbox(
                    file_bytes,
                    raw_findings,
                )
            )
        elif file_ext.endswith(".docx"):
            raw_findings = anonymizer_service.analyze_docx(file_bytes)
        elif file_ext.endswith(".xlsx"):
            raw_findings = anonymizer_service.analyze_xlsx(file_bytes)
        else:
            # Brak wsparcia
            return []

        # Grupowanie unikalnych znalezisk po (typ, wartosc)
        grouped: dict[tuple[str, str], dict] = {}

        location_fields = (
            # PDF
            "page",
            "bbox",
            "pdf_bbox",

            # XLSX
            "location",
            "xlsx_part",
            "xlsx_cell",
            "xlsx_storage",
            "xlsx_shared_index",

            # DOCX
            "part",
            "location",
            "docx_part",
            "docx_story",
            "docx_paragraph",
        )

        for f in raw_findings:
            key = (
                f["entity_type"],
                f["raw_value"],
            )

            # Konkretne pojedyncze wystąpienie findingu.
            occurrence = {}

            for field in location_fields:
                if (
                    field in f
                    and f[field] is not None
                ):
                    occurrence[field] = f[field]

            if key not in grouped:
                grouped[key] = {
                    "entity_type": f["entity_type"],
                    "marker": f["marker"],
                    "score": f["score"],
                    "reason": f.get(
                        "reason",
                        "Regula z silnika",
                    ),
                    "raw_value": f["raw_value"],
                    "count": 0,

                    # Wszystkie miejsca wystąpienia tej samej
                    # wartości.
                    "occurrences": [],
                }

                # ----------------------------------------------------
                # Backward compatibility.
                #
                # Zachowujemy również pierwszą lokalizację bezpośrednio
                # w findingu. PDF preview oraz starszy kod mogą nadal
                # z tego korzystać.
                # ----------------------------------------------------

                for field in location_fields:
                    if (
                        field in f
                        and f[field] is not None
                    ):
                        grouped[key][field] = f[field]

            grouped[key]["count"] += 1

            grouped[key]["occurrences"].append(
                occurrence
            )

            # Jeżeli ta sama wartość została znaleziona z różnymi
            # score, w tabeli pokazujemy najwyższy.
            if (
                f.get("score", 0)
                > grouped[key].get("score", 0)
            ):
                grouped[key]["score"] = f["score"]

        # Nadajemy identyfikatory.
        result = []

        for idx, (key, value) in enumerate(
            grouped.items(),
            start=1,
        ):
            value["id"] = str(idx)
            result.append(value)

        # ---------------------------------------------------
        # PDF: podpis cyfrowy jako finding dokumentowy.
        #
        # Nie jest to finding tekstowy Presidio.
        # Trafia jednak do tego samego pipeline:
        #
        # analiza -> checkbox -> confirmed_ids -> anonymize
        # ---------------------------------------------------

        if filename.lower().endswith(
            ".pdf"
        ):
            signatures = (
                pdf_adapter.detect_digital_signatures(
                    file_bytes
                )
            )

            if signatures:
                first_signature = signatures[0]

                result.append(
                    {
                        "id": str(
                            len(result) + 1
                        ),
                        "entity_type": "PDF_SIGNATURE",
                        "marker": "PODPIS CYFROWY",
                        "score": 1.0,
                        "reason": (
                            "Wykryto podpis cyfrowy "
                            "w strukturze dokumentu PDF."
                        ),
                        # Techniczny identyfikator.
                        # Nie jest wyszukiwany w tekscie PDF.
                        "raw_value": "__PDF_SIGNATURES__",
                        "page": first_signature[
                            "page"
                        ],
                        "bbox": first_signature[
                            "bbox"
                        ],
                        "count": len(
                            signatures
                        ),
                        "pdf_bbox": first_signature[
                            "pdf_bbox"
                        ],
                        "occurrences": [
                            {
                                "page": signature[
                                    "page"
                                ],
                                "bbox": signature[
                                    "bbox"
                                ],
                                "pdf_bbox": signature[
                                    "pdf_bbox"
                                ],
                            }
                            for signature in signatures
                        ],
                        "document_action": (
                            "remove_pdf_signatures"
                        ),
                    }
                )

        return result

    @app.route("/analyze", methods=["POST"])
    def analyze():
        """Trasa analizy pliku."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Pusta nazwa pliku"}), 400

        filename_lower = file.filename.lower()

        # Walidacja formatu
        _SUPPORTED = (".pdf", ".docx", ".xlsx")
        _UNSUPPORTED = (".doc", ".xls", ".docm", ".xlsm", ".xlsb")
        if any(filename_lower.endswith(ext) for ext in _UNSUPPORTED):
            return jsonify({"error": f"Format {Path(file.filename).suffix} nie jest obsługiwany. Obsługiwane formaty: PDF, DOCX, XLSX."}), 400
        if not any(filename_lower.endswith(ext) for ext in _SUPPORTED):
            return jsonify({"error": "Nieobsługiwany format pliku. Obsługiwane: PDF, DOCX, XLSX."}), 400

        file_bytes = file.read()

        try:
            findings = _get_findings_for_file(file_bytes, file.filename)
            return jsonify({"findings": findings})
        except Exception as exc:
            return jsonify({"error": f"Blad podczas analizy: {str(exc)}"}), 500

    @app.route("/preview-docx", methods=["POST"])
    def preview_docx():
        """Zwraca podgląd DOCX jako HTML, analogicznie do PDF.js."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Pusta nazwa pliku"}), 400

        filename_lower = file.filename.lower()
        if not filename_lower.endswith(".docx"):
            return jsonify({"error": "Ta ścieżka obsługuje wyłącznie DOCX."}), 400

        file_bytes = file.read()
        try:
            findings = _get_findings_for_file(file_bytes, file.filename)
            mode = request.form.get("preview_mode", "detections")
            preview_html = docx_adapter.build_preview_html(file_bytes, findings, mode=mode)
            return jsonify({"html": preview_html})
        except Exception as exc:
            return jsonify({"error": f"Blad podczas generowania podglądu DOCX: {str(exc)}"}), 500

    @app.route("/preview-xlsx", methods=["POST"])
    def preview_xlsx():
        """Zwraca podgląd XLSX jako HTML w tym samym modelu co PDF/DOCX."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Pusta nazwa pliku"}), 400

        filename_lower = file.filename.lower()
        if not filename_lower.endswith(".xlsx"):
            return jsonify({"error": "Ta ścieżka obsługuje wyłącznie XLSX."}), 400

        file_bytes = file.read()
        try:
            findings = _get_findings_for_file(file_bytes, file.filename)

            manual_findings_raw = request.form.get("manual_findings", "[]")
            try:
                manual_findings = json.loads(manual_findings_raw) if manual_findings_raw else []
            except Exception:
                manual_findings = []

            for item in manual_findings:
                if not isinstance(item, dict):
                    continue
                raw_value = str(item.get("raw_value", "")).strip()
                if not raw_value:
                    continue
                findings.append({
                    "id": item.get("id") or f"manual-{len(findings)}-{abs(hash(raw_value))}",
                    "entity_type": item.get("entity_type", "MANUAL"),
                    "marker": item.get("marker", "[DODANE_RĘCZNIE]"),
                    "raw_value": raw_value,
                    "score": float(item.get("score", 1.0)),
                    "reason": item.get("reason", "Dodane ręcznie"),
                    "xlsx_part": item.get("xlsx_part"),
                    "xlsx_cell": item.get("xlsx_cell"),
                    "manual": True,
                })

            mode = request.form.get("preview_mode", "detections")
            preview_html = xlsx_adapter.build_preview_html(file_bytes, findings, mode=mode)
            return jsonify({"html": preview_html})
        except Exception as exc:
            return jsonify({"error": f"Blad podczas generowania podglądu XLSX: {str(exc)}"}), 500

    @app.route("/anonymize", methods=["POST"])
    def anonymize():
        """Trasa anonimizacji pliku."""
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku"}), 400

        file = request.files["file"]
        confirmed_ids_raw = request.form.get("confirmed_ids", "[]")

        try:
            confirmed_ids = json.loads(confirmed_ids_raw)
        except Exception:
            return jsonify({"error": "Niepoprawny format confirmed_ids"}), 400

        file_bytes = file.read()

        try:
            findings = _get_findings_for_file(file_bytes, file.filename)
            confirmed_findings = [f for f in findings if f["id"] in confirmed_ids]

            manual_findings_raw = request.form.get("manual_findings", "[]")
            try:
                manual_findings = json.loads(manual_findings_raw) if manual_findings_raw else []
            except Exception:
                manual_findings = []

            for item in manual_findings:
                if not isinstance(item, dict):
                    continue
                raw_value = str(item.get("raw_value", "")).strip()
                if not raw_value:
                    continue
                confirmed_findings.append({
                    "entity_type": item.get("entity_type", "MANUAL"),
                    "marker": item.get("marker", "[DODANE_RĘCZNIE]"),
                    "raw_value": raw_value,
                    "score": float(item.get("score", 1.0)),
                    "reason": item.get("reason", "Dodane ręcznie"),
                    "xlsx_part": item.get("xlsx_part"),
                    "xlsx_cell": item.get("xlsx_cell"),
                })

            file_ext = file.filename.lower()

            if file_ext.endswith(".pdf"):
                out_bytes = pdf_adapter.anonymize(
                    file_bytes,
                    confirmed_findings,
                )

                mimetype = "application/pdf"

            elif file_ext.endswith(".docx"):
                out_bytes = docx_adapter.anonymize(
                    file_bytes,
                    confirmed_findings,
                )

                mimetype = (
                    "application/vnd.openxmlformats-"
                    "officedocument.wordprocessingml.document"
                )

            elif file_ext.endswith(".xlsx"):
                out_bytes = xlsx_adapter.anonymize(
                    file_bytes,
                    confirmed_findings,
                )

                mimetype = (
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                )

            else:
                return jsonify({
                    "error": "Nieobsługiwany format"
                }), 400


            # -------------------------------------------------------
            # Finalne czyszczenie metadanych.
            #
            # Celowo jest tutaj, a nie osobno w kazdym adapterze.
            # Kazdy obslugiwany format przechodzi przez ten sam
            # koncowy etap przed zwroceniem pliku.
            # -------------------------------------------------------

            out_bytes = sanitize_document_metadata(
                out_bytes,
                file.filename,
            )


            out_io = io.BytesIO(
                out_bytes
            )

            output_filename = _build_anonymized_filename(
                file.filename
            )

            return send_file(
                out_io,
                mimetype=mimetype,
                as_attachment=True,
                download_name=output_filename,
            )
            
        except Exception as exc:
            return jsonify({"error": f"Blad podczas anonimizacji: {str(exc)}"}), 500

    @app.route("/anonymize-all", methods=["POST"])
    def anonymize_all():
        """Anonimizuje wszystkie pliki i zwraca je w jednym archiwum ZIP."""
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "Brak plikow"}), 400

        try:
            settings_raw = request.form.get("settings", "[]")
            settings = json.loads(settings_raw)
            if not isinstance(settings, list):
                raise ValueError("Niepoprawny format ustawien")

            settings_by_index = {
                str(item.get("index")): item
                for item in settings
                if isinstance(item, dict)
            }
            archive_io = io.BytesIO()

            with zipfile.ZipFile(archive_io, "w", zipfile.ZIP_DEFLATED) as archive:
                used_names = set()
                for index, file in enumerate(files):
                    filename = Path(file.filename or f"plik_{index + 1}").name
                    if not filename:
                        filename = f"plik_{index + 1}"

                    item_settings = settings_by_index.get(str(index), {})
                    confirmed_ids = {
                        str(value)
                        for value in item_settings.get("confirmed_ids", [])
                    }
                    manual_findings = item_settings.get("manual_findings", [])
                    file_bytes = file.read()
                    findings = _get_findings_for_file(file_bytes, filename)
                    confirmed_findings = [
                        finding for finding in findings
                        if str(finding.get("id")) in confirmed_ids
                    ]

                    for item in manual_findings:
                        if not isinstance(item, dict):
                            continue
                        raw_value = str(item.get("raw_value", "")).strip()
                        if raw_value:
                            confirmed_findings.append({
                                "entity_type": item.get("entity_type", "MANUAL"),
                                "marker": item.get("marker", "[DODANE_RĘCZNIE]"),
                                "raw_value": raw_value,
                                "score": float(item.get("score", 1.0)),
                                "reason": item.get("reason", "Dodane ręcznie"),
                                "xlsx_part": item.get("xlsx_part"),
                                "xlsx_cell": item.get("xlsx_cell"),
                            })

                    if filename.lower().endswith(".pdf"):
                        output = pdf_adapter.anonymize(file_bytes, confirmed_findings)
                    elif filename.lower().endswith(".docx"):
                        output = docx_adapter.anonymize(file_bytes, confirmed_findings)
                    elif filename.lower().endswith(".xlsx"):
                        output = xlsx_adapter.anonymize(file_bytes, confirmed_findings)
                    else:
                        raise ValueError(f"Nieobslugiwany format pliku: {filename}")

                    output = sanitize_document_metadata(output, filename)
                    output_name = _build_anonymized_filename(filename)
                    suffix = Path(output_name).suffix
                    unique_name = f"{Path(output_name).stem}_{index + 1}{suffix}"
                    counter = 2
                    while unique_name in used_names:
                        unique_name = f"{Path(output_name).stem}_{index + 1}_{counter}{suffix}"
                        counter += 1
                    used_names.add(unique_name)
                    archive.writestr(unique_name, output)

            archive_io.seek(0)
            return send_file(
                archive_io,
                mimetype="application/zip",
                as_attachment=True,
                download_name="anonimizacje.zip",
            )
        except Exception as exc:
            return jsonify({"error": f"Blad podczas anonimizacji plikow: {str(exc)}"}), 500

# ---------------------------------------------------------------------------
# Punkt wejsciowy dla opcjonalnego uruchomienia bezposredniego
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = create_app()
    app.run(debug=FLASK_DEBUG, host="127.0.0.1", port=5000)