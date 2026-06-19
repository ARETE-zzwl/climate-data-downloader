@echo off
chcp 65001 >nul
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo 未找到 Python。请先安装 Python 3.10 或更高版本，并加入 PATH。
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 (
  echo 创建虚拟环境失败。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
  echo 安装失败，请检查上方错误和网络连接。
  pause
  exit /b 1
)
echo 安装完成。现在可以双击“启动气候数据下载器.bat”。
pause

