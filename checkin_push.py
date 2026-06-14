#!/usr/bin/env python
"""JARVIS interactive habit check-in via Web Push (branded, lock-screen buttons).

Mirrors the old ntfy checkin.py loop, but pushes through the JARVIS PWA:
  - sends a branded push with ✅ Did it / ❌ Skipped / 🟡 Partial buttons
  - each button silently POSTs "Log <habit>: <status>" to the INBOUND ntfy topic
  - the gateway delivers that to Jarvis, who logs it via coach.py and replies

No app opening, no typing — tap from the lock screen.

Usage:
  python checkin_push.py --habit "Gym" --question "Good morning — did you hit the gym? 💪"
"""
import argparse, sys, urllib.parse
import push as pushmod

INBOUND_TOPIC = "hermes-yaro-jarvis-in-c4e3ac0f"
NTFY = "https://ntfy.sh"


def send_checkin(habit, question, tag="jarvis-checkin"):
    # iOS Safari/PWA ignores Web Push action buttons, so the reliable path is:
    # tapping the notification opens the app at ?log=<habit>, which shows a
    # one-tap log sheet that POSTs "Log <habit>: <status>" to the inbound topic.
    # (Action buttons are still included for macOS/Android where they DO render.)
    open_url = f"https://euro94.github.io/jarvis-pwa/?log={habit}"
    url = f"{NTFY}/{INBOUND_TOPIC}"
    actions = [
        {"action": "done", "title": "\u2705 Did it"},
        {"action": "skipped", "title": "\u274c Skipped"},
        {"action": "partial", "title": "\U0001f7e1 Partial"},
    ]
    action_urls = {"done": url, "skipped": url, "partial": url}
    action_bodies = {
        "done": f"Log {habit}: done",
        "skipped": f"Log {habit}: skipped",
        "partial": f"Log {habit}: partial",
    }
    return pushmod.send(
        "J.A.R.V.I.S.", question, url=open_url, tag=tag, require=True,
        actions=actions, action_urls=action_urls, action_bodies=action_bodies,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--habit", default="Gym")
    ap.add_argument("--question", default="Good morning \u2014 did you hit the gym? \U0001f4aa")
    a = ap.parse_args()
    n = send_checkin(a.habit, a.question)
    print(f"check-in pushed for habit '{a.habit}'")
    sys.exit(0 if n else 1)


if __name__ == "__main__":
    main()
