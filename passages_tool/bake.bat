@echo off
REM passages_tool bake launcher — Windows
REM bakes the level rendering and populates the renders_out/ directory.

setlocal enabledelayedexpansion

if "%~1" == "" (
    echo Error: Missing level name argument.
    echo Usage: bake.bat ^<name^>
    echo Example: bake.bat onion
    exit /b 1
)

set "LEVEL_INPUT=%~1"
set "LEVEL_FILE="

REM Remove quotes if present
set LEVEL_INPUT=!LEVEL_INPUT:"=!

REM 1. Check if LEVEL_INPUT is an existing file (relative to current directory or absolute)
if exist "!LEVEL_INPUT!" (
    for %%I in ("!LEVEL_INPUT!") do set "LEVEL_FILE=%%~fI"
)

REM 2. Check if LEVEL_INPUT.passages.json exists relative to current directory
if not defined LEVEL_FILE (
    if exist "!LEVEL_INPUT!.passages.json" (
        for %%I in ("!LEVEL_INPUT!.passages.json") do set "LEVEL_FILE=%%~fI"
    )
)

REM 3. Check if it exists in script's json/ directory (with or without extension)
if not defined LEVEL_FILE (
    if exist "%~dp0json\!LEVEL_INPUT!" (
        for %%I in ("%~dp0json\!LEVEL_INPUT!") do set "LEVEL_FILE=%%~fI"
    ) else if exist "%~dp0json\!LEVEL_INPUT!.passages.json" (
        for %%I in ("%~dp0json\!LEVEL_INPUT!.passages.json") do set "LEVEL_FILE=%%~fI"
    )
)

REM 4. Check if it exists in script's root directory (with or without extension)
if not defined LEVEL_FILE (
    if exist "%~dp0!LEVEL_INPUT!" (
        for %%I in ("%~dp0!LEVEL_INPUT!") do set "LEVEL_FILE=%%~fI"
    ) else if exist "%~dp0!LEVEL_INPUT!.passages.json" (
        for %%I in ("%~dp0!LEVEL_INPUT!.passages.json") do set "LEVEL_FILE=%%~fI"
    )
)

if not defined LEVEL_FILE (
    echo Error: Level file not found for "!LEVEL_INPUT!"
    echo Tried looking for:
    echo   - "!LEVEL_INPUT!"
    echo   - "!LEVEL_INPUT!.passages.json"
    echo   - "%~dp0json\!LEVEL_INPUT!"
    echo   - "%~dp0json\!LEVEL_INPUT!.passages.json"
    exit /b 1
)

REM Now change directory to the script's directory so relative paths work perfectly with Panda3D
pushd "%~dp0"

set VENV_DIR=.venv
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

REM ── Create venv if it doesn't exist ──────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo [passages_tool] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Could not create venv. Make sure Python 3.10+ is on PATH.
        popd
        exit /b 1
    )
    echo [passages_tool] Installing dependencies...
    "%VENV_PYTHON%" -m pip install -e ".[dev]" --quiet
    if errorlevel 1 (
        echo ERROR: pip install failed. Check your internet connection.
        popd
        exit /b 1
    )
)

echo [passages_tool] Baking level: "%LEVEL_FILE%"

REM We pass relative paths for outputs to avoid Panda3D drive/backslash issues
"%VENV_PYTHON%" -m passages_tool.renderer "%LEVEL_FILE%" "scene_out" "renders_out" --textures "assets/sample_textures" --force

set RENDER_ERROR=%errorlevel%

if %RENDER_ERROR% neq 0 (
    popd
    echo ERROR: Baking failed.
    exit /b %RENDER_ERROR%
)

echo [passages_tool] Shipping JPEG/KTX2 to shipping_out (JPEG fallback if basisu is missing)...
"%VENV_PYTHON%" -m passages_tool.renderer.convert_to_jpeg "renders_out" "shipping_out"
set SHIP_ERROR=%errorlevel%

popd

if %SHIP_ERROR% neq 0 (
    echo ERROR: Bake succeeded but shipping convert failed. PNGs are in "%~dp0renders_out"
    exit /b %SHIP_ERROR%
)

echo [passages_tool] Baking completed successfully.
echo   PNGs:     "%~dp0renders_out"
echo   Shipping: "%~dp0shipping_out"
