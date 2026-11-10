@echo off
rem ELN starten: Server laeuft in diesem Fenster, Microsoft Edge oeffnet sich automatisch.
rem Portable Version: nutzt das mitgelieferte Python im Ordner "python" (keine Installation noetig).
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
title ELN - Elektronisches Laborbuch (Fenster offen lassen)
set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
if not exist "%PY%" (
  echo Die Anwendung ist noch nicht eingerichtet. Bitte zuerst setup.bat ausfuehren.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul

"%PY%" manage.py needs-setup
if not errorlevel 1 goto starten

echo.
echo ===== ELN - Ersteinrichtung =====
echo Es wird jetzt die Datenbank angelegt und der erste Administrator erstellt.
echo.
"%PY%" manage.py init
if errorlevel 1 goto fehler
echo.
set "DEMO=N"
set /p DEMO="Beispieldaten fuer Schulung/Test anlegen? (J/N): "
if /i "%DEMO%"=="J" "%PY%" manage.py seed-demo
echo.

:starten
"%PY%" manage.py run
if errorlevel 1 goto fehler
exit /b 0

:fehler
echo.
echo Die Anwendung wurde mit einem Fehler beendet. Details: data\logs\fehler.log
pause
exit /b 1
