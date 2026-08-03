@echo off
cd /d "%~dp0"
echo Checking Python runtime...
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)
%PY_CMD% --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Please install Python 3.10 or newer and enable Add Python to PATH.
  pause
  exit /b 1
)
%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Python is too old. Please install Python 3.10 or newer.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating local runtime environment...
  %PY_CMD% -m venv .venv
)
if errorlevel 1 (
  echo Failed to create the virtual environment.
  pause
  exit /b 1
)
echo Installing dependencies. The first install may take a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install --upgrade .
if errorlevel 1 (
  echo Installation failed. Please check the messages above and your network connection.
  pause
  exit /b 1
)
echo.
echo Installation complete. You can start the app with Start_Climate_Data_Downloader.bat.
choice /C YN /M "Start the app now"
if errorlevel 2 exit /b 0
call "%~dp0Start_Climate_Data_Downloader.bat"
