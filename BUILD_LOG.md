# Builder Log

Newest first. One entry per run: what shipped / what's on a branch / what's blocked.

---

## 2026-06-17 — run 1

- **Orient:** No BACKLOG.md or builder log existed; created both, grounded on a
  real audit of the repo (manifest vs. index.html brand tokens).
- **Pulled:** Manifest dark-theme parity.
- **Found:** `manifest.webmanifest` `theme_color` + `background_color` = `#EEF3FA`
  (old light brand); app ground is `#021014` and `<meta theme-color>` already
  `#021014`. Mismatch -> white splash flash + wrong status bar on PWA install.
- **Did:** branch `feat/manifest-dark-theme`; set both manifest colors to `#021014`.
- **Verified:** manifest parses as JSON; both colors == `#021014`; consistent with
  index.html `--bg` and meta theme-color.
- **Status:** SHIPPED. PR #1 merged (squash) to main as `6b27bea`; branch deleted.
  Yaro approved the merge from the PR page.

## 2026-06-17 — run 2

- **Pulled:** Icon brand audit (next item).
- **Found:** all five install icons (icon-180/192/512, maskable-192/512) had a
  stale near-white `#f8fafc` ground — old light brand. Clashed with the dark app
  + the splash fix from run 1; on the home screen the icon was a white tile.
  `mark-256.png` (the in-app transparent glyph) was already correct cyan.
- **Did:** branch `feat/icon-dark-ground`. Regenerated all five from the
  transparent `mark-256` master, tight-cropped and centered on dark navy
  `#021014`. Regular icons 76% scale; maskable 50% so the glyph tips sit ±25%
  from center — comfortably inside the circular maskable safe zone.
- **Verified:** all corners now `#021014`; all PNGs valid; vision check confirms
  centered cyan mark, no clipping, dark ground. apple-touch-icon → icon-180
  (opaque, iOS-safe).
- **Status:** SHIPPED. PR #2 squash-merged to main as `0c341c7`; branch deleted.

## 2026-06-17 — run 3

- **Pulled:** Offline shell completeness.
- **Found:** sw.js `SHELL_ASSETS` precached 6 items but index.html references
  `icons/mark-256.png` (home-screen logo, used twice) which was NOT cached — an
  offline cold launch showed a broken logo. Also missing: `icon-180` (apple-touch)
  and `maskable-512`. Google Fonts are cross-origin; the SW only handles
  same-origin by design, and the CSS has full system fallbacks (Saira ->
  -apple-system/system-ui), so fonts degrade gracefully offline — left as-is.
- **Did:** branch `feat/offline-shell-precache`. Added mark-256, icon-180,
  maskable-512 to SHELL_ASSETS (now 9 same-origin assets). Bumped VERSION
  v81 -> v82 so existing installs re-precache on activate.
- **Verified:** `node --check sw.js` passes; all 9 assets exist on disk; served
  over a local http.server every asset returns 200 (so `cache.addAll`, which
  rejects atomically on any 404, will succeed).
- **Status:** PR #3 squash-merged to main. Branch deleted.

## 2026-06-18 — run 4

- **Pulled:** Persistent mic grant (Yaro's pick — kills the iPhone mic re-ask).
- **Root cause:** Safari's `webkitSpeechRecognition` re-prompts for the mic every
  session. `getUserMedia` (already used for the orb meter) persists its grant in
  an installed PWA. So capture via getUserMedia and transcribe on the host.
- **Server (`stt_proxy.py`):** stdlib HTTP + faster-whisper (`base` model, already
  cached), lazy-loaded so startup is instant. `POST /transcribe` accepts a raw
  audio body or multipart; `GET /health`; CORS scoped to the PWA origin; 25 MB
  cap; VAD filter on. Port 8847. `start_stt.bat` launcher mirrors start_voice.bat.
- **Client:** `makeSttRecognizer()` returns a getUserMedia + MediaRecorder object
  exposing the SAME interface as webkitSpeechRecognition (`.start/.stop/.abort`,
  `on*`), with an AnalyserNode VAD that auto-endpoints on ~1.1s silence (350ms
  min, 15s max). So the entire battle-tested voice loop (zombie watchdog, resume,
  studio voice) runs UNCHANGED — only what `recog` *is* changed. `bindRecogHandlers`
  shares the loop bodies across both backends. Native SR kept as automatic
  fallback via `fallbackToSR()` on `stt-network` error. Swapped all 8 `!SR`
  control-flow guards to `!recog`/`VOICE_OK` so STT-only devices aren't blocked.
  Bumped sw v82 -> v83.
- **Verified:** server transcribed real synthesized clips in mp3, webm/opus
  (Chromium MediaRecorder) and m4a/aac (Safari MediaRecorder) — all correct;
  empty-body -> 400; CORS preflight returns the right headers; all 8 inline
  scripts pass `node --check`; no leftover bare `!SR` control guards; STT URL
  resolves to `https://yaro.tail6a3c7a.ts.net/aether-stt/transcribe`.
- **Host setup needed (one-time, Yaro):** run `start_stt.bat` and
  `tailscale serve --bg --set-path /aether-stt http://127.0.0.1:8847`. Then on the
  iPhone PWA the mic is granted once and not re-asked. Until that path is live the
  app silently uses native dictation (still works, still re-asks).
- **Status:** PR open on `feat/persistent-mic-whisper`. Awaiting review/merge.

## 2026-06-18 — runs 5-7 (batch)

- **Run 5 — Health tab (photo meal logging):** built `screenHealth` + Home fcard;
  snap/pick photo -> upload -> jarvis vision estimate JSON -> localStorage ->
  today's meals + macro totals vs. editable goal. Reuses the Radar spine.
  Shipped to main (PR #5, `96ad49c`). NOTE: live AI estimate UNVERIFIED — account
  hit a credit limit mid-test and jarvis looked "in Downloads" instead of calling
  vision_analyze on the URL. Tracked as a `[!]` blocked backlog item.
- **Run 6 — Build version + Force update:** root-caused a "phone shows X but repo
  doesn't" report to PWA cache opacity (no visible build signal). Added Settings →
  About showing the running SW build, a waiting-update flag, and a Force-update
  button (skip-waiting + clear caches + reload). SW gained get-version/skip-waiting
  message handlers. sw v84->v85. Shipped to main (PR #6, `ff9b48a`).
- **Run 7 — Pre-ship verify script:** `verify.py` codifies the checks that would
  have caught the 3 earlier silent bugs — JS syntax (sw.js + inline scripts),
  manifest JSON + theme/bg color, precache-asset existence, meta/manifest theme
  parity. Verified passing on main (15 checks) AND failing (exit 1) on three
  deliberately broken inputs. Shipped to main.
- **Open blocker:** Health meal AI estimate, pending a credit top-up + possible
  AGENTS.md vision-on-URL rule.

## 2026-06-18 — run 5

- **Pulled:** Health tab — photo meal logging (Yaro asked for it directly).
- **Decision:** route analysis through the existing **jarvis** agent's vision
  tool (no new keys/deps), reusing the Review-Radar upload->ntfy->poll->JSON
  spine. Entry via a Home fcard + `screenHealth` (not a 7th bottom-nav tab — 6 is
  already crowded). State in localStorage so history survives reloads.
- **Did:** branch `feat/health-meal-logging`. Added: Health fcard + handler;
  `screenHealth` markup (totals card, Snap button w/ `capture=environment`,
  today list); dark-HUD CSS; a self-contained JS module (resize, upload, agent
  send, poll, strict JSON parse, optimistic pending row, per-meal delete,
  editable kcal goal, low-confidence "est" tag). sw v83->v84.
- **Verified (code):** all 8 inline scripts pass `node --check`; wiring tokens
  present; upload PUT returned 200 + real URL; POST to jarvis-in 200; poll reads
  jarvis-out replies correctly.
- **BLOCKER (live AI step UNVERIFIED):** the live round-trip could NOT confirm a
  nutrition estimate because (1) the Nous account is OUT OF CREDITS — agent
  replied "Model 'anthropic/claude-opus-4.8' requires available credits"; and
  (2) before that, jarvis said it was looking for the attachment "in Downloads"
  rather than calling vision_analyze on the URL — a possible agent-compliance
  issue that couldn't be diagnosed further once credits died. The app degrades
  gracefully (shows a retry message) when no JSON comes back.
- **Status:** PR opened on `feat/health-meal-logging`, **NOT merged** — held per
  the "can't verify -> don't ship to main" rule. Needs: (a) credit top-up to
  confirm the estimate, and possibly (b) a firmer vision-on-URL nudge for jarvis.
