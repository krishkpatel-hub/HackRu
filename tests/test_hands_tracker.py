"""Tracker-loop tests with a fake camera + landmarker (needs cv2/mediapipe installed, not a webcam)."""
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("mediapipe")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent / "test_hands_fixtures"))

from companion.hands import tracker  # noqa: E402
import make_fixtures as mf  # noqa: E402


class FakeCap:
    def __init__(self, fail_after=None):
        self.released = False
        self.n = 0
        self.fail_after = fail_after

    def read(self):
        self.n += 1
        time.sleep(0.01)  # ~real-time pacing so the stability windows elapse
        if self.fail_after is not None and self.n > self.fail_after:
            return False, None
        return True, np.zeros((480, 640, 3), np.uint8)

    def release(self):
        self.released = True


class FakeLandmarker:
    closed = False

    def close(self):
        self.closed = True


def patch(monkeypatch, cap, script):
    lm = FakeLandmarker()
    monkeypatch.setattr(tracker, "_open_camera", lambda cfg: cap)
    monkeypatch.setattr(tracker, "_make_landmarker", lambda cfg: lm)
    it = iter(script)
    monkeypatch.setattr(tracker, "detect_landmarks", lambda *_: next(it, None))
    return lm


def hand(ratio):
    return [mf.hand(0.5, 0.5, ratio).get(str(i), (0.5, 0.5)) for i in range(21)]


def test_stop_event_releases_everything_and_cancels_active_gesture(monkeypatch):
    cap = FakeCap()
    script = [hand(mf.OPEN)] * 20 + [hand(mf.PINCH)] * 400
    lm = patch(monkeypatch, cap, script)
    stop, events = threading.Event(), []

    def emit(ev):
        events.append(ev)
        if ev["type"] == "gesture_start":
            stop.set()  # stop mid-pinch

    th = threading.Thread(target=tracker.run_hand_tracker, args=(emit, stop, {"smoothing": 0}))
    th.start(); th.join(10)
    assert not th.is_alive()
    assert cap.released and lm.closed
    kinds = [e["type"] for e in events if e["type"] != "hand_frame"]
    assert kinds == ["gesture_start", "gesture_cancel"]
    assert events[-1]["payload"]["reason"] == "shutdown"


def test_camera_failure_raises_and_cleans_up(monkeypatch):
    cap = FakeCap(fail_after=2)
    lm = patch(monkeypatch, cap, [])
    with pytest.raises(RuntimeError, match="camera stopped"):
        tracker.run_hand_tracker(lambda e: None, threading.Event(), {"camera_fail_timeout_s": 0.1})
    assert cap.released and lm.closed


def test_missing_model_fails_before_camera(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(tracker, "_open_camera", lambda cfg: opened.append(1))
    with pytest.raises(FileNotFoundError, match="companion.hands.model"):
        tracker.run_hand_tracker(lambda e: None, threading.Event(), {"model_path": str(tmp_path / "nope.task")})
    assert not opened


def test_preview_is_dropped_off_main_thread_on_macos(monkeypatch):
    monkeypatch.setattr(tracker.pv, "preview_allowed", lambda: False)
    cap = FakeCap()
    patch(monkeypatch, cap, [None] * 5)
    stop = threading.Event()
    th = threading.Thread(target=tracker.run_hand_tracker, args=(lambda e: stop.set(), stop, {"preview": True}))
    th.start(); th.join(10)
    assert not th.is_alive() and cap.released
