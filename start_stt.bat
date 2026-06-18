@echo off
REM One-click launcher for the AETHER speech-to-text proxy (stt_proxy.py).
REM This is what kills the iPhone mic re-ask: the PWA records audio with
REM getUserMedia (whose grant persists in an installed PWA) and POSTs it here for
REM transcription with local faster-whisper. Leave this window open while you use
REM voice in the app. If this proxy is down, the app falls back to the browser's
REM built-in dictation (which works, but re-asks the mic each session).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3 from python.org and re-run.
  pause
  exit /b 1
)

echo Installing faster-whisper if needed...
python -m pip install --quiet --disable-pip-version-check faster-whisper

echo.
echo Starting AETHER STT proxy ^(Ctrl+C to stop^)...
echo Expose it to your phone, tailnet-only:
echo   tailscale serve --bg --set-path /aether-stt http://127.0.0.1:8847
echo.
python stt_proxy.py
echo.
echo STT proxy stopped.
pause
