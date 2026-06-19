@echo off
set "PYTHONPATH=%~dp0src"
python -m cmip_downloader
if errorlevel 1 pause
