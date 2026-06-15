@echo off
REM One-click launcher for the AETHER Claude-direct voice proxy (voice_proxy.py).
REM Double-click this file. It runs from the repo folder, installs the SDK if
REM needed, asks for your Anthropic API key if it's not already set, and starts
REM the proxy. Leave the window open while you use Live mode in the app.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3 from python.org and re-run.
  pause
  exit /b 1
)

echo Installing the Anthropic SDK if needed...
python -m pip install --quiet --disable-pip-version-check anthropic

if "%ANTHROPIC_API_KEY%"=="" (
  echo.
  echo Paste your Anthropic API key ^(starts with sk-ant-...^) and press Enter:
  set /p ANTHROPIC_API_KEY=^>
)

echo.
echo Starting AETHER voice proxy ^(Ctrl+C to stop^)...
python voice_proxy.py
echo.
echo Proxy stopped.
pause
