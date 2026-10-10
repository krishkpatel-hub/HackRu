"""Standalone entry point: ``python -m companion.hands`` prints each emitted event as JSON."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m companion.hands", description=__doc__)
    p.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    p.add_argument("--no-preview", action="store_true", help="headless: no window")
    p.add_argument("--model", help="path to hand_landmarker.task")
    p.add_argument("--smoothing", type=float, help="cursor smoothing 0..<1 (default 0.5)")
    p.add_argument("--pinch-start", type=float, help="pinch ratio to start (default 0.35)")
    p.add_argument("--pinch-release", type=float, help="pinch ratio to release (default 0.60)")
    p.add_argument("--stable-ms", type=float, help="stability window in ms (default 80)")
    p.add_argument("--no-frames", action="store_true", help="print only gesture_* events")
    a = p.parse_args(argv)

    config = {"camera_index": a.camera, "preview": not a.no_preview}
    for key, val in (("model_path", a.model), ("smoothing", a.smoothing), ("pinch_start", a.pinch_start),
                     ("pinch_release", a.pinch_release), ("pinch_stable_ms", a.stable_ms)):
        if val is not None:
            config[key] = val

    def emit(event: dict) -> None:
        if a.no_frames and event["type"] == "hand_frame":
            return
        print(json.dumps(event, separators=(",", ":")), flush=True)

    from .tracker import run_hand_tracker  # imported late so --help works without cv2/mediapipe

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        run_hand_tracker(emit, stop, config)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
