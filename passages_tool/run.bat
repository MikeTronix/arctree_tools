@echo off
REM passages_tool launcher — Windows
REM Uses a local .venv next to this script (created/repaired by _ensure_venv.bat).

setlocal
cd /d "%~dp0"

call "%~dp0_ensure_venv.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

echo [passages_tool] Starting...
"%VENV_PYTHON%" -m passages_tool.main %*
