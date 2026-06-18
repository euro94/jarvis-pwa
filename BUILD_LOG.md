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
