@echo off
rem Vollstaendige Datensicherung (Datenbank, Dateien, Konfiguration) als ZIP mit Zeitstempel
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
"%PY%" manage.py backup
pause
