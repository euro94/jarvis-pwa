#!/usr/bin/env python
"""JARVIS subscription receiver.
Polls the ntfy sub-capture topic for subscription objects the PWA POSTs when
you tap "Enable Push", and saves them to subscriptions.json. Also handles
TEST_PUSH requests (fires a test notification immediately).

Run once after enabling push in the app:
  python sub_receiver.py --since 10m
Or leave running to keep catching re-subscriptions:
  python sub_receiver.py --watch
"""
import argparse, json, os, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SUBS = os.path.join(BASE, "subscriptions.json")
SUB_TOPIC = "hermes-yaro-jarvis-pwa-sub-426e9ec3"
NTFY = "https://yaro.tail6a3c7a.ts.net"


def load():
    if os.path.exists(SUBS):
        try:
            d = json.load(open(SUBS))
            return d if isinstance(d, list) else [d]
        except Exception:
            return []
    return []


def save(subs):
    json.dump(subs, open(SUBS, "w"), indent=2)


def add_sub(sub):
    subs = load()
    eps = {s.get("endpoint") for s in subs}
    if sub.get("endpoint") not in eps:
        subs.append(sub)
        save(subs)
        print(f"+ saved subscription ({sub['endpoint'][:50]}...) total={len(subs)}")
    else:
        print("= subscription already stored")


def fire_test():
    import subprocess
    subprocess.run([sys.executable, os.path.join(BASE, "push.py"),
                    "--title", "J.A.R.V.I.S.",
                    "--body", "Systems online. This is a live push to your iPhone. \u2713",
                    "--tag", "jarvis-test"])


def poll(since):
    url = f"{NTFY}/{SUB_TOPIC}/json?poll=1&since={since}"
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis"})
    with urllib.request.urlopen(req, timeout=30) as r:
        for line in r.read().decode().splitlines():
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("event") != "message":
                continue
            msg = o.get("message", "")
            if msg.strip() == "TEST_PUSH":
                print("test push requested -> firing")
                fire_test()
                continue
            try:
                sub = json.loads(msg)
                if sub.get("endpoint"):
                    add_sub(sub)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="10m")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    if a.watch:
        print("watching for subscriptions (Ctrl-C to stop)...")
        last = a.since
        while True:
            try:
                poll(last)
            except Exception as e:
                print("poll err:", e, file=sys.stderr)
            last = "30s"
            time.sleep(20)
    else:
        poll(a.since)
        print("done. stored:", len(load()))


if __name__ == "__main__":
    main()
