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
- **Status:** on branch `feat/manifest-dark-theme`, pushed, awaiting review. Not merged.
