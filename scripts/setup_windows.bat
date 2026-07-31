@echo off
cd /d "%~dp0.."

echo Tworzenie srodowiska wirtualnego...
python -m venv .venv
echo Aktualizacja pip...
.venv\Scripts\python.exe -m pip install --upgrade pip
echo Instalacja zaleznosci...
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo Gotowe.
pause