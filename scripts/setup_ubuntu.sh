#!/usr/bin/env bash
cd "$(dirname "$0")/.."

echo "Tworzenie srodowiska wirtualnego..."
python3 -m venv .venv

echo "Aktualizacja pip..."
.venv/bin/python -m pip install --upgrade pip

echo "Instalacja zaleznosci..."
.venv/bin/python -m pip install -r requirements.txt

echo "Generowanie slownikow..."
.venv/bin/python scripts/update_dictionaries.py

echo "Gotowe."