"""Hand Landmarker model asset: locate it or download it (``python -m companion.hands.model``)."""

from __future__ import annotations

import hashlib
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .config import DEFAULT_MODEL_PATH

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/"
    "hand_landmarker.task"
)
# SHA-256 of the file we tested with (downloaded 2026-10-10). "latest" can change upstream;
# a mismatch is reported as a warning, not an error.
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(dest: Path = DEFAULT_MODEL_PATH) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    try:
        ctx = None
        try:  # python.org builds on macOS ship without a CA bundle; certifi (if present) fixes that
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        with urllib.request.urlopen(MODEL_URL, timeout=60, context=ctx) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except (ssl.SSLError, urllib.error.URLError):
        print("urllib download failed (certificates?); falling back to curl", file=sys.stderr)
        subprocess.run(["curl", "-fL", "-o", str(tmp), MODEL_URL], check=True)
    tmp.replace(dest)
    if sha256(dest) != MODEL_SHA256:
        print("warning: model checksum differs from the tested file", file=sys.stderr)
    return dest


if __name__ == "__main__":
    print(download())
