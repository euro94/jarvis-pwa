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
# Default to GPU (this host has an RTX 5070). float16 on CUDA is ~4x faster than
# int8 on CPU and frees the CPU for the rest of the stack. If CUDA init fails
# (driver/cuDNN missing) get_model() automatically falls back to cpu/int8 so
# voice never breaks. Override with STT_DEVICE / STT_COMPUTE env vars.
DEVICE = os.environ.get("STT_DEVICE", "cuda")
COMPUTE = os.environ.get("STT_COMPUTE", "float16")
LANG = os.environ.get("STT_LANG", "en")                   # force English; set "" to auto-detect
ALLOW_ORIGIN = os.environ.get("STT_ALLOW_ORIGIN", "https://euro94.github.io")
MAX_BYTES = int(os.environ.get("STT_MAX_BYTES", str(25 * 1024 * 1024)))  # 25 MB cap

_model = None


def get_model():
    """Lazy-load faster-whisper. Try GPU first; on any CUDA/cuDNN failure fall
    back to cpu/int8 so voice keeps working on a host without a usable GPU."""
    global _model, DEVICE, COMPUTE
    if _model is None:
        from faster_whisper import WhisperModel  # imported lazily
        try:
            print(f"[stt] loading faster-whisper '{MODEL_SIZE}' ({DEVICE}/{COMPUTE})...", flush=True)
            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
        except Exception as e:
            if DEVICE != "cpu":
                print(f"[stt] GPU init failed ({e}); falling back to cpu/int8", flush=True)
                DEVICE, COMPUTE = "cpu", "int8"
                _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
            else:
                raise
        print(f"[stt] model ready ({DEVICE}/{COMPUTE}).", flush=True)
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
    # Warm the model now so the FIRST utterance isn't a cold ~1-2s load on top of
    # transcription. Non-fatal if it fails — get_model() will retry on request.
    try:
        get_model()
    except Exception as e:
        print(f"[stt] warm-up skipped: {e}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
