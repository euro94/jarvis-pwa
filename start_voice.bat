@echo off
REM AETHER Claude-direct voice proxy launcher.
REM Uses a dedicated Python 3.11 venv (.voicevenv) because the system Python 3.14
REM has no native wheels for the anthropic SDK's deps (pydantic_core, jiter).
REM Auth uses the Claude Code OAuth token from .builder_env (Pro/Max plan, no
REM per-token API cost) — no ANTHROPIC_API_KEY required.
cd /d "%~dp0"

REM Load the OAuth token (CLAUDE_CODE_OAUTH_TOKEN) from .builder_env.
for /f "usebackq tokens=1,* delims==" %%A in (".builder_env") do (
  if "%%A"=="export CLAUDE_CODE_OAUTH_TOKEN" set CLAUDE_CODE_OAUTH_TOKEN=%%~B
)

if not exist ".voicevenv\Scripts\python.exe" (
  echo Voice venv missing. Run: py -V:Astral/CPython3.11.15 -m venv .voicevenv ^&^& .voicevenv\Scripts\python -m pip install anthropic
  pause
  exit /b 1
)

echo Starting AETHER voice proxy (Ctrl+C to stop)...
.voicevenv\Scripts\python.exe voice_proxy.py
echo.
echo Proxy stopped.
pause
