@echo off
rem ELN beenden (alternativ: Startfenster schliessen oder Strg+C)
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
"%PY%" manage.py stop
timeout /t 3 >nul
