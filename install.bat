@echo off
rem UTF-8 for all file I/O (place names, km2) instead of the Windows code page
set PYTHONUTF8=1
rem Windows installer: double-click, or run install.bat (finds Python >= 3.11 and runs install.py, see there)
cd /d "%~dp0"
for %%V in (3.12 3.13 3.11 3.14) do (
  py -%%V -c "import sys" >nul 2>&1 && ( py -%%V install.py %* & goto :end )
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && ( python install.py %* & goto :end )
echo ERROR: Python 3.11 or newer not found. Install it from https://www.python.org (tick "Add python.exe to PATH") and run install.bat again.
:end
pause
