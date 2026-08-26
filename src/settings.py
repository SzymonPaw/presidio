"""Ustawienia aplikacji odczytywane ze zmiennych srodowiskowych."""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Sciezki bazowe
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = DATA_DIR / "source"
RECOGNIZERS_DIR = BASE_DIR / "config" / "recognizers"
REPORTS_DIR = DATA_DIR / "reports"
INSTANCE_DIR = BASE_DIR / "instance"
MIGRATIONS_DIR = BASE_DIR / "migrations"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# Zmienne srodowiskowe
# ---------------------------------------------------------------------------
def _get_env(key: str, default: str | None = None) -> str | None:
    """Pobiera zmienna srodowiskowa, z opcjonalna domyslna."""
    return os.getenv(key, default)


FLASK_DEBUG = _get_env("FLASK_DEBUG", "1") == "1"
FLASK_PORT = int(_get_env("PORT", "5000"))
FLASK_HOST = _get_env("HOST", "127.0.0.1")

DATABASE_URL = _get_env("DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'metrics.sqlite3'}")

# ---------------------------------------------------------------------------
# Slowniki - sciezki do plikow generowanych
# ---------------------------------------------------------------------------
FIRST_NAMES_DICT = RECOGNIZERS_DIR / "first_names.csv"
SURNAMES_DICT = RECOGNIZERS_DIR / "surnames.csv"
LOCALITIES_DICT = RECOGNIZERS_DIR / "localities.txt"

# ---------------------------------------------------------------------------
# Pliki zrodlowe (do generowania slownikow)
# ---------------------------------------------------------------------------
FIRST_NAMES_SOURCE = SOURCE_DIR / "first_names_source.csv"
SURNAMES_SOURCE = SOURCE_DIR / "surnames_source.csv"
SIMC_SOURCE = SOURCE_DIR / "SIMC.csv"

REQUIRED_GENERATED_DICTS = [
    FIRST_NAMES_DICT,
    SURNAMES_DICT,
    LOCALITIES_DICT,
]

REQUIRED_SOURCE_FILES = [
    FIRST_NAMES_SOURCE,
    SURNAMES_SOURCE,
    SIMC_SOURCE,
]

# ---------------------------------------------------------------------------
# Konfiguracja uploadu oraz limitów bezpieczeństwa ZIP/XML
# ---------------------------------------------------------------------------
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
MAX_FILES_PER_BATCH = 8

# Limity ZIP bomb / bezpieczeństwa
ZIP_MAX_ENTRIES = 500
ZIP_MAX_DECOMPRESSED_PART = 30 * 1024 * 1024  # 30 MB
ZIP_MAX_DECOMPRESSED_TOTAL = 150 * 1024 * 1024  # 150 MB
ZIP_MAX_RATIO = 50  # Max 50x kompresji

# ---------------------------------------------------------------------------
# Inne ustawienia
# ---------------------------------------------------------------------------
SECRET_KEY = _get_env("SECRET_KEY", "dev-secret-change-in-production")


def ensure_directories() -> None:
    """Tworzy wymagane katalogi, jesli nie istnieja."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RECOGNIZERS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)