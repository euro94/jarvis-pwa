@echo off
REM Start the AETHER "Claude Code" Builder bridge.
REM Double-click this, or run it from a terminal. Leave the window open.
cd /d "%~dp0"
echo Starting Claude Code Builder bridge...  (close this window to stop)
python builder_bridge.py
pause
