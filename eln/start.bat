@echo off
rem ELN starten: Server laeuft in diesem Fenster, Microsoft Edge oeffnet sich automatisch.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
title ELN - Elektronisches Laborbuch (Fenster offen lassen)
if not exist ".venv\Scripts\python.exe" (
  echo Die Anwendung ist noch nicht eingerichtet. Bitte zuerst setup.bat ausfuehren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py run
if errorlevel 1 (
  echo.
  echo Die Anwendung wurde mit einem Fehler beendet. Details: data\logs\fehler.log
  pause
)
