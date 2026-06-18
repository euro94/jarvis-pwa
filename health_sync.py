#!/usr/bin/env python
"""AETHER iOS Health sync receiver — bridges Apple Health -> the PWA.

A PWA cannot read Apple HealthKit directly (no web API). So the iPhone PUSHES
its Health data to this host receiver, and the app PULLS the normalized result
from /latest and merges it into the Health + Sleep tabs. Same tailnet/ntfy spine
as meals & uploads — no App Store, no cloud.

TWO INGEST FORMATS, ONE NORMALIZED OUTPUT
  1. Apple Shortcuts (free): a Shortcut reads Health, builds simple JSON, POSTs
     it here. We define this shape (see SHORTCUT FORMAT below).
  2. Health Auto Export (~$5 app): background-syncs HealthKit to a REST endpoint
     in its own nested {"data":{"metrics":[...],"workouts":[...]}} shape.
  Both are detected and normalized to the SAME entry list the app understands.

  iPhone --POST /ingest {health json}--> health_sync.py --normalize+dedupe-->
                                              latest.json
  PWA --GET /latest?token=...------------------^  (merged into HX_ENTRIES)

ENDPOINTS
  POST /ingest        accept either format; token via ?token= or X-Aether-Token
  GET  /latest        return the normalized records (token-guarded)
  GET  /health        liveness

DEDUPE: every normalized record carries a stable `sid`
  ios-sleep-<day>, ios-steps-<day>, ios-workout-<startISO>
so a re-sync UPDATES the same record rather than piling up duplicates. The app
upserts on `sid`.

SECURITY: the host is on Tailscale Funnel (publicly reachable), so /ingest and
/latest REQUIRE a shared token (env AETHER_SYNC_TOKEN, default below — change it).
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("HEALTH_SYNC_PORT", "8848"))
TOKEN = os.environ.get("AETHER_SYNC_TOKEN", "aether-sync-7e3f9c")  # CHANGE THIS
ALLOW_ORIGIN = os.environ.get("SYNC_ALLOW_ORIGIN", "https://euro94.github.io")
STORE = os.environ.get("HEALTH_SYNC_STORE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "health_sync_store.json"))
MAX_BODY = 8 * 1024 * 1024
KEEP_DAYS = 30


def day_key_from_iso(iso):
    """Local-ish day key 'YYYY-M-D' matching the app's hxDayKey (no zero-pad)."""
    dt = parse_dt(iso)
    if not dt:
        dt = datetime.now()
    return f"{dt.year}-{dt.month}-{dt.day}"


def parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    # Health Auto Export: "2024-06-18 07:05:00 -0700"; Shortcuts/ISO: "2024-06-18T07:05:00Z"
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") and s.endswith("Z") else s, fmt)
        except (ValueError, TypeError):
            continue
    # last resort: epoch seconds/millis
    try:
        n = float(s)
        if n > 1e12:
            n /= 1000.0
        return datetime.fromtimestamp(n)
    except (ValueError, TypeError):
        return None


def to_ms(dt):
    if not dt:
        return int(time.time() * 1000)
    try:
        return int(dt.timestamp() * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fmt_min(m):
    m = int(round(m))
    h, mm = m // 60, m % 60
    return f"{h}h" + (f" {mm}m" if mm else "")


def normalize(payload):
    """Return a list of normalized records from EITHER ingest format."""
    out = []
    # ---- Health Auto Export shape: {"data": {"metrics": [...], "workouts": [...]}} ----
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data and (isinstance(data.get("metrics"), list) or isinstance(data.get("workouts"), list)):
        out += _from_auto_export(data)
        return out
    # ---- Apple Shortcuts shape: flat, we defined it ----
    out += _from_shortcuts(payload)
    return out


def _from_auto_export(data):
    recs = []
    # sleep: metric name 'sleep_analysis'; sum asleep hours per day
    by_day_sleep = {}
    by_day_steps = {}
    for m in data.get("metrics", []) or []:
        name = (m.get("name") or "").lower()
        for d in m.get("data", []) or []:
            dt = parse_dt(d.get("date") or d.get("startDate"))
            dk = f"{dt.year}-{dt.month}-{dt.day}" if dt else day_key_from_iso(None)
            if name in ("sleep_analysis", "sleep"):
                # Auto Export gives hours in qty, or asleep/inBed breakdown
                hrs = num(d.get("asleep") or d.get("totalSleep") or d.get("qty"))
                if hrs:
                    by_day_sleep[dk] = by_day_sleep.get(dk, 0) + hrs * 60.0
            elif name in ("step_count", "steps"):
                by_day_steps[dk] = by_day_steps.get(dk, 0) + num(d.get("qty"))
    for dk, mins in by_day_sleep.items():
        recs.append(_sleep_rec(dk, mins))
    for dk, steps in by_day_steps.items():
        recs.append(_steps_rec(dk, steps))
    # workouts
    for w in data.get("workouts", []) or []:
        recs.append(_workout_rec(w.get("name") or w.get("type") or "Workout",
                                 w.get("start") or w.get("startDate"),
                                 num(w.get("duration")) ,  # seconds or minutes -> handled below
                                 num((w.get("distance") or {}).get("qty") if isinstance(w.get("distance"), dict) else w.get("distance"))))
    return recs


def _from_shortcuts(p):
    """Our defined Shortcuts shape (all fields optional):
       { "date":"2024-06-18T07:05:00Z",   # optional; defaults to now
         "sleep_min": 430,                 # minutes asleep last night
         "steps": 5400,
         "workouts": [ {"type":"Run","min":28,"km":5.0,"start":"..."} ] }
    """
    recs = []
    dk = day_key_from_iso(p.get("date"))
    if p.get("sleep_min") not in (None, "", 0):
        recs.append(_sleep_rec(dk, num(p.get("sleep_min"))))
    elif p.get("sleep_hours") not in (None, "", 0):
        recs.append(_sleep_rec(dk, num(p.get("sleep_hours")) * 60.0))
    if p.get("steps") not in (None, "", 0):
        recs.append(_steps_rec(dk, num(p.get("steps"))))
    for w in p.get("workouts", []) or []:
        mins = num(w.get("min") or w.get("minutes") or w.get("duration"))
        recs.append(_workout_rec(w.get("type") or w.get("name") or "Workout",
                                 w.get("start") or p.get("date"), mins,
                                 num(w.get("km") or w.get("dist_km") or w.get("distance")), already_min=True))
    return recs


def _sleep_rec(dk, mins):
    mins = int(round(mins))
    return {"sid": f"ios-sleep-{dk}", "type": "sleep", "day": dk, "min": mins,
            "t": _day_ms(dk, 7), "text": f"Slept {fmt_min(mins)} · synced", "src": "ios"}


def _steps_rec(dk, steps):
    steps = int(round(steps))
    return {"sid": f"ios-steps-{dk}", "type": "steps", "day": dk, "steps": steps,
            "t": _day_ms(dk, 12), "text": f"{steps:,} steps · synced", "src": "ios"}


def _workout_rec(name, start_iso, dur, dist_km, already_min=False):
    dt = parse_dt(start_iso)
    dk = f"{dt.year}-{dt.month}-{dt.day}" if dt else day_key_from_iso(None)
    mins = dur if already_min else (dur / 60.0 if dur > 180 else dur)  # Auto Export duration is seconds
    mins = int(round(mins))
    sid = "ios-workout-" + (dt.isoformat() if dt else str(int(time.time())))
    label = name + (f", {dist_km:.1f}km" if dist_km else "") + (f", {mins}m" if mins else "")
    return {"sid": sid, "type": "move", "day": dk, "min": mins, "km": round(dist_km, 2) if dist_km else 0,
            "t": to_ms(dt), "text": label + " · synced", "src": "ios"}


def _day_ms(dk, hour):
    try:
        y, m, d = (int(x) for x in dk.split("-"))
        return int(datetime(y, m, d, hour).timestamp() * 1000)
    except (ValueError, OverflowError):
        return int(time.time() * 1000)


def load_store():
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"records": [], "updated": 0}


def save_store(store):
    cutoff_ms = (time.time() - KEEP_DAYS * 86400) * 1000
    store["records"] = [r for r in store["records"] if r.get("t", 0) >= cutoff_ms][-2000:]
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f)
    os.replace(tmp, STORE)


def upsert(store, recs):
    by_sid = {r["sid"]: r for r in store["records"] if r.get("sid")}
    for r in recs:
        by_sid[r["sid"]] = r
    store["records"] = sorted(by_sid.values(), key=lambda x: x.get("t", 0))
    store["updated"] = int(time.time())
    return len(recs)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Aether-Token")

    def _json(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code); self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _token_ok(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        tok = (q.get("token", [None])[0]) or self.headers.get("X-Aether-Token")
        return tok == TOKEN

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/health":
            s = load_store()
            self._json(200, {"ok": True, "records": len(s.get("records", [])), "updated": s.get("updated", 0)})
        elif path == "/latest":
            if not self._token_ok():
                self._json(401, {"error": "bad token"}); return
            s = load_store()
            self._json(200, {"records": s.get("records", []), "updated": s.get("updated", 0)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/ingest", ""):
            self._json(404, {"error": "not found"}); return
        if not self._token_ok():
            self._json(401, {"error": "bad token"}); return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > MAX_BODY:
                self._json(413, {"error": "too large"}); return
            payload = json.loads(self.rfile.read(n) or "{}")
        except (ValueError, OSError):
            self._json(400, {"error": "bad json"}); return
        try:
            recs = normalize(payload)
            store = load_store()
            added = upsert(store, recs)
            save_store(store)
            self._json(200, {"ok": True, "ingested": added, "total": len(store["records"])})
        except Exception as e:
            self._json(500, {"error": f"normalize failed: {e}"})

    def log_message(self, *a):
        pass


def main():
    print(f"AETHER iOS health-sync on http://127.0.0.1:{PORT}  (store={STORE})")
    print(f"  expose:  tailscale funnel --bg --set-path /aether-sync http://127.0.0.1:{PORT}")
    print(f"  iPhone POSTs to https://<host>/aether-sync/ingest?token=...  ;  app GETs /aether-sync/latest")
    if TOKEN == "aether-sync-7e3f9c":
        print("  WARNING: using the default token — set AETHER_SYNC_TOKEN to something private.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
