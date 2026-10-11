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


def test_two_hand_tracker_single_stream_coherent_observations(monkeypatch):
    cap=FakeCap(); lm=FakeLandmarker()
    monkeypatch.setattr(tracker,'_open_camera',lambda cfg:cap)
    monkeypatch.setattr(tracker,'_make_landmarker',lambda cfg:lm)
    ticks=[0]
    def detect(*_):
        ticks[0]+=1
        right=[(x-.25,y) for x,y in hand(mf.OPEN if ticks[0]<60 else mf.PINCH)]
        left=[(x+.25,y) for x,y in hand(mf.PINCH)]
        values=[('Right',.99,right),('Left',.99,left)]
        return values if ticks[0]%2 else list(reversed(values))
    monkeypatch.setattr(tracker,'detect_hands',detect)
    events=[]; stop=threading.Event()
    def emit(event):
        events.append(event)
        if event['type']=='hands_frame' and event['payload']['hands']['Right']['event']=='START':
            stop.set()
    thread=threading.Thread(target=tracker.run_hand_tracker,args=(emit,stop,{'two_hands':True,'smoothing':0}))
    thread.start(); thread.join(5)
    if thread.is_alive(): stop.set();thread.join(2)
    assert not thread.is_alive() and cap.released and lm.closed
    assert all(e['type']=='hands_frame' for e in events)
    assert len([e for e in events if e['payload']['hands']['Right']['event']=='START'])==1
    assert events[-1]['payload']['hands']['Right']['event']=='CANCEL'
    assert not any(e['payload']['hands']['Left']['event']=='START' for e in events)
    from shared.protocol import validate_event
    for event in events: validate_event(event)


def test_two_hand_pipeline_mirrors_once_before_inference(monkeypatch):
    class PatternCap(FakeCap):
        def read(self):
            frame=np.zeros((2,4,3),np.uint8)
            frame[:,0,:]=10
            frame[:,-1,:]=200
            return True,frame
    cap=PatternCap();lm=FakeLandmarker();stop=threading.Event();seen=[]
    monkeypatch.setattr(tracker,'_open_camera',lambda cfg:cap)
    monkeypatch.setattr(tracker,'_make_landmarker',lambda cfg:lm)
    def detect(_landmarker,frame,_timestamp):
        seen.append(frame.copy())
        return []
    monkeypatch.setattr(tracker,'detect_hands',detect)
    tracker.run_hand_tracker(lambda event:stop.set(),stop,{'two_hands':True})
    assert len(seen)==1
    assert np.all(seen[0][:,0,:]==200) and np.all(seen[0][:,-1,:]==10)
    assert cap.released and lm.closed


def test_two_hand_camera_failure_cancels_and_releases(monkeypatch):
    cap=FakeCap(fail_after=85);lm=FakeLandmarker();events=[]
    monkeypatch.setattr(tracker,'_open_camera',lambda cfg:cap)
    monkeypatch.setattr(tracker,'_make_landmarker',lambda cfg:lm)
    monkeypatch.setattr(tracker,'detect_hands',lambda *_:[
        ('Left',.99,hand(mf.OPEN if cap.n<55 else mf.PINCH))])
    with pytest.raises(RuntimeError,match='camera stopped'):
        tracker.run_hand_tracker(events.append,threading.Event(),
            {'two_hands':True,'camera_fail_timeout_s':.1,'smoothing':0})
    assert cap.released and lm.closed
    transitions=[event['payload']['hands']['Left']['event'] for event in events
                 if event['payload']['hands']['Left']['event']!='NONE']
    assert transitions==['START','CANCEL']
    from shared.protocol import validate_event
    for event in events: validate_event(event)
