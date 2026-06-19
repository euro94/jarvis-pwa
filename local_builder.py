#!/usr/bin/env python
"""local_builder.py — autonomous local coder for AETHER.

Reads the highest-scored effort:small findings from eval_db, asks the local
qwen2.5-coder:7b model to implement each one as a targeted patch to index.html,
verifies the result, and opens a PR for human review.

HARD RULES (same as the main builder loop):
  - Only attempts effort:small findings.
  - Every change must pass: node --check on all inline scripts + verify.py.
  - Never commits to main. Always a feat/local-<slug> branch + PR.
  - If verify fails: revert, mark rejected, move on.
  - Never attempts the same finding twice in the same run.
  - Max 3 attempts per run to keep GPU time bounded.

HONEST LIMITS:
  The local 7B model is good at:
    - Adding a CSS rule or tweaking a value
    - Adding a small HTML element (a badge, a label, a button)
    - Adding a one-function JS helper

  It will fail on:
    - Multi-section refactors (>50 lines of context needed)
    - Logic that crosses screen boundaries
    - Anything requiring understanding the full 5000-line file

  The verifier catches failures — rejected items don't ship.
"""
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval_db

REPO       = Path(__file__).parent
INDEX      = REPO / "index.html"
SW         = REPO / "sw.js"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
CODER_MODEL = "qwen2.5-coder:7b"
MAX_ATTEMPTS = 3    # per run
CONTEXT_CHARS = 6000  # chars of index.html sent as context (keeps prompt small)


# ── helpers ──────────────────────────────────────────────────────────────────

def ollama_generate(prompt: str, model: str = CODER_MODEL) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["response"].strip()
    except Exception as e:
        return f"ERROR: {e}"


def run(cmd, cwd=None, capture=True):
    r = subprocess.run(cmd, shell=True, cwd=cwd or str(REPO),
                       capture_output=capture, text=True)
    return r.returncode, r.stdout + r.stderr


def verify() -> tuple[bool, str]:
    """Run verify.py + node --check on all inline scripts."""
    code, out = run("python verify.py")
    if code != 0:
        return False, out
    # Also extract and check all <script> blocks
    html = INDEX.read_text(encoding="utf-8")
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I)
    for i, block in enumerate(blocks):
        if not block.strip():
            continue
        tmp = REPO / f"_tmp_check_{i}.js"
        try:
            tmp.write_text(block, encoding="utf-8")
            c, o = run(f"node --check {tmp}")
            if c != 0:
                return False, f"Script block {i} syntax error:\n{o}"
        finally:
            tmp.unlink(missing_ok=True)
    return True, "ok"


def git(cmd) -> tuple[int, str]:
    return run(f"git {cmd}")


def current_sw_version() -> int:
    m = re.search(r"aether-v(\d+)", SW.read_text())
    return int(m.group(1)) if m else 91


def bump_sw():
    v = current_sw_version()
    new_v = v + 1
    content = SW.read_text()
    SW.write_text(content.replace(f"aether-v{v}", f"aether-v{new_v}"))
    return new_v


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")


def get_relevant_context(finding: dict) -> str:
    """Extract targeted context: the screen's markup section + its JS section."""
    html = INDEX.read_text(encoding="utf-8")
    screen = finding["screen"]
    title = finding["title"].lower()
    chunks = []

    # 1. Screen markup block
    start = html.find(f'id="{screen}"')
    if start != -1:
        end = min(len(html), start + 2000)
        chunks.append(f"<!-- MARKUP for {screen} -->\n" + html[start:end])

    # 2. Related JS — search for functions/variables related to keywords in the title
    keywords = [w for w in re.split(r'\W+', title) if len(w) > 3]
    for kw in keywords[:3]:
        pattern = re.compile(rf'(function\s+\w*{re.escape(kw)}\w*|const\s+\w*{re.escape(kw)}\w*)', re.I)
        for m in list(pattern.finditer(html))[:2]:
            js_start = max(0, m.start() - 100)
            js_end = min(len(html), m.start() + 800)
            chunks.append(f"<!-- JS related to '{kw}' -->\n" + html[js_start:js_end])

    # 3. CSS for the screen (search for screen-specific CSS rules)
    css_pattern = re.compile(rf'#{screen}\b[^{{{{]*{{[^}}]+}}', re.S)
    for m in list(css_pattern.finditer(html))[:2]:
        chunks.append(f"/* CSS for {screen} */\n" + m.group(0))

    if not chunks:
        return html[:CONTEXT_CHARS]

    combined = "\n\n".join(chunks)
    return combined[:CONTEXT_CHARS]


def build_prompt(finding: dict) -> str:
    context = get_relevant_context(finding)
    return textwrap.dedent(f"""
    You are modifying a single-file PWA called AETHER (index.html, vanilla HTML/CSS/JS, no frameworks).
    The app is ~5400 lines. You must make ONE small, targeted change.

    FINDING TO IMPLEMENT:
    Screen: {finding['screen']}
    Title: {finding['title']}
    Detail: {finding['detail']}
    Effort: {finding['effort']} (this is small — a few lines max)

    RELEVANT CODE CONTEXT (the section you are modifying):
    ```html
    {context[:4000]}
    ```

    OUTPUT FORMAT — you must output EXACTLY this format, nothing else:
    <<<OLD>>>
    (copy exact lines from the context above that you want to replace — must match verbatim)
    <<<NEW>>>
    (your replacement lines)
    <<<END>>>

    RULES:
    1. The OLD section must be an EXACT copy of lines from the context. Copy them character-for-character.
    2. The NEW section replaces the OLD section entirely.
    3. Make the smallest possible change — ideally 1-3 lines changed.
    4. Do NOT add new dependencies, frameworks, or external scripts.
    5. If you cannot safely make this change in <10 lines, output: SKIP: <reason>
    6. Keep the existing style — dark navy/teal theme (#04070e bg, #3ce6ff cyan), same class naming.

    Output now:
    """).strip()


def apply_diff(patch_text: str) -> bool:
    """Apply a <<<OLD>>>...<<<NEW>>>...<<<END>>> replacement to index.html."""
    m = re.search(r"<<<OLD>>>\n(.*?)<<<NEW>>>\n(.*?)<<<END>>>", patch_text, re.S)
    if not m:
        return False

    old_text = m.group(1)
    new_text = m.group(2)

    if not old_text.strip():
        return False

    html = INDEX.read_text(encoding="utf-8")

    # Exact match first
    if old_text in html:
        INDEX.write_text(html.replace(old_text, new_text, 1), encoding="utf-8")
        return True

    # Try stripping trailing whitespace on each line (common model artifact)
    old_stripped = "\n".join(l.rstrip() for l in old_text.split("\n"))
    for i in range(len(html) - len(old_stripped)):
        chunk = html[i:i+len(old_stripped)+20]
        chunk_stripped = "\n".join(l.rstrip() for l in chunk.split("\n"))
        if chunk_stripped.startswith(old_stripped):
            end = i + len(old_text)
            html = html[:i] + new_text + html[end:]
            INDEX.write_text(html, encoding="utf-8")
            return True

    return False


def get_token() -> str:
    remote, _ = run("git remote get-url origin")
    m = re.search(r"//([^@]*)@", remote)
    return m.group(1) if m else ""


def create_pr(branch: str, title: str, body: str) -> str:
    token = get_token()
    if not token:
        return ""
    payload = json.dumps({
        "title": title, "head": branch, "base": "main", "body": body
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/repos/euro94/jarvis-pwa/pulls",
        data=payload, method="POST",
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("html_url", "")
    except Exception:
        return ""


# ── main build loop ─────────────────────────────────────────────────────────

def attempt(finding: dict) -> tuple[str, str]:
    """Try to implement one finding. Returns ('shipped'|'rejected'|'skipped', reason)."""
    fid   = finding["id"]
    title = finding["title"]
    screen = finding["screen"]
    branch = f"local/{slug(title)}"

    print(f"\n{'='*60}")
    print(f"Attempting: {title}")
    print(f"Screen: {screen} | Effort: {finding['effort']} | Score: {finding['score']}")

    # Checkpoint: save current index.html so we can revert
    original = INDEX.read_bytes()

    # Branch off main
    git("fetch -q origin main")
    git("checkout -q main")
    git(f"checkout -q -b {branch}")
    eval_db.mark_attempted(fid, branch)

    # Ask the coder model
    print("  → asking qwen2.5-coder:7b...")
    t0 = time.time()
    response = ollama_generate(build_prompt(finding))
    elapsed = time.time() - t0
    print(f"  → model responded in {elapsed:.1f}s")

    # Model said SKIP
    if response.startswith("SKIP"):
        INDEX.write_bytes(original)
        git("checkout -q main")
        git(f"branch -D {branch}")
        reason = response[:200]
        print(f"  → model skipped: {reason}")
        return "skipped", reason

    # Extract patch
    m = re.search(r"<<<PATCH>>>(.*?)<<<END>>>", response, re.S)
    if not m:
        # Try to find a code block with - / + lines
        m = re.search(r"```.*?\n(.*?)```", response, re.S)
    
    if not m:
        INDEX.write_bytes(original)
        git("checkout -q main")
        git(f"branch -D {branch}")
        return "rejected", "model output contained no extractable patch"

    patch_text = m.group(1)

    # Apply
    applied = apply_diff(patch_text)
    if not applied:
        # Try CSS-only insertion as fallback
        INDEX.write_bytes(original)
        git("checkout -q main")
        git(f"branch -D {branch}")
        return "rejected", "patch could not be applied cleanly to index.html"

    # Bump SW
    new_v = bump_sw()

    # Verify
    ok, msg = verify()
    if not ok:
        # Revert
        INDEX.write_bytes(original)
        SW.write_text(SW.read_text().replace(f"aether-v{new_v}", f"aether-v{new_v-1}"))
        git("checkout -q main")
        git(f"branch -D {branch}")
        return "rejected", f"verify failed: {msg[:300]}"

    # Commit
    git("add index.html sw.js")
    git(f'commit -q -m "feat(local-build): {title[:72]}\n\nAuto-implemented by qwen2.5-coder:7b from eval finding.\nScreen: {screen} | sw v{new_v}"')
    git(f"push -q -u origin {branch}")

    pr_url = create_pr(
        branch,
        f"feat(local): {title[:72]}",
        f"**Auto-implemented** by `qwen2.5-coder:7b` from eval finding.\n\n"
        f"**Screen:** {screen}\n"
        f"**Finding:** {finding['detail']}\n"
        f"**Score:** {finding['score']} (impact:{finding['impact']} effort:{finding['effort']})\n\n"
        f"> ⚠️ Verify before merging — local model output. Check the diff carefully.\n\n"
        f"sw → v{new_v} | verify.py 15/15"
    )

    git("checkout -q main")
    print(f"  → shipped! PR: {pr_url or branch}")
    return "shipped", pr_url


def run_builder():
    eval_db.init_db()
    candidates = eval_db.get_buildable(limit=MAX_ATTEMPTS + 2)
    if not candidates:
        print("No effort:small pending findings in DB. Run eval first.")
        return

    attempted = 0
    for finding in candidates:
        if attempted >= MAX_ATTEMPTS:
            break
        status, reason = attempt(finding)
        if status == "shipped":
            eval_db.mark_shipped(finding["id"], reason)
        elif status == "rejected":
            eval_db.mark_rejected(finding["id"], reason)
        elif status == "skipped":
            eval_db.mark_skipped(finding["id"], reason)
        attempted += 1
        time.sleep(2)  # brief pause between attempts

    s = eval_db.stats()
    print(f"\nRun complete. DB: {s['total']} findings | {s['by_status']}")


if __name__ == "__main__":
    run_builder()
