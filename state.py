#!/usr/bin/env python
"""JARVIS state publisher.
Composes Yaro's live status (next event, leave-by, weather, focus, gym streak)
from the existing context scripts and publishes a compact JSON blob to the
ntfy STATE topic. The PWA Home tab polls that topic and renders it.

Run from cron (e.g. every 30 min, plus on demand):
  python state.py
"""
import json, os, subprocess, sys, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.expanduser("~"), ".hermes", "scripts")
STATE_TOPIC = "hermes-yaro-jarvis-state-85ec36fe"
NTFY = "https://ntfy.sh"
PY = sys.executable


def run_json(args, timeout=45):
    try:
        out = subprocess.run([PY] + args, capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout.strip() or "null")
    except Exception:
        return None


def run_text(args, timeout=45):
    try:
        out = subprocess.run([PY] + args, capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip()
    except Exception:
        return ""


def s(p):
    return os.path.join(SCRIPTS, p)


def first_upcoming_event():
    """Parse ical.py agenda for the next timed event today/tomorrow."""
    txt = run_text([s("ical.py"), "agenda"])
    next_evt = None
    for line in txt.splitlines():
        line = line.rstrip()
        # lines like '  09:00  Title  [Calendar]'
        st = line.strip()
        if len(st) >= 5 and st[:2].isdigit() and st[2] == ":":
            time_part = st[:5]
            rest = st[5:].strip()
            # strip [Calendar] tag
            if "[" in rest:
                rest = rest[: rest.rfind("[")].strip()
            next_evt = f"{time_part} · {rest}"
            break
    return next_evt


def weather_line():
    w = run_json([s("context.py"), "weather", "--days", "1"])
    try:
        d = w["home"][0]
        return f"{d['summary']}, {d['high_f']}°/{d['low_f']}°"
    except Exception:
        return None


def commute_leaveby():
    c = run_json([s("context.py"), "commute", "--direction", "to_work"])
    try:
        # if config provides a target arrival or leave_by, prefer it
        if c.get("leave_by"):
            return c["leave_by"]
        est = c.get("estimated_min")
        if est:
            return f"~{est} min drive"
    except Exception:
        pass
    return None


def gym_streak():
    st = run_json([s("coach.py"), "streak", "--event", "Gym"])
    try:
        return st.get("current_done_streak", 0)
    except Exception:
        return 0


def headline(next_evt, streak):
    h = datetime.datetime.now().hour
    if next_evt:
        return f"Next up: {next_evt.split(' · ',1)[-1]}"
    if h < 12:
        return "Clear morning. Let's move."
    if h < 18:
        return "Afternoon. Stay on plan."
    return "Evening. Wind down well."


def build_state():
    next_evt = first_upcoming_event()
    streak = gym_streak()
    return {
        "headline": headline(next_evt, streak),
        "next": next_evt or "Nothing scheduled",
        "leaveby": commute_leaveby() or "—",
        "weather": weather_line() or "—",
        "focus": "Gym + ship JARVIS" if streak else "Build the streak",
        "streak": streak,
        "updated_at": datetime.datetime.now().isoformat(timespec="minutes"),
    }


def publish(state):
    body = json.dumps(state)
    req = urllib.request.Request(
        f"{NTFY}/{STATE_TOPIC}",
        data=body.encode(),
        headers={"Title": "jarvis-state", "Tags": "satellite"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except Exception as e:
        print("publish error:", e, file=sys.stderr)
        return None


def main():
    state = build_state()
    code = publish(state)
    print(json.dumps({"published": code, "state": state}, indent=2))


if __name__ == "__main__":
    main()
