@echo off
rem UTF-8 for all file I/O (place names, km2) instead of the Windows code page
set PYTHONUTF8=1
rem Windows: start the web app and open it in the browser (run install.bat first)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Not installed yet - run install.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m povodne serve --open %*
pause
