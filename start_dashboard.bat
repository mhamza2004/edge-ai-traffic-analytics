@echo off
REM Auto-start script for the Edge-AI Traffic Analytics Engine.
REM Waits briefly so Docker Desktop / network have time to come up after login,
REM then activates the venv and starts the live dashboard server.

cd /d "%~dp0"

echo Waiting 20 seconds for system services to settle...
timeout /t 20 /nobreak >nul

call venv\Scripts\activate.bat

echo Starting Traffic Analytics Engine...
python -m scripts.run_pipeline --serve --config config/config.yaml

REM If the server exits/crashes, keep the window open so the error is visible
REM instead of the window just vanishing.
echo.
echo Server stopped. Press any key to close this window.
pause >nul
