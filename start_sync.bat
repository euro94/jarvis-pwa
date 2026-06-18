@echo off
REM Launcher for the AETHER iOS Health sync receiver (health_sync.py).
REM The iPhone pushes Apple Health data here (sleep, steps, workouts); the PWA
REM pulls the normalized result into the Health + Sleep tabs. Leave open while
REM you want syncing to work.
cd /d "%~dp0"

REM IMPORTANT: set a private token and use the SAME one on the iPhone + in the
REM app's Settings -> iOS Health Sync field. Change the value below.
if "%AETHER_SYNC_TOKEN%"=="" set "AETHER_SYNC_TOKEN=aether-sync-7e3f9c"

echo Starting AETHER health-sync on port 8849 (Ctrl+C to stop)...
echo Token: %AETHER_SYNC_TOKEN%
echo Expose it to your phone (tailnet + funnel):
echo    tailscale funnel --bg --set-path /aether-sync http://127.0.0.1:8849
echo.
python health_sync.py
echo.
echo Health sync stopped.
pause
