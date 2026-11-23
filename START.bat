@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OLEG AI

set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo Python не найден. Устанавливаю его автоматически, это займёт пару минут...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python установлен. Закрой это окно и запусти START.bat ещё раз.
  pause
  exit /b
)

if not exist .venv (
  echo Первый запуск: готовлю программу, подожди 1-3 минуты...
  %PY% -m venv .venv
)
call .venv\Scripts\activate.bat
if not exist .venv\.ready (
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Не удалось установить компоненты. Проверь интернет и запусти START.bat ещё раз.
    pause
    exit /b
  )
  echo ok> .venv\.ready
)

python -m oleg_ai.launcher
pause
