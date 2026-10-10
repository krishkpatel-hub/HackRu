"""run_hand_tracker(emit, stop_event, config) -> None  (README contract)."""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable, Mapping, Optional

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from . import preview as pv
from .config import HandConfig
from .engine import HandEngine


def _open_camera(cfg: HandConfig):
    cap = cv2.VideoCapture(cfg.camera_index)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(
            f"cannot open camera {cfg.camera_index}. Check permissions "
            "(macOS: System Settings > Privacy & Security > Camera for your terminal) and camera_index."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, cfg.camera_fps)
    return cap


def _make_landmarker(cfg: HandConfig):
    model = cfg.resolved_model_path()
    if not model.is_file():
        raise FileNotFoundError(
            f"hand landmarker model not found at {model}. "
            "Run: python -m companion.hands.model   (or set model_path / $HAND_LANDMARKER_MODEL)"
        )
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2 if cfg.two_hands else 1,
        min_hand_detection_confidence=cfg.min_detection_confidence,
        min_hand_presence_confidence=cfg.min_presence_confidence,
        min_tracking_confidence=cfg.min_tracking_confidence,
    )
    return vision.HandLandmarker.create_from_options(options)


def detect_landmarks(landmarker, mirrored_bgr, timestamp_ms: int):
    """Run inference on an already-mirrored BGR frame; return [(x, y), ...] or None."""
    rgb = cv2.cvtColor(mirrored_bgr, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(image, timestamp_ms)
    if not result.hand_landmarks:
        return None
    return [(p.x, p.y) for p in result.hand_landmarks[0]]


def detect_hands(landmarker, mirrored_bgr, timestamp_ms):
    rgb = cv2.cvtColor(mirrored_bgr, cv2.COLOR_BGR2RGB)
    result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
    return [(labels[0].category_name, labels[0].score, [(p.x,p.y) for p in points])
            for points, labels in zip(result.hand_landmarks, result.handedness) if labels]


def run_hand_tracker(
    emit: Callable[[dict], Any],
    stop_event: threading.Event,
    config: Optional[Mapping[str, Any]] = None,
) -> None:
    """Track one hand until ``stop_event`` is set. Blocks; emits README hand events via ``emit``.

    Raises RuntimeError / FileNotFoundError on setup failure (camera, model) *before* emitting
    anything, and RuntimeError if the camera keeps failing. Camera, landmarker and preview window
    are always released, and an active gesture is cancelled (reason "shutdown") on exit.
    """
    cfg = HandConfig.from_mapping(config)
    show_preview = cfg.preview
    if show_preview and not pv.preview_allowed():
        print("hands: preview disabled (macOS HighGUI needs the main thread)", file=sys.stderr)
        show_preview = False

    landmarker = _make_landmarker(cfg)
    cap = None
    engine = HandEngine(cfg)
    from .roles import Roles, pose
    roles = Roles(cfg.manipulator_hand) if cfg.two_hands else None
    try:
        cap = _open_camera(cfg)
        t0 = time.monotonic()
        last_ts_ms = -1
        fps, fps_t = 0.0, t0
        fail_since: Optional[float] = None
        while not stop_event.is_set():
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok or frame is None:
                fail_since = fail_since or now
                if now - fail_since > cfg.camera_fail_timeout_s:
                    raise RuntimeError("camera stopped delivering frames")
                for ev in engine.update(now - t0, None):  # keep loss/cancel timing alive
                    emit(ev)
                stop_event.wait(0.01)
                continue
            fail_since = None

            frame = cv2.flip(frame, 1)  # mirror once; inference and preview share this image
            ts_ms = max(int((now - t0) * 1000), last_ts_ms + 1)
            last_ts_ms = ts_ms
            h, w = frame.shape[:2]
            if roles is not None:
                landmarks, selector = roles.update(detect_hands(landmarker, frame, ts_ms), now-t0, engine.pinching)
                emit({'type':'selector_frame', 'payload':dict(
                    pose=pose(selector, w/h) if selector is not None else 'ABSENT',
                    manipulator=roles.manipulator, selector=roles.selector)})
            else:
                landmarks = detect_landmarks(landmarker, frame, ts_ms)
            for ev in engine.update(now - t0, landmarks, aspect=w / h):
                emit(ev)

            dt = now - fps_t
            if dt > 0:
                fps = 0.9 * fps + 0.1 / dt if fps else 1.0 / dt
            fps_t = now
            if show_preview:
                if not pv.show(cfg.window_name, pv.draw(frame, landmarks, engine, fps)):
                    stop_event.set()
    finally:
        try:
            for ev in engine.shutdown():
                emit(ev)
        finally:
            if cap is not None:
                cap.release()
            landmarker.close()
            if show_preview:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
