# AETHER — Build Backlog

Yaro decides WHAT. Builder decides HOW and ships one item per run.
Top unblocked item gets pulled first. Keep entries concrete: a change + an
acceptance check. Vague items get marked `NEEDS-SPEC` and escalated, not guessed.

Status keys: `[ ]` todo · `[~]` on a branch awaiting review · `[x]` shipped to main · `[!]` blocked

---

## Now (top of stack)

- [~] **Health experience overhaul + Sleep tab** — replaced the basic meal-logger
  with the full Aether wellbeing screen (Yaro's aether-health.html mockup): small
  water orb + cross-domain **synthesis line** ("Aether noticed — …"), macro rings
  with the lowest one accented, ambient strip (hydration/movement/sleep), voice +
  photo + chip logging dock, timeline, hydration sparkline, orb "drinks" each log.
  **Sleep is its own screen** (`screenSleep`): last-night big number, 7-night bar
  chart, sleep→performance reflection. One `HX_ENTRIES[]` localStorage model
  across food/water/move/sleep/mood. Photo→macros still routes to LOCAL vision
  first (vision_local.py) then jarvis fallback. Namespaced `hx-`, scoped teal
  world, battery-safe orbs (stop when screen inactive). Home cards for Health +
  Sleep. sw v86->v87. _Verified: verify.py 15/15; headless Chrome run — openHealth/
  openSleep execute clean, 6 entries render, rings compute (56g protein), synthesis
  fires cross-domain, 7 week bars, water log updates ambient. No JS errors._

- [x] **Local vision backend (Ollama) — UNBLOCKS Health, no cloud/credits** —
  SHIPPED. Installed Ollama on the host + pulled `qwen2.5vl:7b` (runs on the RTX
  5070). Added `vision_local.py` (stdlib proxy port 8846, `POST /analyze`
  {image_url|image_b64, prompt} -> Ollama `/api/generate` -> {text}, CORS, health
  check) + `start_vision.bat`. Wired Health to try local vision FIRST (free,
  fast, private), falling back to the jarvis/ntfy path; Settings toggle
  (`aetherLocalVision`, default on). sw v85->v86. _Verified END-TO-END: real meal
  photo -> tailnet upload -> local model returned correct nutrition JSON
  ({chicken/rice/broccoli, 450 kcal, 35P/25C/15F, high}); hlParse handles the
  model's ```json fences; verify.py 15/15._ Expose:
  `tailscale serve --bg --set-path /aether-vision http://127.0.0.1:8846`.

- [!] **Health meal AI estimate — credit blocker RESOLVED via local vision** —
  superseded by the local backend above; cloud credits no longer required.

- [x] **Pre-ship verify script** — SHIPPED to main. `verify.py` checks JS syntax
  (sw.js + all inline scripts via node --check), manifest JSON + theme/bg ==
  `#021014`, every SHELL_ASSETS precache file exists, and `<meta theme-color>` ==
  manifest. _Verified: passes clean on main (15 checks, exit 0); catches all 3
  failure modes (color mismatch, missing asset, JS syntax) with exit 1._

- [!] **Health meal AI estimate — BLOCKED on credits** — feature shipped (PR #5)
  but the live nutrition estimate is unverified: Nous account hit a credit limit
  mid-test ("Model 'anthropic/claude-opus-4.8' requires available credits"), and
  jarvis looked for the attachment "in Downloads" instead of calling
  vision_analyze on the URL. _Unblock: Yaro tops up credits, then re-test a real
  meal photo; if jarvis still mis-routes, add a vision-on-URL rule to AGENTS.md._

- [x] **Health tab — photo meal logging** — SHIPPED to main (PR #5, squash
  `96ad49c`). `screenHealth` from a Home fcard; snap/pick photo -> upload ->
  jarvis estimates `{name,calories,protein,carbs,fat,confidence}` -> localStorage
  -> today's meals + macro totals vs. editable kcal goal. Reuses Radar spine.

- [x] **Build version + Force update** — SHIPPED to main (PR #6, `ff9b48a`).
  Settings → About shows the running SW build (`aether-vNN`), flags a waiting
  update, and a Force-update button clears caches + reloads. sw v84->v85. Durable
  fix for "phone vs repo" cache confusion.

- [x] **Persistent mic grant (getUserMedia + host Whisper)** — SHIPPED on branch
  `feat/persistent-mic-whisper` (PR open). Added `stt_proxy.py` (stdlib HTTP +
  faster-whisper `base`, lazy-loaded; `/transcribe` + `/health`; CORS for the PWA
  origin) and `start_stt.bat`. Client: `makeSttRecognizer()` — a getUserMedia +
  MediaRecorder shim with the SAME interface as webkitSpeechRecognition (VAD
  auto-endpoint on silence), so the whole voice loop runs unchanged; native SR
  kept as automatic fallback (`fallbackToSR`) if the endpoint is down. All `!SR`
  control-flow guards swapped to `!recog`/`VOICE_OK`. Expose tailnet-only:
  `tailscale serve --bg --set-path /aether-stt http://127.0.0.1:8847`.
  _Verified: server transcribes real mp3/webm-opus/m4a-aac clips correctly; CORS
  preflight OK; all 8 inline scripts pass node --check. Live payoff = Yaro's
  iPhone: grant mic once, no re-ask next session._

## Next (unblocked, not yet pulled)

- [x] **Icon brand audit** — install icons had a stale light-theme ground
  (`#f8fafc` white tile) clashing with the dark app. Recomposited the cyan AETHER
  mark onto dark navy `#021014`: icon-180/192/512 at 76% scale; maskable-192/512
  at 50% (tips ±25% from center, inside the circular safe zone). Shipped on
  branch `feat/icon-dark-ground`. _Accept: 192/512/maskable render the cyan mark
  on #021014; no white box; maskable safe-zone clear._
- [x] **Offline shell completeness** — sw.js precache was missing `mark-256.png`
  (home-screen logo), `icon-180`, `maskable-512`. Added all three + bumped to
  v82. Cross-origin Google Fonts intentionally not cached (system fallback stack
  covers offline). Shipped on `feat/offline-shell-precache`. _Accept: all 9
  same-origin shell assets precached & serve 200; SW syntax valid._

## Icebox (needs spec / a decision from Yaro)

- [ ] NEEDS-SPEC: in-app `BUILDER_TOKEN` field (BUILDER.md notes it's typed as a
  prefix today; an in-app field was floated). Decide UX before building.

---

_Builder loop: ORIENT → PLAN → BRANCH → ACT → VERIFY → SHIP. One feature per run,
finish or revert, never ship red, never auto-merge. Log lives in BUILD_LOG.md._
