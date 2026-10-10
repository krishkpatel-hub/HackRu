"""Preview drawing and window handling (OpenCV HighGUI)."""

from __future__ import annotations

import sys
import threading
from typing import Optional, Sequence

import cv2

from .engine import HandEngine

# MediaPipe hand skeleton
_BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
          (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


def preview_allowed() -> bool:
    """HighGUI on macOS must run on the main thread; elsewhere any thread works."""
    if sys.platform == "darwin":
        return threading.current_thread() is threading.main_thread()
    return True


def draw(frame, landmarks: Optional[Sequence], engine: HandEngine, fps: float):
    """Draw onto the (already mirrored) frame in place and return it."""
    h, w = frame.shape[:2]
    if landmarks is not None:
        pts = [(int(p[0] * w), int(p[1] * h)) for p in landmarks]
        for a, b in _BONES:
            cv2.line(frame, pts[a], pts[b], (200, 200, 200), 1, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, p, 2, (0, 200, 255), -1, cv2.LINE_AA)
        cv2.line(frame, pts[4], pts[8], (0, 255, 0) if engine.pinching else (0, 120, 255), 2, cv2.LINE_AA)
    if engine.cursor is not None:
        cx, cy = int(engine.cursor[0] * w), int(engine.cursor[1] * h)
        color = (0, 255, 0) if engine.pinching else (255, 255, 0)
        cv2.circle(frame, (cx, cy), 12, color, 2, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 2, color, -1, cv2.LINE_AA)
    if not engine.present:
        track = "LOST"
    else:
        track = "TRACKING"
    pinch = "PINCH" if engine.pinching else ("open hand needed" if engine.needs_release else "ready")
    cur = "u=%.3f v=%.3f" % engine.cursor if engine.cursor else "u=null v=null"
    ratio = "ratio=%.2f" % engine.ratio if engine.ratio is not None else "ratio=-"
    lines = (f"{track}  {pinch}", cur, ratio, f"{fps:4.1f} fps  (q/Esc quits)")
    cv2.rectangle(frame, (0, 0), (260, 12 + 20 * len(lines)), (0, 0, 0), -1)
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (8, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def show(window: str, frame) -> bool:
    """Show a frame; return False when the user asked to quit (q/Esc/window closed)."""
    cv2.imshow(window, frame)
    key = cv2.waitKey(1) & 0xFF
    if key in (ord("q"), 27):
        return False
    try:
        return cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False
