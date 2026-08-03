@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay Python. Hay cai Python 3.10 tro len tu python.org
  echo va nho tich chon "Add python.exe to PATH" khi cai.
  pause
  exit /b 1
)
python run_demo.py %*
pause
