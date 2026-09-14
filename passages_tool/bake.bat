@echo off
REM passages_tool bake launcher — Windows
REM Bakes PNG viewpoints then ships JPEG/KTX2. Uses the same local .venv as run.bat.

setlocal enabledelayedexpansion

if "%~1" == "" (
    echo Error: Missing level name argument.
    echo Usage: bake.bat ^<name^>
    echo Example: bake.bat onion
    exit /b 1
)

set "LEVEL_INPUT=%~1"
set "LEVEL_FILE="
set LEVEL_INPUT=!LEVEL_INPUT:"=!

if exist "!LEVEL_INPUT!" (
    for %%I in ("!LEVEL_INPUT!") do set "LEVEL_FILE=%%~fI"
)
if not defined LEVEL_FILE (
    if exist "!LEVEL_INPUT!.passages.json" (
        for %%I in ("!LEVEL_INPUT!.passages.json") do set "LEVEL_FILE=%%~fI"
    )
)
if not defined LEVEL_FILE (
    if exist "%~dp0json\!LEVEL_INPUT!" (
        for %%I in ("%~dp0json\!LEVEL_INPUT!") do set "LEVEL_FILE=%%~fI"
    ) else if exist "%~dp0json\!LEVEL_INPUT!.passages.json" (
        for %%I in ("%~dp0json\!LEVEL_INPUT!.passages.json") do set "LEVEL_FILE=%%~fI"
    )
)
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

pushd "%~dp0"

call "%~dp0_ensure_venv.bat"
if errorlevel 1 (
    popd
    exit /b 1
)

echo [passages_tool] Baking level: "%LEVEL_FILE%"
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
