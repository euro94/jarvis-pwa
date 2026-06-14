#!/usr/bin/env python
"""AETHER Web Push sender.
Sends a real Web Push notification to subscribed devices (the installed PWA),
using the VAPID keypair. Subscriptions are stored in subscriptions.json.

Usage:
  python push.py --title "AETHER" --body "Time to leave for the gym."
  python push.py --body "Did you make it to the gym?" \
      --action "yes:Yes:https://...log/done" --action "no:Skipped:https://...log/skip"
"""
import argparse, json, os, sys
from pywebpush import webpush, WebPushException

BASE = os.path.dirname(os.path.abspath(__file__))
SUBS = os.path.join(BASE, "subscriptions.json")
VAPID = json.load(open(os.path.join(BASE, "keys", "vapid.json")))
VAPID_PRIVATE_PEM = os.path.join(BASE, "keys", "private_key.pem")
# pywebpush wants the PEM path or the raw b64 private key; we pass the b64 priv.
VAPID_CLAIMS = {"sub": "mailto:yleshchik@icloud.com"}
ICON = "https://euro94.github.io/jarvis-pwa/icons/icon-192.png"


def load_subs():
    if not os.path.exists(SUBS):
        return []
    try:
        data = json.load(open(SUBS))
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def save_subs(subs):
    json.dump(subs, open(SUBS, "w"), indent=2)


def send(title, body, url=None, tag="jarvis", require=False, actions=None, action_urls=None, action_bodies=None):
    subs = load_subs()
    if not subs:
        print("No subscriptions yet. Enable push in the PWA first.")
        return 0
    payload = {
        "title": title, "body": body, "icon": ICON, "tag": tag,
        "requireInteraction": require, "url": url or "https://euro94.github.io/jarvis-pwa/",
    }
    if actions:
        payload["actions"] = actions
    if action_urls:
        payload["actionUrls"] = action_urls
    if action_bodies:
        payload["actionBodies"] = action_bodies

    ok, dead = 0, []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps(payload),
                vapid_private_key=VAPID["private_key"],
                vapid_claims=dict(VAPID_CLAIMS),
            )
            ok += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):  # gone -> prune
                dead.append(sub)
            print(f"push error ({code}): {e}", file=sys.stderr)
    if dead:
        save_subs([s for s in subs if s not in dead])
        print(f"pruned {len(dead)} dead subscription(s)")
    print(f"sent to {ok}/{len(subs)} device(s)")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="AETHER")
    ap.add_argument("--body", required=True)
    ap.add_argument("--url")
    ap.add_argument("--tag", default="jarvis")
    ap.add_argument("--require", action="store_true")
    # --action id:Label:URL  (repeatable) — optional 4th field :BODY for POST body
    ap.add_argument("--action", action="append", default=[])
    a = ap.parse_args()

    actions, action_urls, action_bodies = [], {}, {}
    for spec in a.action:
        parts = spec.split(":", 3)
        if len(parts) >= 3:
            aid, label, aurl = parts[0], parts[1], parts[2]
            actions.append({"action": aid, "title": label})
            action_urls[aid] = aurl
            if len(parts) == 4:
                action_bodies[aid] = parts[3]
    send(a.title, a.body, url=a.url, tag=a.tag, require=a.require,
         actions=actions or None, action_urls=action_urls or None,
         action_bodies=action_bodies or None)


if __name__ == "__main__":
    main()
