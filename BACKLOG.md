# AETHER — Build Backlog

Yaro decides WHAT. Builder decides HOW and ships one item per run.
Top unblocked item gets pulled first. Keep entries concrete: a change + an
acceptance check. Vague items get marked `NEEDS-SPEC` and escalated, not guessed.

Status keys: `[ ]` todo · `[~]` on a branch awaiting review · `[x]` shipped to main · `[!]` blocked

---

## Now (top of stack)

- [x] **Manifest dark-theme parity** — set `theme_color`/`background_color` to
  `#021014` to match `<meta theme-color>` and `--bg`. Shipped via PR #1 (squash
  `6b27bea`).

## Next (unblocked, not yet pulled)

- [~] **Icon brand audit** — install icons had a stale light-theme ground
  (`#f8fafc` white tile) clashing with the dark app. Recomposited the cyan AETHER
  mark onto dark navy `#021014`: icon-180/192/512 at 76% scale; maskable-192/512
  at 50% (tips ±25% from center, inside the circular safe zone). Shipped on
  branch `feat/icon-dark-ground`. _Accept: 192/512/maskable render the cyan mark
  on #021014; no white box; maskable safe-zone clear._
- [ ] **Offline shell completeness** — verify `sw.js` precaches everything
  index.html references (fonts, logo svg, icons) so a cold offline launch isn't
  broken. _Accept: airplane-mode reload renders the home screen fully._

## Icebox (needs spec / a decision from Yaro)

- [ ] NEEDS-SPEC: in-app `BUILDER_TOKEN` field (BUILDER.md notes it's typed as a
  prefix today; an in-app field was floated). Decide UX before building.

---

_Builder loop: ORIENT → PLAN → BRANCH → ACT → VERIFY → SHIP. One feature per run,
finish or revert, never ship red, never auto-merge. Log lives in BUILD_LOG.md._
