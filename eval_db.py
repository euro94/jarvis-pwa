#!/usr/bin/env python
"""eval_db.py — SQLite store for AETHER eval findings.

Every eval run writes its findings here. The local builder reads from here
to find the highest-value, lowest-effort items to attempt.

Schema
------
findings:
  id          INTEGER PK autoincrement
  fingerprint TEXT UNIQUE   -- sha256(screen+title)[:16], dedupes across runs
  screen      TEXT          -- screenHome, screenHealth, etc.
  category    TEXT          -- critical | gap | epic_idea
  title       TEXT
  detail      TEXT
  effort      TEXT          -- small | medium | large
  impact      TEXT          -- high | medium | low
  status      TEXT          -- pending | attempted | shipped | rejected | skipped
  score       REAL          -- computed: impact_val / effort_val
  eval_date   TEXT          -- ISO date of first seen
  last_seen   TEXT          -- ISO date of most recent eval that reported it
  attempts    INTEGER       -- how many times coder tried it
  branch      TEXT          -- git branch if attempted
  pr_url      TEXT          -- GitHub PR URL if shipped
  notes       TEXT          -- why rejected / what was tried

runs:
  id          INTEGER PK autoincrement
  run_at      TEXT          -- ISO datetime
  screens     TEXT          -- JSON list of screens evaluated
  findings_n  INTEGER       -- total findings this run
  new_n       INTEGER       -- new findings (not seen before)
  duration_s  REAL
"""
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "eval_results.db")

IMPACT_VAL = {"high": 3, "medium": 2, "low": 1}
EFFORT_VAL  = {"small": 1, "medium": 2, "large": 3}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS findings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT    UNIQUE NOT NULL,
            screen      TEXT    NOT NULL,
            category    TEXT    NOT NULL DEFAULT 'gap',
            title       TEXT    NOT NULL,
            detail      TEXT    NOT NULL DEFAULT '',
            effort      TEXT    NOT NULL DEFAULT 'medium',
            impact      TEXT    NOT NULL DEFAULT 'medium',
            status      TEXT    NOT NULL DEFAULT 'pending',
            score       REAL    NOT NULL DEFAULT 0,
            eval_date   TEXT    NOT NULL,
            last_seen   TEXT    NOT NULL,
            attempts    INTEGER NOT NULL DEFAULT 0,
            branch      TEXT    NOT NULL DEFAULT '',
            pr_url      TEXT    NOT NULL DEFAULT '',
            notes       TEXT    NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      TEXT NOT NULL,
            screens     TEXT NOT NULL DEFAULT '[]',
            findings_n  INTEGER NOT NULL DEFAULT 0,
            new_n       INTEGER NOT NULL DEFAULT 0,
            duration_s  REAL    NOT NULL DEFAULT 0
        );
        """)


def _fingerprint(screen: str, title: str) -> str:
    raw = f"{screen}::{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _score(effort: str, impact: str) -> float:
    i = IMPACT_VAL.get(impact, 2)
    e = EFFORT_VAL.get(effort, 2)
    return round(i / e, 3)


def upsert_finding(screen, category, title, detail, effort="medium", impact="medium"):
    """Insert a new finding or update last_seen if already known. Returns (id, is_new)."""
    fp = _fingerprint(screen, title)
    today = date.today().isoformat()
    score = _score(effort, impact)
    with _conn() as c:
        row = c.execute("SELECT id, status FROM findings WHERE fingerprint=?", (fp,)).fetchone()
        if row:
            c.execute(
                "UPDATE findings SET last_seen=?, detail=?, effort=?, impact=?, score=? WHERE fingerprint=?",
                (today, detail, effort, impact, score, fp)
            )
            return row["id"], False
        else:
            cur = c.execute(
                """INSERT INTO findings
                   (fingerprint,screen,category,title,detail,effort,impact,status,score,eval_date,last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fp, screen, category, title, detail, effort, impact, "pending", score, today, today)
            )
            return cur.lastrowid, True


def log_run(screens, findings_n, new_n, duration_s):
    with _conn() as c:
        c.execute(
            "INSERT INTO runs (run_at, screens, findings_n, new_n, duration_s) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), json.dumps(screens), findings_n, new_n, duration_s)
        )


def get_buildable(limit=5):
    """Return top-scored pending findings with effort:small, sorted by score desc."""
    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM findings
            WHERE status='pending' AND effort='small'
            ORDER BY score DESC, eval_date ASC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_all(status=None, limit=100):
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM findings WHERE status=? ORDER BY score DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM findings ORDER BY score DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def mark_attempted(finding_id, branch):
    with _conn() as c:
        c.execute(
            "UPDATE findings SET status='attempted', attempts=attempts+1, branch=? WHERE id=?",
            (branch, finding_id)
        )


def mark_shipped(finding_id, pr_url):
    with _conn() as c:
        c.execute(
            "UPDATE findings SET status='shipped', pr_url=? WHERE id=?",
            (pr_url, finding_id)
        )


def mark_rejected(finding_id, reason):
    with _conn() as c:
        c.execute(
            "UPDATE findings SET status='rejected', attempts=attempts+1, notes=? WHERE id=?",
            (reason, finding_id)
        )


def mark_skipped(finding_id, reason):
    with _conn() as c:
        c.execute(
            "UPDATE findings SET status='skipped', notes=? WHERE id=?",
            (reason, finding_id)
        )


def stats():
    with _conn() as c:
        total  = c.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        by_status = dict(c.execute(
            "SELECT status, COUNT(*) FROM findings GROUP BY status"
        ).fetchall())
        runs_n = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        new_today = c.execute(
            "SELECT COUNT(*) FROM findings WHERE eval_date=?", (date.today().isoformat(),)
        ).fetchone()[0]
    return {"total": total, "by_status": by_status, "runs": runs_n, "new_today": new_today}


if __name__ == "__main__":
    init_db()
    print("DB initialised at", DB_PATH)
    s = stats()
    print(f"Findings: {s['total']} total | {s['by_status']} | {s['new_today']} new today | {s['runs']} runs")
