@echo off
REM Register the AETHER voice proxy watchdog as a scheduled task (every 3 min).
set WD=C:\Users\yaros\.hermes\jarvis-pwa\.voicevenv\Scripts\python.exe
set SC=C:\Users\yaros\.hermes\scripts\voice_proxy_watchdog.py
schtasks /Create /TN "AETHER_Voice_Proxy" /TR "\"%WD%\" \"%SC%\"" /SC MINUTE /MO 3 /F
schtasks /Query /TN "AETHER_Voice_Proxy" /FO LIST
