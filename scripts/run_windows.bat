@echo off
cd /d "%~dp0.."

echo Uruchamianie aplikacji...
call .venv\Scripts\activate.bat
python app.py
pause