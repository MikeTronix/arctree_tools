@echo off
REM Shared by run.bat and bake.bat.
REM Ensures a WORKING local .venv lives next to this tool (passages_tool/.venv).
REM That isolation is intentional — do not reuse the repo-root env, Miniconda, or
REM some other project's venv. A leftover venv whose pyvenv.cfg still points at an
REM uninstalled interpreter (typical after removing Miniconda) is deleted and recreated.

cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

set "_NEED=0"
if not exist "%VENV_PYTHON%" set "_NEED=1"
if "%_NEED%"=="0" (
    "%VENV_PYTHON%" -c "import sys" 1>nul 2>nul
    if errorlevel 1 set "_NEED=1"
)
if "%_NEED%"=="0" exit /b 0

echo [passages_tool] Local .venv is missing or broken (cannot start Python).
echo [passages_tool] Creating %VENV_DIR%
if exist "%VENV_DIR%" (
    echo [passages_tool] Removing the old venv...
    rmdir /s /q "%VENV_DIR%"
    if exist "%VENV_DIR%" (
        echo ERROR: Could not remove "%VENV_DIR%". Close any program using it and retry.
        exit /b 1
    )
)

REM Prefer a standalone 3.10+ interpreter. Skip anything already inside another
REM venv (sys.prefix != sys.base_prefix) — on this machine PATH "python" is often
REM some other project's env, which would just recreate the Miniconda-style trap.
set "HOST_PY="
for %%P in (python3.12 python3.11 python3.10 python python3) do (
    if not defined HOST_PY (
        %%P -c "import sys; assert sys.version_info >= (3, 10); assert sys.prefix == sys.base_prefix" 1>nul 2>nul
        if not errorlevel 1 set "HOST_PY=%%P"
    )
)
if not defined HOST_PY (
    py -3 -c "import sys; assert sys.version_info >= (3, 10); assert sys.prefix == sys.base_prefix" 1>nul 2>nul
    if not errorlevel 1 set "HOST_PY=py -3"
)

if defined HOST_PY (
    echo [passages_tool] Host interpreter: %HOST_PY%
    %HOST_PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Could not create venv with %HOST_PY%.
        exit /b 1
    )
) else (
    where uv >nul 2>nul
    if errorlevel 1 (
        echo ERROR: No working standalone Python 3.10+ on PATH.
        echo Install Python from python.org ^(not the Microsoft Store stub^),
        echo or install uv, and retry.
        echo A Python that already lives inside another .venv is skipped on purpose.
        exit /b 1
    )
    echo [passages_tool] Host interpreter: uv python 3.12
    uv venv --python 3.12 "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: uv venv failed.
        exit /b 1
    )
)

echo [passages_tool] Installing dependencies into the local venv...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
"%VENV_PYTHON%" -m pip install -e ".[dev]" --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    exit /b 1
)

"%VENV_PYTHON%" -c "import sys" 1>nul 2>nul
if errorlevel 1 (
    echo ERROR: New venv still cannot start. Host Python may be a stub.
    exit /b 1
)

echo [passages_tool] venv ready: %VENV_PYTHON%
exit /b 0
