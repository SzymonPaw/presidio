#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
	if command -v python3.14 >/dev/null 2>&1; then
		PYTHON_BIN="python3.14"
	else
		PYTHON_BIN="python3"
	fi
fi

echo "Uzywany interpreter: $($PYTHON_BIN --version)"
echo "Tworzenie srodowiska wirtualnego..."
"$PYTHON_BIN" -m venv .venv

echo "Aktualizacja pip..."
.venv/bin/python -m pip install --upgrade pip

echo "Instalacja zaleznosci..."
.venv/bin/python -m pip install -r requirements.txt

echo "Generowanie slownikow..."
.venv/bin/python scripts/update_dictionaries.py

echo "Gotowe."