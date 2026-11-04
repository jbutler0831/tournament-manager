@echo off
REM Builds dist\TournamentManager.exe. Run from a normal Command Prompt in the project folder.
REM See BUILD_WINDOWS.md for details.
setlocal
cd /d "%~dp0"

echo [1/5] Checking Python...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo ERROR: Python was not found.
    echo Install Python 3.9 or newer from https://www.python.org/downloads/windows/
    echo and tick "Add python.exe to PATH" in the installer.
    exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.9 or newer is required. Found:
    %PY% --version
    exit /b 1
)
%PY% -c "import tkinter"
if errorlevel 1 (
    echo ERROR: Tkinter is missing. Re-run the python.org installer, choose Modify,
    echo and tick "tcl/tk and IDLE".
    exit /b 1
)
%PY% --version

echo [2/5] Creating build environment in .venv-build ...
if not exist ".venv-build\Scripts\python.exe" (
    %PY% -m venv .venv-build
    if errorlevel 1 exit /b 1
)
set "VPY=.venv-build\Scripts\python.exe"

echo [3/5] Installing qrcode and PyInstaller...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VPY%" -m pip install -r requirements.txt "pyinstaller>=6.10"
if errorlevel 1 exit /b 1

echo [4/5] Running tests...
"%VPY%" -m unittest test_tournament_manager.py
if errorlevel 1 (
    echo ERROR: Tests failed. The .exe was NOT built.
    exit /b 1
)

echo [5/5] Building TournamentManager.exe ...
"%VPY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name TournamentManager tournament_manager.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed. See the messages above.
    exit /b 1
)

echo.
echo Done: dist\TournamentManager.exe
echo Saves and logs will go to Documents\TournamentManager\
endlocal
