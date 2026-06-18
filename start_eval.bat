@echo off
REM One-shot eval run — screenshots all screens, sends to local vision model,
REM prints findings to console. Use this to get instant feedback before or after
REM shipping a branch. Needs: Chrome, vision_local.py running on :8846.
REM
REM Usage:
REM   start_eval.bat                       -- all screens, medium+ findings
REM   start_eval.bat low                   -- include low-severity too
REM   start_eval.bat high screenHealth,screenSleep  -- specific screens
cd /d "%~dp0"
set MIN_SEV=%1
if "%MIN_SEV%"=="" set MIN_SEV=medium
set SCREENS=%2
if "%SCREENS%"=="" set SCREENS=
if not "%SCREENS%"=="" set SCREENS_ARG=--screens %SCREENS%
echo AETHER eval — min severity: %MIN_SEV%
python eval_loop.py --url https://euro94.github.io/jarvis-pwa/ --min-severity %MIN_SEV% %SCREENS_ARG%
pause
