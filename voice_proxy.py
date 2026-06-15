#!/usr/bin/env python
"""AETHER "Claude-direct" voice proxy.

The fast conversational path: the PWA streams straight to this proxy over your
Tailscale tailnet (bypassing the ntfy poll loop), and this proxy calls the
Claude API directly with streaming + tool use. Plain chat is answered instantly
by Claude; only real *actions* are dispatched to Hermes / the existing agents
over the same ntfy topics the rest of AETHER already uses.

  Phone (PWA, "Live" mode) ──HTTPS/SSE──► voice_proxy.py ──► Claude API (stream)
                                                │
                                                └─ tool calls ─► ntfy ─► Hermes / Claude Code

Why a proxy at all: the Anthropic API key must never ship in the browser. This
holds it server-side. It is intentionally small and stdlib-only (plus the
`anthropic` SDK) so it can run next to builder_bridge.py today and lift to a
serverless host (Cloudflare Workers / Vercel) later with no logic change.

Run it:
  pip install anthropic
  set ANTHROPIC_API_KEY=sk-ant-...
  python voice_proxy.py

Expose it to your phone, tailnet-only (NOT funnel), reusing your existing TLS
hostname so the HTTPS PWA can reach it without mixed-content errors:
  tailscale serve --bg --set-path /aether-voice http://127.0.0.1:8848
Then in the app, set VOICE_PROXY to  https://<your-tailnet-host>/aether-voice

SECURITY: same model as the rest of AETHER — keep it tailnet-only. Anyone who
can reach this endpoint can spend your Claude credits and drive your agents.
"""
import json, os, sys, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic

# ---- config ----
PORT       = int(os.environ.get("VOICE_PROXY_PORT", "8848"))
MODEL      = os.environ.get("VOICE_MODEL", "claude-sonnet-4-6")  # fast turns; heavy work goes to Hermes
MAX_TOKENS = int(os.environ.get("VOICE_MAX_TOKENS", "1024"))
NTFY       = os.environ.get("AETHER_NTFY", "https://yaro.tail6a3c7a.ts.net")
# Allow the PWA origin to call us from the browser.
ALLOW_ORIGIN = os.environ.get("VOICE_ALLOW_ORIGIN", "https://euro94.github.io")

# Inbound ntfy topics for each AETHER agent (must match index.html's AGENTS).
AGENT_TOPICS = {
    "jarvis":   "hermes-yaro-jarvis-in-c4e3ac0f",
    "research": "hermes-yaro-research-in-f97aeefc",
    "reviewer": "hermes-yaro-seniorrev-in-bfb96220",
    "design":   "hermes-yaro-design-in-ea57c6e8",
    "builder":  "hermes-yaro-builder-in-c7b4c5ae80",   # Claude Code — edits & ships the app
}

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

SYSTEM = (
    "You are AETHER, Yaro's voice assistant, speaking aloud through his phone. "
    "Keep replies short and natural — one to three sentences, no markdown, no lists, "
    "no emoji; it's being read by a text-to-speech voice. Answer questions and chat "
    "directly and instantly yourself. Only when Yaro actually wants something DONE — "
    "logging a habit, or kicking off real work (research, a code/design review, or "
    "having Claude Code edit and ship the app) — call a tool to hand that off to the "
    "right background agent, then tell him in one line that it's on its way. Don't "
    "narrate tool use; just do it. If a request is ambiguous, ask one short question."
)

TOOLS = [
    {
        "name": "log_habit",
        "description": "Log a habit/check-in (e.g. Gym) as done, skipped, or partial.",
        "input_schema": {
            "type": "object",
            "properties": {
                "habit": {"type": "string", "description": "Habit name, e.g. Gym"},
                "status": {"type": "string", "enum": ["done", "skipped", "partial"]},
            },
            "required": ["habit", "status"],
        },
    },
    {
        "name": "send_to_hermes",
        "description": (
            "Hand a real task off to a background agent over Hermes. Use 'jarvis' for "
            "schedule/calendar/quick tasks, 'research' for deep research, 'reviewer' for "
            "code/design review, 'design' for UI/brand work, and 'builder' (Claude Code) "
            "to edit and ship this app. Call this only for actual work, not chit-chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "enum": list(AGENT_TOPICS.keys())},
                "message": {"type": "string", "description": "The full task for that agent."},
            },
            "required": ["agent", "message"],
        },
    },
]


def ntfy_post(topic, body):
    req = urllib.request.Request(f"{NTFY}/{topic}", data=body.encode("utf-8"), method="POST")
    urllib.request.urlopen(req, timeout=20).read()


def run_tool(name, inp):
    inp = inp or {}
    try:
        if name == "log_habit":
            habit, status = inp.get("habit", "?"), inp.get("status", "done")
            ntfy_post(AGENT_TOPICS["jarvis"], f"Log {habit}: {status}")
            return f"Logged {habit}: {status}."
        if name == "send_to_hermes":
            agent = inp.get("agent", "jarvis")
            topic = AGENT_TOPICS.get(agent)
            if not topic:
                return f"Unknown agent '{agent}'."
            ntfy_post(topic, inp.get("message", "") or "(no message)")
            return f"Handed off to {agent}."
    except Exception as e:
        return f"Tool error: {e}"
    return f"Unknown tool '{name}'."


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # tiny health check
        self.send_response(200 if self.path == "/health" else 404)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok" if self.path == "/health" else b"not found")

    def do_POST(self):
        if self.path.rstrip("/") not in ("/chat", ""):
            self.send_response(404); self._cors(); self.end_headers(); return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or "{}")
            messages = payload.get("messages") or []
        except Exception:
            self.send_response(400); self._cors(); self.end_headers()
            self.wfile.write(b'{"error":"bad request"}'); return

        # Open the SSE stream to the phone.
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(obj):
            try:
                self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                raise

        full = []
        try:
            # Agentic loop: stream text, run any tool calls, continue until end_turn.
            for _ in range(6):  # safety cap on tool round-trips
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                    tools=TOOLS,
                    thinking={"type": "disabled"},          # fast voice turns
                    output_config={"effort": "low"},
                    messages=messages,
                ) as stream:
                    for event in stream:
                        if event.type == "content_block_delta" and event.delta.type == "text_delta":
                            full.append(event.delta.text)
                            emit({"type": "text", "text": event.delta.text})
                    final = stream.get_final_message()

                if final.stop_reason != "tool_use":
                    break

                # Execute tool calls, feed results back, loop.
                messages.append({"role": "assistant", "content": final.content})
                results = []
                for blk in final.content:
                    if blk.type == "tool_use":
                        out = run_tool(blk.name, blk.input)
                        emit({"type": "action", "tool": blk.name, "result": out})
                        results.append({"type": "tool_result", "tool_use_id": blk.id, "content": out})
                messages.append({"role": "user", "content": results})

            emit({"type": "done", "text": "".join(full)})
        except (BrokenPipeError, ConnectionResetError):
            pass  # phone hung up
        except Exception as e:
            try:
                emit({"type": "error", "error": str(e)})
            except Exception:
                pass

    def log_message(self, *a):  # quieter console
        pass


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set — requests will fail.", file=sys.stderr)
    print(f"AETHER voice proxy on http://127.0.0.1:{PORT}  (model={MODEL})")
    print(f"  expose:  tailscale serve --bg --set-path /aether-voice http://127.0.0.1:{PORT}")
    print(f"  then in the app set VOICE_PROXY = {NTFY}/aether-voice")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
