#!/usr/bin/env python
"""AETHER local vision proxy — host-side image understanding for the PWA.

Why this exists: the app's image features (Health meal logging, Review Radar
workpaper review) used a cloud model that needs Nous credits. This runs a local
vision model (Ollama, GPU-accelerated) so image analysis costs nothing, works
offline-of-cloud, and keeps confidential images on the machine (Radar privacy).

  Phone (PWA) --POST /analyze {image_url, prompt}--> vision_local.py
                                                          |
                                              fetch image bytes -> base64
                                                          |
                                          Ollama /api/generate (qwen2.5vl) -> {"text": "..."}

Design: stdlib-only HTTP (mirrors voice_proxy.py / stt_proxy.py) talking to a
local Ollama server (default http://127.0.0.1:11434). The model is pulled once
with `ollama pull qwen2.5vl:7b`.

Run it:
  (Ollama installed + a vision model pulled)
  python vision_local.py

Expose it to the phone, tailnet-only (NOT funnel), reusing the existing TLS host
so the HTTPS PWA can reach it without mixed-content errors:
  tailscale serve --bg --set-path /aether-vision http://127.0.0.1:8846
Then the app POSTs to  https://<your-tailnet-host>/aether-vision/analyze

SECURITY: keep it tailnet-only. Anyone who can reach it can run the local model
and fetch arbitrary image URLs from this machine's network position.
"""
import base64
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config ----
PORT = int(os.environ.get("VISION_PROXY_PORT", "8846"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")
ALLOW_ORIGIN = os.environ.get("VISION_ALLOW_ORIGIN", "https://euro94.github.io")
MAX_IMG_BYTES = int(os.environ.get("VISION_MAX_IMG_BYTES", str(20 * 1024 * 1024)))
FETCH_TIMEOUT = int(os.environ.get("VISION_FETCH_TIMEOUT", "30"))
GEN_TIMEOUT = int(os.environ.get("VISION_GEN_TIMEOUT", "180"))


def fetch_image_b64(url: str) -> str:
    """Download an image URL and return base64 (no data: prefix)."""
    req = urllib.request.Request(url, headers={"User-Agent": "AETHER-vision/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        data = r.read(MAX_IMG_BYTES + 1)
    if len(data) > MAX_IMG_BYTES:
        raise ValueError(f"image too large (> {MAX_IMG_BYTES} bytes)")
    if not data:
        raise ValueError("empty image")
    return base64.b64encode(data).decode("ascii")


def ollama_generate(prompt: str, image_b64: str) -> str:
    """Call Ollama /api/generate with one image, non-streaming."""
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=GEN_TIMEOUT) as r:
        out = json.loads(r.read())
    return (out.get("response") or "").strip()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            up = False
            try:
                with urllib.request.urlopen(f"{OLLAMA}/api/version", timeout=4) as r:
                    up = r.status == 200
            except Exception:
                up = False
            self._json(200, {"ok": True, "model": MODEL, "ollama_up": up})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") not in ("/analyze", ""):
            self._json(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or "{}")
        except Exception:
            self._json(400, {"error": "bad request"})
            return
        url = (payload.get("image_url") or "").strip()
        prompt = (payload.get("prompt") or "Describe this image in detail.").strip()
        img_b64 = payload.get("image_b64")  # optional: send bytes directly
        if not url and not img_b64:
            self._json(400, {"error": "image_url or image_b64 required"})
            return
        try:
            if not img_b64:
                img_b64 = fetch_image_b64(url)
            text = ollama_generate(prompt, img_b64)
            self._json(200, {"text": text, "model": MODEL})
        except ValueError as e:
            self._json(413, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"vision failed: {e}"})

    def log_message(self, *a):
        pass


def main():
    print(f"AETHER local-vision proxy on http://127.0.0.1:{PORT}  (model={MODEL} via {OLLAMA})")
    print(f"  expose:  tailscale serve --bg --set-path /aether-vision http://127.0.0.1:{PORT}")
    print(f"  then the app POSTs to  https://<tailnet-host>/aether-vision/analyze")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
