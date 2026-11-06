@echo off
rem ELN - Einrichtung unter Windows (einmalig ausfuehren)
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
echo.
echo ===== ELN Anwendungstechnik - Einrichtung =====
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo FEHLER: Python wurde nicht gefunden.
  echo Bitte Python 3.11 oder neuer von https://www.python.org installieren
  echo und bei der Installation "Add python.exe to PATH" anhaken.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo FEHLER: Python 3.10 oder neuer ist erforderlich.
  %PY% --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Virtuelle Umgebung wird angelegt ...
  %PY% -m venv .venv
  if errorlevel 1 goto fehler
)
echo [2/4] Pakete werden installiert ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fehler

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo       Konfigurationsdatei .env angelegt - Pfade bei Bedarf anpassen.
)

echo [3/4] Datenbank wird eingerichtet ...
".venv\Scripts\python.exe" manage.py init
if errorlevel 1 goto fehler

echo.
set /p DEMO="[4/4] Beispieldaten fuer Schulung/Test anlegen? (J/N): "
if /i "%DEMO%"=="J" (
  ".venv\Scripts\python.exe" manage.py seed-demo
)

echo.
echo ===== Einrichtung abgeschlossen. Start mit start.bat =====
pause
exit /b 0

:fehler
echo.
echo FEHLER bei der Einrichtung. Bitte Meldungen oben pruefen (siehe README, Abschnitt Fehlerbehebung).
pause
exit /b 1
