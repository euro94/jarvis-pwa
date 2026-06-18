#!/usr/bin/env python
"""AETHER eval_daemon.py — continuous product intelligence on the local GPU.

Runs forever, cycling through every app screen as fast as the GPU allows.
Uses qwen2.5vl:7b via vision_local.py — zero API cost, zero cloud, free.

WHAT IT DOES EACH CYCLE:
  1. Screenshots every screen with headless Chrome (?eval=<id>)
  2. SHA-256s the screenshot — only re-evals if the screen changed
  3. Sends the image to the local vision model (Ollama, RTX 5070)
  4. Three-lens eval: CRITICAL (broken) · GAPS (missing) · EPIC (wow)
  5. Critical findings → immediate ntfy push to Yaro's phone
  6. New ideas → silently appended to BACKLOG.md (deduped)
  7. Daily midnight digest: summary of everything found that day

WHY NO THROTTLING:
  The GPU is sitting idle most of the time. Every idle cycle is a missed eval.
  The model takes ~10-15s per screen; 10 screens = ~2 minutes per full cycle.
  In 24h that's ~700 eval cycles. Run it continuously — make the GPU earn it.
  Screenshot hashing means the model only fires when the screen actually changed
  (after a ship or a hot-reload), so the eval isn't noisy on stable screens.

NTFY ALERTS (critical findings only):
  Sends to the Jarvis out topic so it lands alongside normal Jarvis messages.
  One alert per unique issue per screen — won't spam on repeat evals.

STARTUP:
  Placed in the Windows Startup folder so it's always running.
  Survives vision proxy downtime with exponential backoff.

Usage:
  python eval_daemon.py [--url URL] [--proxy http://127.0.0.1:8846]
                        [--ntfy https://yaro.tail6a3c7a.ts.net]
                        [--ntfy-topic hermes-yaro-jarvis-7450b76f]
                        [--backlog C:\\path\\BACKLOG.md]
                        [--no-alerts] [--no-backlog]
                        [--cycle-delay 0]        # seconds between cycles (0=max)
                        [--eval-delay 0]         # seconds between screens (0=max)
"""
import argparse
import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

# ── defaults ──────────────────────────────────────────────────────────────────
CHROME_DEFAULT = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
VISION_PROXY   = "http://127.0.0.1:8846"
APP_URL        = "https://euro94.github.io/jarvis-pwa/"
NTFY_BASE      = "https://yaro.tail6a3c7a.ts.net"
NTFY_TOPIC     = "hermes-yaro-jarvis-7450b76f"  # Jarvis out — same as agent messages
BACKLOG_PATH   = r"C:\Users\yaros\.hermes\jarvis-pwa\BACKLOG.md"
LOG_PATH       = r"C:\Users\yaros\.hermes\jarvis-pwa\eval_daemon.log"

SCREENS = [
    "screenHome", "screenChat", "screenHealth", "screenSleep",
    "screenPlan", "screenLearn", "screenRadar",
    "screenStream", "screenStudio", "screenSettings",
]

# ── screen context (same as eval_loop, defines purpose+epic bar per screen) ──
SCREEN_CTX = {
    "screenHome": dict(
        name="Home",
        purpose="Mission control. Agent quick-launch cards, today's activity, voice orb, "
                "fast-access to every pillar: Talk, Build, Learn, Health, Sleep, Plan, Radar.",
        epic="Opening it feels like a personal intelligence briefing — state of your day, "
             "most important task, body status. Not cards — living insight.",
    ),
    "screenChat": dict(
        name="Talk",
        purpose="Voice-first conversation with Jarvis agents. Voice orb, agent-switcher, chat history.",
        epic="Feels like talking to someone who knows you — your calendar, your audit crunch, "
             "your goals — and responds without prompting.",
    ),
    "screenHealth": dict(
        name="Health",
        purpose="Photo meal logging, macro rings (protein/carbs/fat), ambient strip "
                "(hydration/movement/sleep from Watch), cross-domain synthesis line, "
                "today timeline, hydration sparkline, voice-first dock. Local vision model.",
        epic="You open it and it already knows your day. Barely any logging — it logs itself.",
    ),
    "screenSleep": dict(
        name="Sleep",
        purpose="Big last-night number, 7-night bar chart (gold<7h), per-night log, "
                "sleep×focus×food reflection, text entry bar.",
        epic="'You focus best after 7h and this was your third short night in a row.' "
             "Connects sleep to your actual performance the next day.",
    ),
    "screenPlan": dict(
        name="Plan",
        purpose="Covey quadrant planning, agent-assisted prioritisation, calendar sync.",
        epic="Plan half-populated from calendar and tasks — you confirm, not start from scratch.",
    ),
    "screenLearn": dict(
        name="Learn",
        purpose="FSRS spaced-rep tutor, 27 FAR CPA topics, MCQ-first, agent as live tutor.",
        epic="'You've nailed depreciation but keep slipping on governmental funds. Let's do three.' "
             "A private tutor who knows exactly where you are.",
    ),
    "screenRadar": dict(
        name="Radar",
        purpose="AI workpaper reviewer. Upload → agent reviews → push notification with findings. "
                "Privacy mode uses local vision.",
        epic="Upload a workpaper, get a senior reviewer's first pass in under 60s.",
    ),
    "screenStream": dict(
        name="Stream",
        purpose="Live feed of all agent activity — tool calls, completions, ntfy events.",
        epic="Feels like watching your AI team at work. Each line is readable and meaningful.",
    ),
    "screenStudio": dict(
        name="Studio",
        purpose="Agent control hub: all agents, status, switch, trigger builds.",
        epic="Each agent card shows recent work and live status — a real control room.",
    ),
    "screenSettings": dict(
        name="Settings",
        purpose="Model, voice (Kokoro TTS), local vision toggle, iOS sync token, "
                "live mode, about/version, force update.",
        epic="Every toggle explains why you'd use it. Settings teaches the app's capabilities.",
    ),
}

EVAL_PROMPT = """You are AETHER's product intelligence engine. Evaluate this screenshot.

AETHER is Yaro's personal AI assistant PWA — a 30-something CPA at an accounting firm
in Sacramento. He preps for FAR CPA exam, works out at the gym, tracks sleep/food with
iPhone/Watch. He wants the app to feel like JARVIS from Iron Man — calm, confident,
genuinely intelligent. Dark navy/cyan theme, installed PWA.

SCREEN: {name}
PURPOSE: {purpose}
EPIC BAR: {epic}

Respond with ONLY valid JSON, no fences:
{{
  "overall": "epic|good|needs_work|broken",
  "critical": [
    {{"title":"...", "detail":"one sentence: what is broken", "fix":"one sentence fix"}}
  ],
  "gaps": [
    {{"title":"...", "detail":"one sentence: what should be here and why", "effort":"small|medium|large", "impact":"high|medium|low"}}
  ],
  "epic_idea": {{
    "title":"...",
    "detail":"2-3 sentences: specific feature, why amazing, what triggers it",
    "effort":"small|medium|large"
  }}
}}

Rules:
- critical[] EMPTY if nothing is genuinely broken (do not invent issues)
- gaps[] 0-3 entries max, only things visibly absent from the screenshot
- epic_idea: one specific, buildable idea — not vague
- overall "epic" = screen already delivers on its epic bar
"""

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger("eval")

# ── state ─────────────────────────────────────────────────────────────────────
class DaemonState:
    def __init__(self):
        self.screen_hashes: dict[str, str] = {}       # sid -> last screenshot hash
        self.alerted_issues: set[str] = set()          # hash of (sid+title) already alerted
        self.backlog_titles: set[str] = set()          # titles already in backlog
        self.daily_findings: list[dict] = []           # reset at midnight
        self.daily_ideas: list[dict] = []
        self.last_daily_digest: date | None = None
        self.cycle: int = 0
        self.total_evals: int = 0
        self.start_time: float = time.time()


# ── chrome ────────────────────────────────────────────────────────────────────
def screenshot(base_url: str, screen_id: str, out_path: str, chrome: str) -> bool:
    url = base_url.rstrip("/") + f"/?eval={screen_id}"
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--window-size=390,844", "--device-scale-factor=2",
        "--enable-logging=stderr", "--v=0",
        f"--screenshot={out_path}", "--virtual-time-budget=5000", url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        p = Path(out_path)
        return p.exists() and p.stat().st_size > 1000
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def img_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── vision ────────────────────────────────────────────────────────────────────
def call_vision(b64: str, prompt: str, proxy: str, timeout: int = 240) -> str:
    body = json.dumps({"image_b64": b64, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{proxy}/analyze", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("text", "")


def parse(raw: str, screen_id: str) -> dict:
    s = re.sub(r"^```(json)?", "", raw.strip(), flags=re.IGNORECASE)
    s = re.sub(r"```$", "", s.strip()).strip()
    a, b = s.find("{"), s.rfind("}")
    base = {"screen": screen_id, "overall": "unknown",
            "critical": [], "gaps": [], "epic_idea": None}
    if a < 0 or b < 0:
        return base
    try:
        d = json.loads(s[a:b+1])
        d["screen"] = screen_id
        return d
    except json.JSONDecodeError:
        return base


def vision_healthy(proxy: str) -> bool:
    try:
        with urllib.request.urlopen(f"{proxy}/health", timeout=6) as r:
            h = json.loads(r.read())
        return bool(h.get("ollama_up"))
    except Exception:
        return False


# ── ntfy ──────────────────────────────────────────────────────────────────────
def ntfy_push(base: str, topic: str, title: str, body: str, priority: str = "high"):
    try:
        req = urllib.request.Request(
            f"{base}/{topic}",
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "mag,aether-eval",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log.warning(f"ntfy push failed: {e}")


# ── backlog ────────────────────────────────────────────────────────────────────
def load_backlog_titles(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    text = p.read_text(encoding="utf-8", errors="ignore")
    return {m.group(1).strip().lower()[:40]
            for m in re.finditer(r'\*\*(.*?)\*\*', text)}


def append_backlog(path: str, entries: list[str], known: set[str]) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    text = p.read_text(encoding="utf-8", errors="ignore")
    new = []
    for e in entries:
        key = (re.search(r'\*\*(.*?)\*\*', e) or type("", (), {"group": lambda *a: e})()).group(1)
        short = key.strip().lower()[:40]
        if short not in known:
            new.append(e)
            known.add(short)
    if not new:
        return 0
    IDEAS = "\n## Ideas (eval-generated)\n"
    if IDEAS not in text:
        text = text.rstrip() + "\n" + IDEAS + "\n"
    insert = "\n".join(new) + "\n"
    text = text.replace(IDEAS + "\n", IDEAS + "\n" + insert)
    p.write_text(text, encoding="utf-8")
    return len(new)


# ── midnight digest ────────────────────────────────────────────────────────────
def send_digest(state: DaemonState, ntfy_base: str, ntfy_topic: str, no_alerts: bool):
    today = date.today()
    if state.last_daily_digest == today:
        return
    state.last_daily_digest = today
    if not state.daily_findings and not state.daily_ideas:
        return
    runtime_h = round((time.time() - state.start_time) / 3600, 1)
    crit_count = sum(len(r.get("critical", [])) for r in state.daily_findings)
    ideas_count = len(state.daily_ideas)
    lines = [
        f"🧠 AETHER eval — {today.strftime('%b %d')} digest",
        f"{state.total_evals} evals · {crit_count} critical · {ideas_count} new ideas · {runtime_h}h uptime",
    ]
    if crit_count:
        lines.append("\n🚨 Critical today:")
        for r in state.daily_findings:
            for c in r.get("critical", []):
                sname = SCREEN_CTX.get(r["screen"], {}).get("name", r["screen"])
                lines.append(f"  {sname}: {c.get('title','')}")
    if ideas_count:
        lines.append(f"\n✨ Top epic idea today:")
        # find a small-effort high-impact one
        for idea in state.daily_ideas:
            if idea.get("effort") == "small":
                lines.append(f"  {idea.get('screen_name','')}: {idea.get('title','')}")
                break
        else:
            if state.daily_ideas:
                first = state.daily_ideas[0]
                lines.append(f"  {first.get('screen_name','')}: {first.get('title','')}")
    body = "\n".join(lines)
    if not no_alerts:
        ntfy_push(ntfy_base, ntfy_topic, "AETHER nightly eval digest", body, "default")
    log.info(f"digest sent: {crit_count} critical, {ideas_count} ideas")
    # reset daily state
    state.daily_findings.clear()
    state.daily_ideas.clear()


# ── eval one screen ────────────────────────────────────────────────────────────
def eval_screen(sid: str, args, state: DaemonState, tmp: str) -> dict | None:
    ctx = SCREEN_CTX.get(sid, {})
    ss = os.path.join(tmp, f"{sid}.png")
    chrome = args.chrome if Path(args.chrome).exists() else \
             "/c/Program Files/Google/Chrome/Application/chrome.exe"

    if not screenshot(args.url, sid, ss, chrome):
        log.debug(f"  {sid}: screenshot failed")
        return None

    h = img_hash(ss)
    if state.screen_hashes.get(sid) == h:
        log.debug(f"  {sid}: no change (hash match)")
        return None  # screen unchanged since last eval — skip

    state.screen_hashes[sid] = h
    state.total_evals += 1

    prompt = EVAL_PROMPT.format(
        name=ctx.get("name", sid),
        purpose=ctx.get("purpose", ""),
        epic=ctx.get("epic", ""),
    )
    try:
        raw = call_vision(img_b64(ss), prompt, args.proxy, timeout=240)
        result = parse(raw, sid)
    except Exception as e:
        log.warning(f"  {sid}: vision error — {e}")
        return None

    nc = len(result.get("critical") or [])
    ng = len(result.get("gaps") or [])
    has_epic = bool(result.get("epic_idea"))
    log.info(f"  {sid}: {result.get('overall','?')} crit={nc} gaps={ng} epic={'✨' if has_epic else '—'}")

    return result


# ── handle results (alerts + backlog) ─────────────────────────────────────────
def handle_result(result: dict, state: DaemonState, args):
    sid = result["screen"]
    sname = SCREEN_CTX.get(sid, {}).get("name", sid)
    ts = datetime.now().strftime("%Y-%m-%d")

    # ── critical alerts ──────────────────────────────────────────────────────
    for c in result.get("critical") or []:
        key = hashlib.sha256(f"{sid}|{c.get('title','')}".encode()).hexdigest()[:12]
        if key not in state.alerted_issues:
            state.alerted_issues.add(key)
            state.daily_findings.append(result)
            title = f"🚨 {sname}: {c.get('title','')}"
            body = f"{c.get('detail','')}\n\n💡 {c.get('fix','')}"
            log.warning(f"CRITICAL — {sname}: {c.get('title','')}")
            if not args.no_alerts:
                ntfy_push(args.ntfy, args.ntfy_topic, title, body, "urgent")

    # ── backlog: gaps ────────────────────────────────────────────────────────
    entries = []
    for g in result.get("gaps") or []:
        title = (g.get("title") or "").strip()
        if not title:
            continue
        entries.append(
            f"- [ ] **{title}** [{sname}] — {g.get('detail','')} "
            f"`effort:{g.get('effort','?')}` `impact:{g.get('impact','?')}` _(eval {ts})_"
        )
        state.daily_ideas.append({"screen_name": sname, "title": title,
                                  "effort": g.get("effort","?")})

    # ── backlog: epic idea ────────────────────────────────────────────────────
    ei = result.get("epic_idea")
    if ei and ei.get("title"):
        title = ei["title"].strip()
        entries.append(
            f"- [ ] **✨ {title}** [{sname}] — {ei.get('detail','')} "
            f"`effort:{ei.get('effort','?')}` `impact:high` _(epic idea, eval {ts})_"
        )
        state.daily_ideas.append({"screen_name": sname, "title": f"✨ {title}",
                                  "effort": ei.get("effort","?")})

    if entries and not args.no_backlog:
        added = append_backlog(args.backlog, entries, state.backlog_titles)
        if added:
            log.info(f"  +{added} to BACKLOG")


# ── main loop ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url",        default=APP_URL)
    ap.add_argument("--proxy",      default=VISION_PROXY)
    ap.add_argument("--ntfy",       default=NTFY_BASE)
    ap.add_argument("--ntfy-topic", default=NTFY_TOPIC, dest="ntfy_topic")
    ap.add_argument("--backlog",    default=BACKLOG_PATH)
    ap.add_argument("--chrome",     default=CHROME_DEFAULT)
    ap.add_argument("--no-alerts",  action="store_true")
    ap.add_argument("--no-backlog", action="store_true")
    ap.add_argument("--cycle-delay", type=float, default=0,
                    help="seconds to wait between full cycles (0=as fast as GPU allows)")
    ap.add_argument("--eval-delay",  type=float, default=0,
                    help="seconds to wait between individual screen evals")
    args = ap.parse_args()

    state = DaemonState()
    if not args.no_backlog:
        state.backlog_titles = load_backlog_titles(args.backlog)

    log.info("=" * 60)
    log.info("AETHER eval daemon — continuous product intelligence")
    log.info(f"  url:     {args.url}")
    log.info(f"  proxy:   {args.proxy}")
    log.info(f"  backlog: {args.backlog}")
    log.info(f"  alerts:  {'off' if args.no_alerts else 'ntfy → '+args.ntfy_topic}")
    log.info(f"  screens: {len(SCREENS)}")
    log.info("=" * 60)

    # wait for vision proxy on startup (with backoff)
    backoff = 5
    while not vision_healthy(args.proxy):
        log.warning(f"vision proxy not ready — retrying in {backoff}s")
        time.sleep(backoff)
        backoff = min(backoff * 2, 120)
    log.info("vision proxy healthy — starting eval loop")

    with tempfile.TemporaryDirectory() as tmp:
        while True:
            state.cycle += 1
            log.info(f"── cycle {state.cycle} ──")

            # midnight digest
            now = datetime.now()
            if now.hour == 0 and now.minute < 5:
                send_digest(state, args.ntfy, args.ntfy_topic, args.no_alerts)

            # vision proxy health check every cycle
            if not vision_healthy(args.proxy):
                log.warning("vision proxy down — waiting 30s")
                time.sleep(30)
                continue

            for sid in SCREENS:
                result = eval_screen(sid, args, state, tmp)
                if result:
                    handle_result(result, state, args)
                if args.eval_delay > 0:
                    time.sleep(args.eval_delay)

            if args.cycle_delay > 0:
                time.sleep(args.cycle_delay)

            uptime_h = (time.time() - state.start_time) / 3600
            log.info(f"cycle {state.cycle} done | {state.total_evals} evals | "
                     f"{uptime_h:.1f}h uptime")


if __name__ == "__main__":
    main()
