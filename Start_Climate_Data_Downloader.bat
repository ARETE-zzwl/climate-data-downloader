@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo The app is not installed yet. Run Install_Climate_Data_Downloader.bat first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m cmip_downloader
