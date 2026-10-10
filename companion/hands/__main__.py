"""Standalone entry point: ``python -m companion.hands`` prints each emitted event as JSON."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading


def list_cameras() -> int:
    """Print index, resolution and brightness per camera so the laptop webcam can be told from
    a phone (Continuity Camera, usually 1080p) or a virtual camera (OBS)."""
    import cv2

    for i in range(5):
        cap = cv2.VideoCapture(i)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        cap.release()
        if ok:
            h, w = frame.shape[:2]
            print(f"camera {i}: {w}x{h} mean brightness {frame.mean():.0f}")
    print("pick one with --camera N (a black or logo frame = phone/virtual camera)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m companion.hands", description=__doc__)
    p.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    p.add_argument("--two-hands", action="store_true", help="Coherent anatomical left/right observations for selection clutch controls")
    p.add_argument("--manipulator-hand", choices=("Left","Right"), default="Right",
                   help="Deprecated compatibility option; clutch mode always uses anatomical roles")
    p.add_argument("--no-preview", action="store_true", help="headless: no window")
    p.add_argument("--model", help="path to hand_landmarker.task")
    p.add_argument("--smoothing", type=float, help="cursor smoothing 0..<1 (default 0.5)")
    p.add_argument("--pinch-start", type=float, help="pinch ratio to start (default 0.35)")
    p.add_argument("--pinch-release", type=float, help="pinch ratio to release (default 0.60)")
    p.add_argument("--stable-ms", type=float, help="stability window in ms (default 80)")
    p.add_argument("--list-cameras", action="store_true", help="probe camera indexes 0-4 and exit")
    p.add_argument("--no-frames", action="store_true", help="print only gesture transition events/frames")
    a = p.parse_args(argv)
    if a.list_cameras:
        return list_cameras()

    config = {"camera_index": a.camera, "preview": not a.no_preview,
              "two_hands": a.two_hands, "manipulator_hand": a.manipulator_hand}
    for key, val in (("model_path", a.model), ("smoothing", a.smoothing), ("pinch_start", a.pinch_start),
                     ("pinch_release", a.pinch_release), ("pinch_stable_ms", a.stable_ms)):
        if val is not None:
            config[key] = val

    def emit(event: dict) -> None:
        if a.no_frames and event["type"] == "hand_frame":
            return
        if (a.no_frames and event["type"] == "hands_frame" and
                all(hand['event'] == 'NONE' for hand in event['payload']['hands'].values())):
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
