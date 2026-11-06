@echo off
rem Wiederherstellung einer Sicherung. Vorher Anwendung mit stop.bat beenden!
rem Aufruf: restore.bat "C:\ELN-Sicherungen\eln_sicherung_20260101_120000.zip"
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if "%~1"=="" (
  echo Aufruf: restore.bat PFAD_ZUR_SICHERUNG.zip
  echo Vorhandene Sicherungen siehe Ordner laut ELN_BACKUP_DIR in .env
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py restore "%~1"
pause
