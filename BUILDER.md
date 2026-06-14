# Claude Code Builder — drive the app from your phone

Talk to **Claude Code** from the AETHER PWA and have it edit and ship this app
for you — no PC needed in the moment. Pick the **Claude Code** agent in the
**Stream** (or Talk) tab, type what you want, and a bridge running on your PC
runs Claude Code in this repo, streams progress to the feed, commits, and pushes.
GitHub Pages redeploys → reload the app → your change is live. The app rebuilds
itself.

## How it fits together

```
Phone (AETHER PWA, "Claude Code" agent)        Your PC (builder_bridge.py)
   POST message ──► ntfy builder-in ──────────►  picks it up
                                                   └─ runs:  claude -p "<message>"  (in this repo)
                                                        ├─ edits files, runs git, etc.
   feed ◄── ntfy builder-out ◄──────────────────  streams progress + final reply
                                                        └─ git push  ──► GitHub Pages redeploys
```

The app side is just another agent entry in `index.html` (`id:"builder"`), so it
shows up in the Stream tab's agent switcher automatically. The host side is
`builder_bridge.py`.

## Run the bridge (on the PC where this repo lives)

1. Make sure Claude Code is installed and signed in (the bridge calls `claude`).
2. Double-click **`start_builder.bat`**, or run:
   ```
   python builder_bridge.py
   ```
3. Leave the window open. On your phone: open AETHER → **Stream** tab → tap the
   agent name to switch to **Claude Code** → type a request → send.
4. Send `/new` to reset the conversation (starts a fresh Claude Code session).

To keep it always-on, run it under Task Scheduler (at logon) or `nssm` as a
service. It auto-reconnects if the network blips.

## Security — please read

This bridge runs phone messages as Claude Code **on your machine**. Treat it
accordingly:

- **Keep it tailnet-only.** The trigger is an unguessable ntfy topic on your
  Tailscale tailnet. Never expose the builder topics via Tailscale **Funnel** —
  anyone who could reach the inbound topic could drive Claude Code on your PC.
- **Scoped by default.** `PERMISSION_ARGS` in `builder_bridge.py` lets the agent
  edit files and run `git` / `python` / `node` / `npm` (enough to build & ship),
  but **blocks `rm`/destructive shell** and denies anything outside the allowlist.
- **Want a stronger gate?** Set a shared secret:
  ```
  set BUILDER_TOKEN=some-long-random-string
  python builder_bridge.py
  ```
  Then every phone message must start with that token (currently you'd type it as
  a prefix; an in-app field can be added later).
- **Budget cap.** `BUILDER_MAX_USD` (default `$3`) caps spend per request.
- **Blanket full power** (run *any* command) is a one-line change in
  `PERMISSION_ARGS` (`["--dangerously-skip-permissions"]`) — an RCE surface; only
  on fully trusted infra.

## Files

| File | Role |
|------|------|
| `builder_bridge.py` | Host daemon: ntfy ⇄ headless Claude Code |
| `start_builder.bat` | One-click launcher (Windows) |
| `index.html` | App: the `id:"builder"` "Claude Code" agent |
| `.builder_session` | Local session id for multi-turn continuity (gitignored) |
