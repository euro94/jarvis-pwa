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
- **Status:** on branch `feat/icon-dark-ground`, pushed. PR opened. Not merged.
