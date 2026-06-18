@echo off
REM One-click launcher for the AETHER local-vision proxy (vision_local.py).
REM Runs a LOCAL vision model (Ollama) so the app's image features — Health meal
REM logging and Review Radar — work with no cloud and no Nous credits. Leave this
REM window open while you use them. If it's down, the app falls back to the cloud
REM agent automatically.
cd /d "%~dp0"

where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama not found on PATH. Install it from https://ollama.com/download
  echo Then run:  ollama pull qwen2.5vl:7b
  pause
  exit /b 1
)

echo Ensuring the vision model is present (qwen2.5vl:7b)...
ollama pull qwen2.5vl:7b

echo.
echo Starting AETHER local-vision proxy ^(Ctrl+C to stop^)...
echo Expose it to your phone, tailnet-only:
echo   tailscale serve --bg --set-path /aether-vision http://127.0.0.1:8846
echo.
python vision_local.py
echo.
echo Vision proxy stopped.
pause
