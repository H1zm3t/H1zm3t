@echo off
rem ELN beenden (alternativ: Startfenster schliessen oder Strg+C)
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" manage.py stop
timeout /t 3 >nul
