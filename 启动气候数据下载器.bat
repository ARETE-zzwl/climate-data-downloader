@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo 尚未安装。请先双击“安装气候数据下载器.bat”。
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m cmip_downloader
