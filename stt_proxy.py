#!/usr/bin/env python
"""AETHER speech-to-text proxy — host-side Whisper for the PWA.

Why this exists: on iPhone, Safari's webkitSpeechRecognition re-prompts for the
microphone on *every* session, which is friction Yaro hates. An installed PWA's
getUserMedia grant, by contrast, persists. So the app captures audio with
getUserMedia + MediaRecorder and POSTs the clip here; this proxy runs
faster-whisper locally and returns the transcript. No browser speech permission,
no re-ask.

  Phone (PWA) --getUserMedia+MediaRecorder--> POST /transcribe (audio blob)
                                                    |
                                                    v
                                          faster-whisper (local) -> {"text": "..."}

Design: stdlib-only HTTP (mirrors voice_proxy.py) plus faster-whisper, which is
already installed with the 'base' model cached. The model is loaded lazily on the
first request so startup is instant and a cold host doesn't pay for it until
voice is actually used.

Run it:
  pip install faster-whisper          # already present on Yaro's host
  python stt_proxy.py

Expose it to the phone, tailnet-only (NOT funnel), reusing the existing TLS host
so the HTTPS PWA can reach it without mixed-content errors:
  tailscale serve --bg --set-path /aether-stt http://127.0.0.1:8847
Then the app POSTs audio to  https://<your-tailnet-host>/aether-stt/transcribe

SECURITY: same model as the rest of AETHER — keep it tailnet-only. Anyone who can
reach this endpoint can transcribe audio on your machine and spend CPU/GPU.
"""
import io
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config ----
PORT = int(os.environ.get("STT_PROXY_PORT", "8847"))
MODEL_SIZE = os.environ.get("STT_MODEL", "base")          # base is cached; tiny/small also fine
DEVICE = os.environ.get("STT_DEVICE", "cpu")              # "cuda" if a GPU is available
COMPUTE = os.environ.get("STT_COMPUTE", "int8")           # int8 = fast on CPU, low memory
LANG = os.environ.get("STT_LANG", "en")                   # force English; set "" to auto-detect
ALLOW_ORIGIN = os.environ.get("STT_ALLOW_ORIGIN", "https://euro94.github.io")
MAX_BYTES = int(os.environ.get("STT_MAX_BYTES", str(25 * 1024 * 1024)))  # 25 MB cap

_model = None


def get_model():
    """Lazy-load faster-whisper so process start is instant."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # imported lazily
        print(f"[stt] loading faster-whisper '{MODEL_SIZE}' ({DEVICE}/{COMPUTE})...", flush=True)
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
        print("[stt] model ready.", flush=True)
    return _model


def transcribe_bytes(raw: bytes) -> str:
    """Write the uploaded audio to a temp file and run faster-whisper on it.

    faster-whisper decodes via ffmpeg/av, so it accepts webm/ogg/mp4/wav as long
    as the codec is supported — which covers what MediaRecorder produces on
    Safari (mp4/aac) and Chromium (webm/opus)."""
    model = get_model()
    suffix = ".audio"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(raw)
        path = tf.name
    try:
        kwargs = {"beam_size": 1, "vad_filter": True}
        if LANG:
            kwargs["language"] = LANG
        segments, _info = model.transcribe(path, **kwargs)
        return "".join(seg.text for seg in segments).strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _read_upload(handler) -> bytes:
    """Read the request body. Accepts a raw audio body (the app's default) OR a
    multipart/form-data 'file' field, so the endpoint is easy to test with curl."""
    n = int(handler.headers.get("Content-Length", "0"))
    if n <= 0:
        return b""
    if n > MAX_BYTES:
        raise ValueError(f"upload too large ({n} bytes > {MAX_BYTES})")
    body = handler.rfile.read(n)
    ctype = (handler.headers.get("Content-Type") or "").lower()
    if "multipart/form-data" in ctype and "boundary=" in ctype:
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"')
        marker = ("--" + boundary).encode()
        parts = body.split(marker)
        for part in parts:
            if b"\r\n\r\n" not in part:
                continue
            head, data = part.split(b"\r\n\r\n", 1)
            if b"filename=" in head or b'name="file"' in head:
                return data.rstrip(b"\r\n")
        return b""
    return body  # raw audio body


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._json(200, {"ok": True, "model": MODEL_SIZE, "loaded": _model is not None})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") not in ("/transcribe", ""):
            self._json(404, {"error": "not found"})
            return
        try:
            raw = _read_upload(self)
        except ValueError as e:
            self._json(413, {"error": str(e)})
            return
        except Exception as e:
            self._json(400, {"error": f"bad upload: {e}"})
            return
        if not raw:
            self._json(400, {"error": "empty audio"})
            return
        try:
            text = transcribe_bytes(raw)
            self._json(200, {"text": text})
        except Exception as e:
            self._json(500, {"error": f"transcription failed: {e}"})

    def log_message(self, *a):  # quieter console
        pass


def main():
    print(f"AETHER STT proxy on http://127.0.0.1:{PORT}  (model={MODEL_SIZE} {DEVICE}/{COMPUTE})")
    print(f"  expose:  tailscale serve --bg --set-path /aether-stt http://127.0.0.1:{PORT}")
    print(f"  then the app POSTs audio to  https://<tailnet-host>/aether-stt/transcribe")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
