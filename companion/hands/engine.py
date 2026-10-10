"""Pure detection logic: landmarks in, README hand events out. No OpenCV/MediaPipe, no clock.

Landmarks are MediaPipe hand landmarks in the *already mirrored* image, normalized to [0, 1]
(x left->right, y top->bottom). Only indices 0 (wrist), 4 (thumb tip), 5/9/17 (MCPs) and
8 (index tip) are read, so replay fixtures can be tiny.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .config import HandConfig

WRIST, THUMB_TIP, INDEX_MCP, MIDDLE_MCP, INDEX_TIP, PINKY_MCP = 0, 4, 5, 9, 8, 17

Event = Dict[str, Any]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def pinch_ratio(lm: Any, aspect: float) -> Optional[float]:
    """Thumb-tip to index-tip distance divided by palm size, or None if degenerate.

    Distances are measured in image-height units (x scaled by ``aspect`` = width/height) so the
    metric is not distorted by a non-square frame. Palm size is the larger of wrist->middle-MCP
    and index-MCP->pinky-MCP, which stays usable when the hand points at the camera.
    """

    def d(a: int, b: int) -> float:
        return math.hypot((lm[a][0] - lm[b][0]) * aspect, lm[a][1] - lm[b][1])

    palm = max(d(WRIST, MIDDLE_MCP), d(INDEX_MCP, PINKY_MCP))
    if not math.isfinite(palm) or palm < 1e-4:
        return None
    ratio = d(THUMB_TIP, INDEX_TIP) / palm
    return ratio if math.isfinite(ratio) else None


class HandEngine:
    """Cursor filter + pinch hysteresis + gesture lifecycle.

    Call ``update(t, landmarks, aspect)`` once per processed camera frame (``landmarks=None`` when
    no hand). It returns the events to emit, in order. ``t`` is seconds, monotonically increasing.
    """

    def __init__(self, config: HandConfig, new_id: Callable[[], str] = lambda: str(uuid.uuid4())):
        self.cfg = config
        self._new_id = new_id
        self.gesture_id: Optional[str] = None
        self.needs_release = True  # a visibly released hand is required before the first pinch too
        # exposed for the preview
        self.present = False
        self.cursor: Optional[Tuple[float, float]] = None
        self.ratio: Optional[float] = None
        self._smooth: Optional[Tuple[float, float]] = None
        self._last_t: Optional[float] = None
        self._lost_since: Optional[float] = None
        self._pinch_since: Optional[float] = None
        self._pinch_pos: Optional[Tuple[float, float]] = None
        self._open_since: Optional[float] = None
        self._open_pos: Optional[Tuple[float, float]] = None
        self._last_frame_t: Optional[float] = None
        self._last_frame_state: Optional[Tuple[bool, bool]] = None

    @property
    def pinching(self) -> bool:
        return self.gesture_id is not None

    # ------------------------------------------------------------------ public
    def update(self, t: float, landmarks: Optional[Sequence], aspect: float = 4 / 3) -> List[Event]:
        events: List[Event] = []
        ratio = None
        raw = None
        if landmarks is not None:
            try:
                ratio = pinch_ratio(landmarks, aspect)
                x, y = landmarks[INDEX_TIP][0], landmarks[INDEX_TIP][1]
                if ratio is not None and math.isfinite(x) and math.isfinite(y):
                    raw = (_clamp01(float(x)), _clamp01(float(y)))
            except (IndexError, KeyError, TypeError, ValueError):
                raw = None
        dt = 1 / 30 if self._last_t is None else max(t - self._last_t, 0.0)
        self._last_t = t

        if raw is None:
            self._on_lost(t, events)
        else:
            self._on_seen(t, dt, raw, ratio, events)
        self._maybe_frame(t, events)
        return events

    def shutdown(self) -> List[Event]:
        """Cancel any active gesture (call once on stop) so nothing is left dangling."""
        events: List[Event] = []
        self._cancel("shutdown", events)
        return events

    # ----------------------------------------------------------------- internals
    def _stable(self) -> float:
        return self.cfg.pinch_stable_ms / 1000.0

    def _on_lost(self, t: float, events: List[Event]) -> None:
        self.present = False
        self.cursor = None
        self.ratio = None
        self._smooth = None  # re-acquire from the raw position, no drag from the old spot
        self._pinch_since = self._open_since = None
        if self._lost_since is None:
            self._lost_since = t
        if t - self._lost_since >= self.cfg.loss_cancel_s:
            # sustained loss: cancel once, and demand a visibly open hand on return
            self._cancel("tracking_lost", events)

    def _on_seen(self, t, dt, raw, ratio, events) -> None:
        self._lost_since = None
        self.present = True
        self.ratio = ratio
        self.cursor = self._filter(raw, dt)
        cfg = self.cfg

        if self.gesture_id is not None:
            # active: only a stable release ends it
            if ratio >= cfg.pinch_release:
                if self._open_since is None:
                    self._open_since, self._open_pos = t, self.cursor
                if t - self._open_since >= self._stable():
                    u, v = self._open_pos
                    events.append(_ev("gesture_end", gesture_id=self.gesture_id, u=u, v=v))
                    self.gesture_id = None
                    self._open_since = self._open_pos = None
            else:
                self._open_since = self._open_pos = None
            return

        # idle
        if self.needs_release:
            if ratio >= cfg.pinch_release:
                if self._open_since is None:
                    self._open_since = t
                if t - self._open_since >= self._stable():
                    self.needs_release = False
                    self._open_since = None
            else:
                self._open_since = None
            self._pinch_since = self._pinch_pos = None
            return

        if ratio <= cfg.pinch_start:
            if self._pinch_since is None:
                # remember where the cursor was when the pinch began, before the fingers
                # closing drag the index tip away
                self._pinch_since, self._pinch_pos = t, self.cursor
            if t - self._pinch_since >= self._stable():
                u, v = self._pinch_pos
                self.gesture_id = self._new_id()
                events.append(_ev("gesture_start", gesture_id=self.gesture_id, u=u, v=v))
                self._pinch_since = self._pinch_pos = None
        else:
            self._pinch_since = self._pinch_pos = None

    def _cancel(self, reason: str, events: List[Event]) -> None:
        if self.gesture_id is not None:
            events.append(_ev("gesture_cancel", gesture_id=self.gesture_id, reason=reason))
            self.gesture_id = None
        self.needs_release = True
        self._open_since = self._pinch_since = None

    def _filter(self, raw, dt) -> Tuple[float, float]:
        if self._smooth is None or self.cfg.smoothing <= 0:
            self._smooth = raw
        else:
            keep = self.cfg.smoothing ** (dt * 30.0)
            sx, sy = self._smooth
            self._smooth = (keep * sx + (1 - keep) * raw[0], keep * sy + (1 - keep) * raw[1])
        return self._smooth

    def _maybe_frame(self, t: float, events: List[Event]) -> None:
        state = (self.present, self.pinching)
        interval = 1.0 / self.cfg.emit_hz
        due = self._last_frame_t is None or t - self._last_frame_t >= interval - 0.004
        # state flips are never rate limited: loss/recovery/pinch must be seen immediately
        if not (due or state != self._last_frame_state or len(events) > 0):
            return
        self._last_frame_t, self._last_frame_state = t, state
        u, v = self.cursor if self.present and self.cursor else (None, None)
        events.append(_ev("hand_frame", u=u, v=v, present=self.present, pinching=self.pinching))


def _ev(type_: str, **payload: Any) -> Event:
    return {"type": type_, "payload": payload}
