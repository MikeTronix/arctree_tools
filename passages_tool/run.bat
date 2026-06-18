@echo off
REM passages_tool launcher — Windows
REM Creates a .venv on first run, then launches the tool.
REM Uses python -m pip (not the pip shim) to avoid Conda venv pip issues.

setlocal

set VENV_DIR=%~dp0.venv
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

REM ── Create venv if it doesn't exist ──────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo [passages_tool] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Could not create venv. Make sure Python 3.10+ is on PATH.
        pause
        exit /b 1
    )
    echo [passages_tool] Installing dependencies...
    "%VENV_PYTHON%" -m pip install -e "%~dp0.[dev]" --quiet
    if errorlevel 1 (
        echo ERROR: pip install failed. Check your internet connection.
        pause
        exit /b 1
    )
)

REM ── Launch ────────────────────────────────────────────────────────────────────
echo [passages_tool] Starting...
"%VENV_PYTHON%" -m passages_tool.main %*
