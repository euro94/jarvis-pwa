#!/usr/bin/env python
"""AETHER eval_loop.py — LOCAL product intelligence engine.

Runs entirely on the local GPU (Ollama + qwen2.5vl:7b). Zero API cost per run.

This is NOT just a bug finder. It asks three questions about every screen:

  1. CRITICAL — what's broken / unacceptable right now (ship blockers, crashes,
     data loss, screens that are blank or unusable).
  2. GAPS — what's conspicuously missing that a screen this ambitious should have:
     features implied by the design but not there, states that aren't handled,
     data that should be surfacing but isn't.
  3. EPIC — what specific, concrete change would make this screen go from good to
     genuinely amazing: the one idea that would make someone say "oh wow".

GAPS and EPIC ideas auto-file into BACKLOG.md so the loop feeds the loop.
The builder loop picks them up on the next run.

Designed to run as a Hermes cron (no_agent=True, 2am daily). Silent when nothing
new to report. When it fires, you get both a digest and new BACKLOG entries.

Usage:
  python eval_loop.py [--url URL] [--screens s1,...] [--min-severity low|medium|high]
                      [--backlog /path/BACKLOG.md] [--no-backlog] [--json]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ---- config -------------------------------------------------------------------
CHROME = os.environ.get(
    "CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
VISION_PROXY = os.environ.get("VISION_PROXY", "http://127.0.0.1:8846")
APP_URL = os.environ.get("AETHER_APP_URL", "https://euro94.github.io/jarvis-pwa/")
BACKLOG_PATH = os.environ.get(
    "AETHER_BACKLOG",
    r"C:\Users\yaros\.hermes\jarvis-pwa\BACKLOG.md",
)

SCREENS = [
    "screenHome",
    "screenChat",
    "screenHealth",
    "screenSleep",
    "screenPlan",
    "screenLearn",
    "screenRadar",
    "screenStream",
    "screenStudio",
    "screenSettings",
]

SEV = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# ─── SCREEN CONTEXT ───────────────────────────────────────────────────────────
# Each entry tells the model:  what this screen IS, what it's SUPPOSED to do,
# what the user is Yaro is trying to accomplish there, and the EPIC bar.
SCREEN_CTX = {
    "screenHome": dict(
        name="Home / Dashboard",
        purpose="Yaro's mission control. Shows his agents as quick-launch cards, "
                "today's activity, a voice orb shortcut, and fast-access to every "
                "pillar: Talk, Build (Studio), Learn (Tutor), Health, Sleep, Plan, Radar.",
        epic_bar="The screen feels like a personal intelligence briefing — the moment "
                 "you open it, you know the state of your day, your most important task, "
                 "and how your body is doing. Not cards — insight.",
    ),
    "screenChat": dict(
        name="Talk / Chat",
        purpose="Voice-first conversation with Jarvis agents. Has a live voice orb, "
                "agent-switcher, and full chat history.",
        epic_bar="The conversation feels like talking to someone who knows you deeply — "
                 "your calendar, your goals, your current audit crunch — and responds "
                 "appropriately. Voice feels instant and natural, zero friction.",
    ),
    "screenHealth": dict(
        name="Health",
        purpose="Photo-first food logging, macro rings (protein/carbs/fat), an ambient "
                "strip (hydration/movement/sleep), a cross-domain synthesis line, a "
                "timeline of today's food+water+movement+mood, hydration sparkline, "
                "voice+chip dock. Uses LOCAL vision model for meal analysis — no cloud.",
        epic_bar="You open it and it already knows your day. Sleep from last night, "
                 "steps synced from your Watch, the one protein nudge that's actually "
                 "true for you right now. You barely need to log — it logs itself.",
    ),
    "screenSleep": dict(
        name="Sleep",
        purpose="Dedicated sleep tab: big last-night number, 7-night bar chart "
                "(gold for < 7h), a per-night log, a cross-domain reflection "
                "(sleep × focus × food), and a text entry bar to log manually.",
        epic_bar="The reflection line says something only Aether would know — "
                 "'you focus best after 7h and this was your third short night in a row.' "
                 "It connects sleep to performance in a way that feels personal and actionable.",
    ),
    "screenPlan": dict(
        name="Plan (First Things First)",
        purpose="Covey quadrant planning: important+urgent / important+not-urgent / etc. "
                "Agent-assisted prioritisation. Syncs with Jarvis for scheduling suggestions.",
        epic_bar="Your plan for the day appears already half-populated from your calendar "
                 "and pending tasks. You just confirm and reprioritize — not start from scratch.",
    ),
    "screenLearn": dict(
        name="Learn / Tutor",
        purpose="Spaced-repetition flashcard tutor (FSRS). Currently seeded with 27 "
                "FAR CPA exam topics. MCQ-first, agent acts as live tutor.",
        epic_bar="Feels like a private tutor who knows exactly where you are in FAR prep "
                 "and meets you there — not a generic flashcard app. 'You've nailed depreciation "
                 "but keep slipping on governmental funds. Let's do three of those.'",
    ),
    "screenRadar": dict(
        name="Review Radar",
        purpose="AI-powered workpaper reviewer for Yaro's accounting practice. "
                "Upload a workpaper → agent reviews it → findings delivered via push. "
                "Privacy mode routes through local vision model.",
        epic_bar="Uploading a workpaper feels instant and confident. The AI reply "
                 "arrives in under 60s with specific, professional comments — as good "
                 "as a senior reviewer's first pass.",
    ),
    "screenStream": dict(
        name="Stream / Activity Feed",
        purpose="Live feed of all agent activity — what Jarvis is doing across all "
                "pillars. Tool calls, completions, ntfy events.",
        epic_bar="Feels like watching your AI team at work. Each activity line is "
                 "readable and meaningful — not a wall of JSON.",
    ),
    "screenStudio": dict(
        name="Studio / Builder",
        purpose="Agent management hub: see all agents (Jarvis/Research/Reviewer), "
                "their status, switch between them, trigger builds.",
        epic_bar="Each agent card shows its recent work and status at a glance — "
                 "not just a list, a control room.",
    ),
    "screenSettings": dict(
        name="Settings",
        purpose="App configuration: model, voice (Kokoro TTS), local vision toggle, "
                "iOS sync token, live mode, about/version, force update.",
        epic_bar="Every toggle has a one-line explanation of why you'd use it. "
                 "Settings teaches you what the app can do.",
    ),
}

# ─── THE PROMPT ────────────────────────────────────────────────────────────────
PRODUCT_EVAL_PROMPT = """You are AETHER's product intelligence engine. You have deep context about this app:

AETHER is Yaro's personal AI assistant PWA — built for a 30-something CPA at an accounting firm in Sacramento. He commutes 40min, preps for the FAR CPA exam, works out at the gym, tracks sleep and food with his iPhone/Watch, and ships code on weeknights. He wants the app to feel like JARVIS from Iron Man — calm, confident, genuinely intelligent. It runs on his iPhone as an installed PWA in a dark navy/cyan cyberpunk theme.

YOU ARE EVALUATING: {screen_name}
PURPOSE: {purpose}
THE EPIC BAR: {epic_bar}

You are looking at a screenshot of this screen RIGHT NOW.

Think like a senior product designer who has shipped consumer mobile apps. Ask three questions:

1. CRITICAL ISSUES — Is anything broken, blank, or unusable right now? What would make a user close the app in frustration or confusion? Be honest and specific. If nothing is critical, say so.

2. MISSING POTENTIAL — What is conspicuously absent that this screen's purpose demands? Think about:
   - Data that should be here but isn't (personalization, context, history)
   - States that aren't handled gracefully (empty, loading, error, first-time)
   - Features that the design promises but doesn't yet deliver
   - Connections to other screens/data that are missing (cross-domain)
   Be specific. "Add machine learning" is not a gap. "The synthesis line says the same generic phrase every day instead of adapting to yesterday's logged data" IS a gap.

3. THE EPIC IDEA — One concrete, specific, buildable change that would make someone say "oh wow, this app actually gets me." Not a vague improvement — a real feature or UX moment. Think small and powerful. What would Yaro tell a friend about?

Respond with ONLY valid JSON. No prose, no markdown fences. Exactly this schema:
{{
  "screen": "{screen_id}",
  "overall": "epic|good|needs_work|broken",
  "critical": [
    {{
      "title": "short title",
      "detail": "one clear sentence: what is broken and where",
      "fix": "one sentence: what would fix it"
    }}
  ],
  "gaps": [
    {{
      "title": "short title — the missing thing",
      "detail": "one sentence: what should be there and why it matters",
      "effort": "small|medium|large",
      "impact": "high|medium|low"
    }}
  ],
  "epic_idea": {{
    "title": "short punchy title",
    "detail": "2-3 sentences: the specific feature or moment, why it would feel amazing, and what data/trigger it needs",
    "effort": "small|medium|large"
  }}
}}

Rules:
- critical[] is EMPTY if nothing is actually broken — do not invent issues
- gaps[] has 0-4 entries — only things you can genuinely see are missing from the screenshot
- epic_idea is ONE idea — the single best one; make it specific and buildable
- effort: small = a few hours of code, medium = a day or two, large = a week+
- impact: would Yaro actually use / notice / tell someone about this?
- overall "epic" = screen delivers on its epic bar and then some
- Do NOT repeat ideas across multiple fields — each idea appears exactly once
"""


# ─── helpers ──────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[eval] {msg}", file=sys.stderr, flush=True)


def screenshot_screen(base_url: str, screen_id: str, out_path: str) -> bool:
    chrome = CHROME
    if not Path(chrome).exists():
        chrome = "/c/Program Files/Google/Chrome/Application/chrome.exe"
    url = base_url.rstrip("/") + f"/?eval={screen_id}"
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--window-size=390,844", "--device-scale-factor=2",
        "--enable-logging=stderr", "--v=0",
        f"--screenshot={out_path}", "--virtual-time-budget=5000", url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        return Path(out_path).exists() and Path(out_path).stat().st_size > 1000
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log(f"  Chrome failed: {e}")
        return False


def img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def call_vision(image_b64: str, prompt: str, timeout: int = 180) -> str:
    body = json.dumps({"image_b64": image_b64, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{VISION_PROXY}/analyze", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("text", "")


def parse_result(raw: str, screen_id: str) -> dict:
    s = re.sub(r"^```(json)?", "", raw.strip(), flags=re.IGNORECASE)
    s = re.sub(r"```$", "", s.strip()).strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < 0:
        return {"screen": screen_id, "overall": "unknown", "critical": [], "gaps": [], "epic_idea": None}
    try:
        return json.loads(s[a:b+1])
    except json.JSONDecodeError:
        return {"screen": screen_id, "overall": "unknown", "critical": [], "gaps": [], "epic_idea": None}


def effort_emoji(e: str) -> str:
    return {"small": "🟢", "medium": "🟡", "large": "🔴"}.get((e or "").lower(), "⚪")


def impact_emoji(i: str) -> str:
    return {"high": "🔥", "medium": "📈", "low": "💧"}.get((i or "").lower(), "❓")


# ─── BACKLOG integration ──────────────────────────────────────────────────────

def backlog_entry_exists(backlog_text: str, title: str) -> bool:
    """Check if a similar entry already exists (fuzzy: first 30 chars of title)."""
    key = title.strip().lower()[:30]
    return key in backlog_text.lower()


def append_to_backlog(backlog_path: str, new_entries: list[str]) -> int:
    """Insert new entries into the Ideas section of BACKLOG.md. Returns count added."""
    if not new_entries:
        return 0
    path = Path(backlog_path)
    if not path.exists():
        log(f"  BACKLOG not found at {backlog_path} — skipping backlog write")
        return 0
    text = path.read_text(encoding="utf-8")
    added = [e for e in new_entries if not backlog_entry_exists(text, e.split("**")[1] if "**" in e else e)]
    if not added:
        return 0
    # Find or create the Ideas section
    IDEAS_HEADER = "\n## Ideas (eval-generated)\n"
    if "## Ideas (eval-generated)" not in text:
        text = text.rstrip() + "\n" + IDEAS_HEADER + "\n"
    else:
        # insert after the section header
        text = text.replace(IDEAS_HEADER, IDEAS_HEADER + "\n")
    insert_block = "\n".join(added) + "\n"
    text = text.replace(IDEAS_HEADER + "\n", IDEAS_HEADER + "\n" + insert_block)
    path.write_text(text, encoding="utf-8")
    log(f"  added {len(added)} entries to BACKLOG")
    return len(added)


def results_to_backlog_entries(results: list[dict]) -> list[str]:
    entries = []
    ts = datetime.now().strftime("%Y-%m-%d")
    for r in results:
        sid = r.get("screen", "?")
        ctx = SCREEN_CTX.get(sid, {})
        sname = ctx.get("name", sid)

        # gaps → backlog
        for g in r.get("gaps") or []:
            title = (g.get("title") or "").strip()
            detail = (g.get("detail") or "").strip()
            effort = (g.get("effort") or "?").lower()
            impact = (g.get("impact") or "?").lower()
            if not title:
                continue
            entries.append(
                f"- [ ] **{title}** [{sname}] — {detail} "
                f"`effort:{effort}` `impact:{impact}` _(eval {ts})_"
            )

        # epic idea → backlog (highest priority treatment)
        ei = r.get("epic_idea")
        if ei and ei.get("title"):
            title = (ei.get("title") or "").strip()
            detail = (ei.get("detail") or "").strip()
            effort = (ei.get("effort") or "?").lower()
            entries.append(
                f"- [ ] **✨ {title}** [{sname}] — {detail} "
                f"`effort:{effort}` `impact:high` _(epic idea, eval {ts})_"
            )
    return entries


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=APP_URL)
    ap.add_argument("--local-url", default="")
    ap.add_argument("--screens", default="")
    ap.add_argument("--min-severity", default="low",
                    choices=["low", "medium", "high"])
    ap.add_argument("--backlog", default=BACKLOG_PATH)
    ap.add_argument("--no-backlog", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    base_url = args.local_url or args.url
    screens = [s.strip() for s in args.screens.split(",") if s.strip()] or SCREENS

    # check vision proxy
    try:
        with urllib.request.urlopen(f"{VISION_PROXY}/health", timeout=6) as r:
            h = json.loads(r.read())
        if not h.get("ollama_up"):
            log("Ollama is down — aborting"); sys.exit(1)
    except Exception as e:
        log(f"vision proxy unreachable ({e})"); sys.exit(1)

    log(f"product eval — {len(screens)} screens | {base_url}")
    log(f"model: {h.get('model','?')} (local, free)")

    results = []

    with tempfile.TemporaryDirectory() as tmp:
        for sid in screens:
            ctx = SCREEN_CTX.get(sid, {})
            log(f"  [{sid}] screenshot…")
            ss = os.path.join(tmp, f"{sid}.png")
            if not screenshot_screen(base_url, sid, ss):
                log(f"  [{sid}] screenshot failed — skip")
                continue

            prompt = PRODUCT_EVAL_PROMPT.format(
                screen_name=ctx.get("name", sid),
                purpose=ctx.get("purpose", sid),
                epic_bar=ctx.get("epic_bar", ""),
                screen_id=sid,
            )
            t0 = time.time()
            try:
                raw = call_vision(img_to_b64(ss), prompt, timeout=240)
                r = parse_result(raw, sid)
                r["elapsed_s"] = round(time.time() - t0, 1)
                results.append(r)
                nc = len(r.get("critical") or [])
                ng = len(r.get("gaps") or [])
                ei = "✨" if r.get("epic_idea") else "—"
                log(f"  [{sid}] {r.get('overall','?')} | crit={nc} gaps={ng} epic={ei} ({r['elapsed_s']}s)")
            except Exception as e:
                log(f"  [{sid}] vision failed: {e}")

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # ─── write backlog ──────────────────────────────────────────────────────
    backlog_added = 0
    if not args.no_backlog:
        entries = results_to_backlog_entries(results)
        backlog_added = append_to_backlog(args.backlog, entries)

    # ─── decide if there's anything worth reporting ─────────────────────────
    has_critical = any(r.get("critical") for r in results)
    has_gaps = any(r.get("gaps") for r in results)
    has_epic = any(r.get("epic_idea") for r in results)

    if not (has_critical or has_gaps or has_epic or backlog_added):
        log("nothing to report — staying silent")
        sys.exit(0)

    # ─── build the report ────────────────────────────────────────────────────
    ts = datetime.now().strftime("%b %d %Y %H:%M")
    broken = [r["screen"].replace("screen","") for r in results if r.get("overall") == "broken"]
    epic_screens = [r["screen"].replace("screen","") for r in results if r.get("overall") == "epic"]

    lines = [
        f"## 🧠 AETHER product eval — {ts}",
        "",
        f"Evaluated **{len(results)} screens** locally (free, {h.get('model','qwen2.5vl')}, RTX 5070)."
        + (f" 🔴 Broken: {', '.join(broken)}." if broken else "")
        + (f" ⭐ Epic already: {', '.join(epic_screens)}." if epic_screens else ""),
        "",
    ]

    # ── CRITICAL section ─────────────────────────────────────────────────────
    crit_results = [r for r in results if r.get("critical")]
    if crit_results:
        lines += ["### 🚨 Critical issues — fix before next ship", ""]
        for r in crit_results:
            sname = SCREEN_CTX.get(r["screen"], {}).get("name", r["screen"])
            for c in r["critical"]:
                lines += [
                    f"**{sname}: {c.get('title','')}**",
                    f"> {c.get('detail','')}",
                    f"💡 {c.get('fix','')}",
                    "",
                ]

    # ── GAPS section ─────────────────────────────────────────────────────────
    gap_results = [r for r in results if r.get("gaps")]
    if gap_results:
        # sort by impact then effort
        def gap_sort_key(item):
            impact_v = {"high":2,"medium":1,"low":0}
            effort_v = {"small":0,"medium":1,"large":2}
            g = item[1]
            return (-impact_v.get(g.get("impact","low"), 0), effort_v.get(g.get("effort","large"), 2))

        all_gaps = []
        for r in gap_results:
            sname = SCREEN_CTX.get(r["screen"], {}).get("name", r["screen"])
            for g in (r.get("gaps") or []):
                all_gaps.append((sname, g))
        all_gaps.sort(key=gap_sort_key)

        lines += ["### 🕳️ Missing potential — what should be here", ""]
        for sname, g in all_gaps:
            lines += [
                f"{effort_emoji(g.get('effort'))} {impact_emoji(g.get('impact'))} "
                f"**{sname}: {g.get('title','')}**",
                f"> {g.get('detail','')}",
                "",
            ]

    # ── EPIC IDEAS section ────────────────────────────────────────────────────
    epic_results = [r for r in results if r.get("epic_idea")]
    if epic_results:
        # sort: small-effort high-impact first
        def epic_sort_key(r):
            ei = r.get("epic_idea") or {}
            effort_v = {"small":0,"medium":1,"large":2}
            return effort_v.get(ei.get("effort","large"), 2)
        epic_results.sort(key=epic_sort_key)

        lines += ["### ✨ Epic ideas — the 'oh wow' moments", ""]
        for r in epic_results:
            ei = r["epic_idea"]
            sname = SCREEN_CTX.get(r["screen"], {}).get("name", r["screen"])
            lines += [
                f"{effort_emoji(ei.get('effort'))} **{sname}: {ei.get('title','')}**",
                f"> {ei.get('detail','')}",
                "",
            ]

    # ── footer ────────────────────────────────────────────────────────────────
    if backlog_added:
        lines += [f"📋 *{backlog_added} idea(s) auto-filed into BACKLOG.md*", ""]
    lines += [
        "---",
        f"*local eval · {h.get('model','qwen2.5vl')} · {len(results)} screens · free*",
    ]

    report = "\n".join(lines)
    print(report)


if __name__ == "__main__":
    main()
