@echo off
setlocal

REM Activate venv if it exists, otherwise use system Python
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
    python -m src.app
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
    python -m src.app
) else (
    py -3.10 -m src.app
)

if %errorlevel% neq 0 (
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
