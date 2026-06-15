# ⚡ Live mode — talk to Claude directly (fast path)

A Claude-first voice/chat path. Instead of every message going phone → ntfy →
PC poll → Hermes → ntfy → phone (≈4–5s of polling lag), the PWA streams
**straight to Claude** through a tiny proxy on your PC. Claude answers chat
instantly; only real **actions** are handed off to Hermes / the existing agents.

```
Phone (PWA "Live" toggle) ──HTTPS/SSE──► voice_proxy.py ──► Claude API (streaming)
                                              │
                                              └─ tool calls ─► ntfy ─► Hermes / Claude Code
```

The Anthropic API key stays on the PC (never in the browser). The proxy is
stdlib-only apart from the `anthropic` SDK, so it runs next to
`builder_bridge.py` today and can move to a serverless host later unchanged.

## Setup (≈3 minutes)

1. **Install + key** (on the PC where the repo lives):
   ```
   pip install anthropic
   set ANTHROPIC_API_KEY=sk-ant-...      # macОS/Linux: export ANTHROPIC_API_KEY=...
   python voice_proxy.py
   ```
   It listens on `127.0.0.1:8848`.

2. **Expose it to your phone — tailnet only** (reuses your existing TLS hostname
   so the HTTPS PWA can reach it without a mixed-content error). **Do NOT use
   `funnel`** — that would put it on the public internet.
   ```
   tailscale serve --bg --set-path /aether-voice http://127.0.0.1:8848
   ```
   This serves it at `https://<your-tailnet-host>/aether-voice`, which is what
   `VOICE_PROXY` in `index.html` already points at.

3. **Turn it on in the app:** Settings → Voice → **⚡ Live mode**. Now the Talk
   tab (typed and voice) streams from Claude directly. If the proxy is ever
   unreachable, it silently falls back to the normal Hermes agent path.

## What goes where

| You say… | What happens |
|---|---|
| "What's a good way to phrase this email?" | Claude answers instantly, no Hermes. |
| "Log my gym as done" | Claude calls `log_habit` → posts to the Jarvis topic. |
| "Have Claude Code make the header bigger and ship it" | Claude calls `send_to_hermes(agent:"builder", …)` → Claude Code edits & ships. |
| "Do deep research on X" | `send_to_hermes(agent:"research", …)`. |

## Tuning

| Env var | Default | Notes |
|---|---|---|
| `VOICE_MODEL` | `claude-sonnet-4-6` | Fast conversational turns. Use `claude-haiku-4-5` for even snappier, or `claude-opus-4-8` for max smarts. |
| `VOICE_PROXY_PORT` | `8848` | Local port. |
| `VOICE_MAX_TOKENS` | `1024` | Per reply (spoken replies are short). |
| `VOICE_ALLOW_ORIGIN` | `https://euro94.github.io` | Browser origin allowed to call the proxy. |

## Security

Same model as the rest of AETHER: **keep it tailnet-only.** Anyone who can
reach `/aether-voice` can spend your Claude credits and trigger your agents
(including Claude Code editing the app). Never expose it via Tailscale Funnel.

## Moving to always-on (later)

Because the proxy holds the key and talks plain HTTPS, you can lift
`voice_proxy.py`'s logic to a Cloudflare Worker / Vercel function so the
conversational layer survives the PC sleeping — only the action hand-off needs
the PC. The app side doesn't change: just point `VOICE_PROXY` at the new URL.

## Files

| File | Role |
|------|------|
| `voice_proxy.py` | The Claude-direct proxy (streaming + tool use → ntfy). |
| `index.html` | `VOICE_PROXY` config, `liveAsk()` SSE client, the ⚡ Live toggle. |
