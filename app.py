"""Lokalny punkt uruchomienia anonimizatora dokumentow."""
import sys
from pathlib import Path

# Upewniamy sie, ze glowne repozytorium jest na PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    from src.settings import FLASK_DEBUG, FLASK_HOST, FLASK_PORT

    print(f"Anonimizator uruchomiony pod adresem http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)