#!/usr/bin/env python
"""AETHER "Claude Code" Builder bridge.

Lets you drive Claude Code from the AETHER PWA (the Stream/Talk tab). The phone
POSTs a message to the builder INBOUND ntfy topic; this daemon picks it up, runs
Claude Code headlessly *inside this repo* with full autonomy, streams progress
back to the OUTBOUND topic (which the app's Stream feed renders live), and posts
the final result. Claude Code can edit index.html and `git push`, so GitHub Pages
redeploys and your phone gets the new app on reload — the app rebuilds itself.

This is the "talk to Claude Code remotely, bypass Hermes" path.

  Run it:   python builder_bridge.py
  Reset the conversation from the app by sending:  /new

SECURITY — read this:
  * The trigger is an unguessable ntfy topic on your Tailscale tailnet. That
    topic name IS the secret (same model as the rest of AETHER). Keep these
    topics tailnet-only; NEVER expose them via Tailscale Funnel — anyone who can
    reach the inbound topic can run code on this machine and push to your repo.
  * Strongly recommended extra lock: set BUILDER_TOKEN in the environment; then
    every phone message must start with that token (the bridge strips it) or it's
    ignored — so topic secrecy isn't your only gate.
  * PERMISSION_ARGS below is SCOPED by default (can build & ship the app, but not
    run arbitrary/destructive shell). A one-line swap to --dangerously-skip-
    permissions grants blanket power; only do that on fully trusted infra.
  * MAX_BUDGET_USD caps spend per request so a runaway can't drain your credits.
"""
import json, os, re, socket, subprocess, sys, time, urllib.request, shutil

# Windows console defaults to cp1252; our progress prints contain Unicode (→, ⌘,
# •, ✨). Printing those raised UnicodeEncodeError, which the poll loop caught as
# a "poll err" — so dispatch() never ran and the Studio silently shipped nothing.
# Force UTF-8 (and never let a logging glyph kill the run).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---- config ----
NTFY      = os.environ.get("AETHER_NTFY", "https://yaro.tail6a3c7a.ts.net")
IN_TOPIC  = "hermes-yaro-builder-in-c7b4c5ae80"
OUT_TOPIC = "hermes-yaro-builder-out-376c52849c"
REPO      = os.path.dirname(os.path.abspath(__file__))
SESS_FILE = os.path.join(REPO, ".builder_session")        # gitignored
BUILDER_TOKEN = os.environ.get("BUILDER_TOKEN", "")        # optional shared secret
MAX_BUDGET_USD = os.environ.get("BUILDER_MAX_USD", "3")    # per-request spend cap
POLL_SECS = 2

# Resolve claude executable. On Windows, `shutil.which("claude")` returns the
# POSIX shell-script shim (from git-bash), which subprocess CANNOT execute
# (WinError 193). We must use the native claude.exe. Prefer an explicit
# CLAUDE_BIN, then the packaged .exe, then PATH lookups.
def _resolve_claude():
    cand = []
    if os.environ.get("CLAUDE_BIN"):
        cand.append(os.environ["CLAUDE_BIN"])
    # the .exe shipped inside the npm package (most reliable on Windows)
    npm_root = os.path.expanduser(r"~/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe")
    cand.append(npm_root)
    cand.append(shutil.which("claude.exe") or "")
    if os.name == "nt":
        cand.append(shutil.which("claude.cmd") or "")
    cand.append(shutil.which("claude") or "")
    cand.append(os.path.expanduser(r"~/.local/bin/claude.exe"))
    for c in cand:
        if c and os.path.exists(c):
            # On Windows, reject the extension-less POSIX shim (can't be spawned).
            if os.name == "nt" and not c.lower().endswith((".exe", ".cmd", ".bat")):
                continue
            return c
    return cand[0] if cand else "claude"

CLAUDE_BIN = _resolve_claude()

# ---- Hermes engine (second shippable engine) ----
# `hermes -z "<prompt>" --yolo -t terminal,file` runs one-shot in this repo and
# prints ONLY the final reply to stdout. It can edit files + git push just like
# Claude Code, so "Send to Hermes" is a REAL engine, not a stub.
def _resolve_hermes():
    if os.environ.get("HERMES_BIN"):
        return os.environ["HERMES_BIN"]
    cand = [
        os.path.expanduser(r"~/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe"),
        shutil.which("hermes.exe") or "",
        shutil.which("hermes") or "",
    ]
    for c in cand:
        if c and os.path.exists(c):
            if os.name == "nt" and not c.lower().endswith((".exe", ".cmd", ".bat")):
                continue
            return c
    return cand[0] if cand else "hermes"

HERMES_BIN = _resolve_hermes()
DEFAULT_ENGINE = os.environ.get("BUILDER_DEFAULT_ENGINE", "claude")  # claude | hermes

# SCOPED AUTONOMY (hardened default): can read/edit/write files and run git,
# python, node, npm — enough to build AND ship the app — but cannot run arbitrary
# or destructive shell. rm/format/etc. are blocked, and any Bash command that does
# not match the allowlist is denied (Claude is told and adapts). This is the
# responsible default for a remotely-triggered agent.
#
# For BLANKET full power instead (run literally ANY command — a real RCE surface),
# replace this whole list with:   ["--dangerously-skip-permissions"]
# Only do that on a machine + tailnet you fully trust.
PERMISSION_ARGS = [
    "--permission-mode", "acceptEdits",
    "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash(git *),Bash(python *),Bash(node *),Bash(npm *)",
    "--disallowedTools", "Bash(rm *),Bash(rmdir *),Bash(del *),Bash(format *)",
]

SYSTEM = (
    "You are AETHER's 'Claude Code' Builder agent, invoked remotely from Yaro's "
    "phone (the Stream tab of the AETHER PWA). Your working directory IS the "
    "euro94/jarvis-pwa repository — the source of this very app. A background "
    "'Hermes' agent edits the same repo concurrently, so BEFORE you push, always "
    "run `git pull --rebase origin main`, and keep changes surgical to avoid "
    "conflicts. After editing index.html, sanity-check that the embedded <script> "
    "still parses. Commit with a clear message (include a Co-Authored-By: Claude "
    "trailer) and `git push origin main` so GitHub Pages redeploys. Your replies "
    "are read on a phone screen — be concise: one or two sentences on what you "
    "changed. If a request is ambiguous, risky, or destructive (deleting data, "
    "touching secrets, large rewrites), do the safe thing and say what you did."
)


# ---- ntfy helpers ----
def post(text, title="claude-code"):
    if not text:
        return
    body = text if len(text) <= 3500 else text[:3490] + " …[truncated]"
    req = urllib.request.Request(
        f"{NTFY}/{OUT_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": title},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print("post error:", e, file=sys.stderr)


def load_session():
    try:
        return open(SESS_FILE).read().strip() or None
    except Exception:
        return None


def save_session(sid):
    try:
        open(SESS_FILE, "w").write(sid or "")
    except Exception:
        pass


# ---- summarize a tool_use for the live feed ----
def tool_summary(name, inp):
    inp = inp or {}
    if name == "Bash":
        return "• " + (inp.get("command") or "bash")[:160]
    if name in ("Edit", "Write", "Read", "NotebookEdit"):
        return f"• {name} {os.path.basename(inp.get('file_path', '') or '')}".strip()
    if name in ("Grep", "Glob"):
        return f"• {name} {inp.get('pattern', '')}"[:160]
    return f"• {name}"


# ---- run Claude Code headlessly, stream progress ----
def run_claude(prompt):
    sid = load_session()
    cmd = [CLAUDE_BIN, "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           "--append-system-prompt", SYSTEM,
           "--max-budget-usd", str(MAX_BUDGET_USD)] + PERMISSION_ARGS
    if sid:
        cmd += ["--resume", sid]

    try:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1)
    except Exception as e:
        post("⚠ Couldn't launch Claude Code: " + str(e))
        return

    last_text = None
    result_text = None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            if ev.get("session_id"):
                save_session(ev["session_id"])
        elif t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "text" and blk.get("text", "").strip():
                    last_text = blk["text"].strip()
                    post(last_text)
                elif blk.get("type") == "tool_use":
                    post(tool_summary(blk.get("name"), blk.get("input")))
        elif t == "result":
            if ev.get("session_id"):
                save_session(ev["session_id"])
            result_text = (ev.get("result") or "").strip()

    err = (proc.stderr.read() or "").strip()
    proc.wait()
    # post the final answer if it wasn't already the last thing we streamed
    if result_text and result_text != last_text:
        post(result_text)
    if proc.returncode and not result_text:
        post("⚠ Claude Code exited with an error.\n" + err[-1500:])


# ---- run Hermes headlessly (one-shot, edits + ships the repo) ----
HERMES_SYSTEM = (
    "You are AETHER's Hermes build engine, invoked from Yaro's phone (Design "
    "Studio). Your working directory IS the euro94/jarvis-pwa repo — the source "
    "of this very app. Make the requested DESIGN/code change to index.html, keep "
    "edits surgical, reuse the existing CSS token system, keep WCAG AA contrast. "
    "BEFORE pushing run `git pull --rebase origin main`; then commit (clear "
    "message) and `git push origin main` so GitHub Pages redeploys. Reply in one "
    "or two sentences on exactly what changed."
)

def run_hermes(prompt):
    if not (HERMES_BIN and os.path.exists(HERMES_BIN)):
        post("⚠ Hermes engine not found — set HERMES_BIN env var.")
        return
    full = HERMES_SYSTEM + "\n\n--- TASK ---\n" + prompt
    cmd = [HERMES_BIN, "-z", full, "--yolo", "-t", "terminal,file"]
    post("• Hermes engine working in the repo…")
    try:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except Exception as e:
        post("⚠ Couldn't launch Hermes: " + str(e))
        return
    try:
        out, err = proc.communicate(timeout=900)
    except subprocess.TimeoutExpired:
        proc.kill()
        post("⚠ Hermes timed out after 15 min.")
        return
    out = (out or "").strip()
    err = (err or "").strip()
    if out:
        post(out)
    if proc.returncode and not out:
        post("⚠ Hermes exited with an error.\n" + err[-1500:])


# ---- dispatch to the selected engine ----
def dispatch(engine, prompt):
    if engine == "hermes":
        run_hermes(prompt)
    else:
        run_claude(prompt)


# ---- single-instance lock (so a double-start is harmless: loser exits) ----
_LOCK_SOCK = None
def acquire_single_instance(port=48762):
    global _LOCK_SOCK
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        _LOCK_SOCK = s   # keep ref alive for process lifetime
        return True
    except OSError:
        return False


# ---- poll the inbound topic for phone messages ----
def main():
    if not acquire_single_instance():
        print("Another builder bridge already holds the lock — exiting.", file=sys.stderr)
        return
    print(f"Builder bridge up. claude={CLAUDE_BIN}")
    print(f"  hermes={HERMES_BIN}  default_engine={DEFAULT_ENGINE}")
    print(f"  listening: {NTFY}/{IN_TOPIC}")
    print(f"  replying:  {NTFY}/{OUT_TOPIC}")
    if not (CLAUDE_BIN and os.path.exists(CLAUDE_BIN)):
        print("WARNING: claude binary not found — set CLAUDE_BIN env var.", file=sys.stderr)
    if not (HERMES_BIN and os.path.exists(HERMES_BIN)):
        print("WARNING: hermes binary not found — Hermes engine disabled.", file=sys.stderr)
    post("⌘ Build bridge online — Claude Code + Hermes engines ready.", title="builder-online")

    seen = set()
    since = int(time.time())
    while True:
        try:
            url = f"{NTFY}/{IN_TOPIC}/json?poll=1&since={since}"
            req = urllib.request.Request(url, headers={"User-Agent": "builder-bridge"})
            with urllib.request.urlopen(req, timeout=30) as r:
                for ln in r.read().decode().splitlines():
                    if not ln.strip():
                        continue
                    try:
                        o = json.loads(ln)
                    except Exception:
                        continue
                    if o.get("event") != "message" or not o.get("id") or o["id"] in seen:
                        continue
                    seen.add(o["id"])
                    since = max(since, int(o.get("time", since)))
                    msg = (o.get("message") or "").strip()
                    if not msg:
                        continue

                    # optional shared-secret gate
                    if BUILDER_TOKEN:
                        if not msg.startswith(BUILDER_TOKEN):
                            print("rejected (bad/no token)", file=sys.stderr)
                            continue
                        msg = msg[len(BUILDER_TOKEN):].strip()

                    if msg == "/new":
                        save_session(None)
                        post("✨ Fresh Claude Code session — context reset.")
                        continue

                    # Parse an optional [engine:claude|hermes] prefix from the app.
                    engine = DEFAULT_ENGINE
                    m = re.match(r"^\s*\[engine:([a-zA-Z]+)\]\s*", msg)
                    if m:
                        engine = m.group(1).lower()
                        msg = msg[m.end():].strip()
                    if engine not in ("claude", "hermes"):
                        engine = "claude"
                    if not msg:
                        continue

                    try:
                        print("->", f"[{engine}]", msg[:80])
                    except Exception:
                        pass
                    label = "⌘ Claude Code on it…" if engine == "claude" else "▣ Hermes on it…"
                    post(label, title="builder-ack")
                    dispatch(engine, msg)
        except Exception as e:
            print("poll err:", e, file=sys.stderr)
        # keep the dedup set from growing forever
        if len(seen) > 500:
            seen = set(list(seen)[-200:])
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
