#!/usr/bin/env python
"""AETHER pre-ship verification.

Codifies the manual checks that would have caught the bugs that shipped silently
before this existed (manifest color mismatch, a missing precache asset, stale
light-theme icons). Run it before merging anything:

    python verify.py

Exits 0 if everything passes, non-zero (and prints FAILs) otherwise. No CI
framework, no build step — just the checks, runnable by hand or from a hook.

Checks:
  1. JS syntax — sw.js and every inline <script> in index.html via `node --check`
  2. Manifest — valid JSON; theme_color and background_color == THEME (dark navy)
  3. Precache — every file listed in sw.js SHELL_ASSETS exists on disk
  4. Theme parity — <meta name="theme-color"> in index.html == manifest theme_color
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
THEME = "#021014"   # the app's dark-navy ground; manifest + meta must match

fails = []
oks = []


def ok(msg):
    oks.append(msg)


def fail(msg):
    fails.append(msg)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def node_check(label, code):
    """Syntax-check a chunk of JS with `node --check`."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        if r.returncode == 0:
            ok(f"JS syntax OK — {label}")
        else:
            fail(f"JS syntax ERROR — {label}:\n{r.stderr.strip()[:800]}")
    finally:
        os.unlink(path)


def check_js():
    if not have_node():
        fail("node not found on PATH — cannot syntax-check JS")
        return
    node_check("sw.js", read("sw.js"))
    html = read("index.html")
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    n = 0
    for i, b in enumerate(blocks):
        if not b.strip():
            continue   # external <script src=...> — nothing inline to check
        n += 1
        node_check(f"index.html inline block {i}", b)
    ok(f"index.html — {n} inline script block(s) checked")


def check_manifest():
    try:
        m = json.loads(read("manifest.webmanifest"))
    except Exception as e:
        fail(f"manifest.webmanifest is not valid JSON: {e}")
        return None
    ok("manifest.webmanifest parses as JSON")
    for key in ("theme_color", "background_color"):
        v = m.get(key)
        if (v or "").lower() == THEME.lower():
            ok(f"manifest {key} == {THEME}")
        else:
            fail(f"manifest {key} is {v!r}, expected {THEME}")
    return m


def check_precache():
    sw = read("sw.js")
    mm = re.search(r"SHELL_ASSETS\s*=\s*\[(.*?)\]", sw, re.DOTALL)
    if not mm:
        fail("could not find SHELL_ASSETS array in sw.js")
        return
    assets = re.findall(r"'([^']+)'|\"([^\"]+)\"", mm.group(1))
    assets = [a or b for a, b in assets]
    missing = []
    for a in assets:
        if a in ("./", "/"):
            continue   # navigation root, served from index.html
        rel = a[2:] if a.startswith("./") else a.lstrip("/")
        if not os.path.exists(os.path.join(ROOT, rel)):
            missing.append(a)
    if missing:
        fail("precache assets missing on disk: " + ", ".join(missing))
    else:
        ok(f"all {len(assets)} SHELL_ASSETS precache entries exist")


def check_theme_parity(manifest):
    html = read("index.html")
    mm = re.search(r'name=["\']theme-color["\']\s+content=["\']([^"\']+)["\']', html)
    if not mm:
        fail("no <meta name=\"theme-color\"> found in index.html")
        return
    meta = mm.group(1)
    mtheme = (manifest or {}).get("theme_color", "")
    if meta.lower() == mtheme.lower() and meta.lower() == THEME.lower():
        ok(f"<meta theme-color> == manifest theme_color == {THEME}")
    else:
        fail(f"<meta theme-color>={meta!r} vs manifest theme_color={mtheme!r} (expected {THEME})")


def main():
    check_js()
    manifest = check_manifest()
    check_precache()
    check_theme_parity(manifest)

    print("\n".join("  PASS  " + m.splitlines()[0] for m in oks))
    if fails:
        print("\n".join("  FAIL  " + m for m in fails))
        print(f"\nverify: {len(oks)} passed, {len(fails)} FAILED")
        sys.exit(1)
    print(f"\nverify: all {len(oks)} checks passed ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
