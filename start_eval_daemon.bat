@echo off
REM AETHER eval_daemon — continuous local product intelligence.
REM Screenshots every screen constantly on the local GPU (Ollama + qwen2.5vl:7b).
REM Fires ntfy alerts on critical issues. Files ideas to BACKLOG.md automatically.
REM Zero API cost. Leave this running always.
cd /d "%~dp0"
echo AETHER eval daemon starting...
echo GPU: qwen2.5vl:7b (RTX 5070) - zero API cost
echo Alerts: ntfy to Jarvis
echo.
python eval_daemon.py
echo.
echo Daemon exited — check eval_daemon.log for errors
pause
