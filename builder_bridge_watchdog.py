#!/usr/bin/env python3
"""
builder_bridge_watchdog.py — keep EXACTLY ONE AETHER "Claude Code" builder
bridge alive, surviving crashes and reboots.

Mirrors the proven tts_bridge_watchdog pattern:
  1. Reap duplicates — more than one builder_bridge.py answering the same ntfy
     topic causes interleaved/duplicate replies (the "WinError 193 + 401 + real
     answer all at once" symptom). Keep only the newest; kill the rest.
  2. Ensure one is alive via a single-instance lock PORT (ground truth). If the
     lock is free, no bridge is running -> start one (detached, no window).

The bridge is launched with the env from .builder_env sourced (CLAUDE token +
CLAUDE_BIN), via a tiny bash shim so the OAuth token never lands in a command
line that PowerShell/CIM would expose.

Stays SILENT when all is well. Prints only when it acts.
Run it on a schedule (Task Scheduler: at logon + every 3 min).
"""
import os
import socket
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(REPO, "builder_bridge.py")
ENVF = os.path.join(REPO, ".builder_env")
LOG = os.path.join(REPO, ".builder_bridge.log")
LOCK_PORT = 48762  # distinct from tts bridge's 48761

# git-bash to source the env file then exec the bridge
BASH = r"C:\Program Files\Git\bin\bash.exe"


def lock_is_held():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.close()
        return False
    except OSError:
        return True


def bridge_pids():
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') "
        "-and $_.CommandLine -like '*builder_bridge.py*' "
        "-and $_.CommandLine -notlike '*watchdog*' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        ).stdout
        return [int(l.strip()) for l in out.splitlines() if l.strip().isdigit()]
    except Exception:
        return []


def kill(pid):
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-WmiObject Win32_Process -Filter 'ProcessId=%d').Terminate()" % pid],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass


def reap_duplicates():
    pids = bridge_pids()
    if len(pids) <= 1:
        return 0
    keep = max(pids)
    reaped = 0
    for pid in pids:
        if pid != keep:
            kill(pid)
            reaped += 1
    return reaped


def start():
    # Build a POSIX path to the repo for bash, then source env + run the bridge.
    repo_posix = "/" + REPO.replace("\\", "/").replace(":", "", 1)
    cmd = "cd '%s' && source .builder_env && exec python -u builder_bridge.py" % repo_posix
    DETACHED = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    logf = open(LOG, "a")
    subprocess.Popen(
        [BASH, "-lc", cmd],
        stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
        creationflags=DETACHED | CREATE_NO_WINDOW,
        close_fds=True,
    )


def main():
    msgs = []
    reaped = reap_duplicates()
    if reaped:
        msgs.append("reaped %d duplicate builder bridge(s)" % reaped)
    if not lock_is_held():
        if not os.path.exists(ENVF):
            print("ERROR: %s missing — cannot start bridge (no Claude token)." % ENVF)
            return
        start()
        msgs.append("builder bridge was down — restarted it")
    if msgs:
        print("; ".join(msgs))


if __name__ == "__main__":
    main()
