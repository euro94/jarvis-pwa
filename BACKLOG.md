# AETHER — Build Backlog

Yaro decides WHAT. Builder decides HOW and ships one item per run.
Top unblocked item gets pulled first. Keep entries concrete: a change + an
acceptance check. Vague items get marked `NEEDS-SPEC` and escalated, not guessed.

Status keys: `[ ]` todo · `[~]` on a branch awaiting review · `[x]` shipped to main · `[!]` blocked

---

## Now (top of stack)

- [~] **Persistent mic grant (getUserMedia + host Whisper)** — SHIPPED on branch
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
