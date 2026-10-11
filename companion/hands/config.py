"""Tracker configuration. Every field can be overridden through the ``config`` mapping."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Optional

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"


@dataclass
class HandConfig:
    # Camera
    camera_index: int = 0
    width: int = 640
    height: int = 480
    camera_fps: int = 30
    camera_fail_timeout_s: float = 3.0  # consecutive failed reads before run_hand_tracker raises

    # MediaPipe
    model_path: Optional[str] = None  # default: $HAND_LANDMARKER_MODEL or models/hand_landmarker.task
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    two_hands: bool = False
    manipulator_hand: str = "Right"  # legacy CLI compatibility; clutch roles are anatomical/fixed
    identity_confidence: float = 0.8
    identity_acquire_s: float = 0.3
    identity_recover_s: float = 0.08
    identity_max_step: float = 0.18
    identity_separation: float = 0.12

    # Whole-hand open/isolated-pinch pose hysteresis.
    finger_open_enter: float = .72
    finger_open_exit: float = .60

    feature_smoothing_s: float = .05  # one time-based articulation/orientation filter
    feature_max_gap_s: float = .20  # reset rather than blend across missing data

    record_landmarks: Optional[str] = None
    record_seconds: float = 20.

    # Output
    emit_hz: float = 30.0

    # Cursor smoothing (one exponential filter). 0 = off, 0.9 = very heavy.
    # Value is the weight kept from the previous cursor per 1/30 s; it is frame-rate independent.
    smoothing: float = 0.5

    # Pinch = thumb tip to index tip distance / palm size.
    pinch_start: float = 0.35      # ratio at or below this starts a pinch
    pinch_release: float = 0.60    # ratio at or above this releases (must exceed pinch_start)
    pinch_stable_ms: float = 80.0  # condition must hold this long before a transition

    # Pinch-aware cursor. Closing/opening the fingers moves the index tip (~15% of frame height on a
    # laptop webcam), so the cursor is held while fingers close/open instead of following the tip.
    pinch_approach: float = 0.75      # ratio below which the cursor holds its pre-close aim point
    anchor_lookback_ms: float = 100.0 # aim point = cursor this long before the hold began
    approach_hold_max_s: float = 0.4  # a hold that never becomes a pinch is released after this long
    open_hold_delta: float = 0.10     # ratio rise above the pinch minimum that freezes the cursor (release began)

    # Tracking loss
    loss_cancel_s: float = 0.5

    # Preview (cv2.imshow). Off by default for embedding; the standalone CLI turns it on.
    preview: bool = False
    window_name: str = "Air Modeler hands"

    @classmethod
    def from_mapping(cls, config: Optional[Mapping[str, Any]]) -> "HandConfig":
        if isinstance(config, cls):
            cfg = config
        else:
            known = {f.name for f in fields(cls)}
            extra = set(config or {}) - known
            if extra:
                raise ValueError(f"unknown hand config keys: {sorted(extra)}")
            cfg = cls(**dict(config or {}))
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not 1 <= self.record_seconds <= 60:
            raise ValueError('Recording length must be 1–60 seconds')
        if self.record_landmarks and not self.two_hands:
            raise ValueError('Landmark recording requires two_hands')
        if type(self.two_hands) is not bool or self.manipulator_hand not in {"Left", "Right"}:
            raise ValueError("two_hands must be bool; manipulator_hand must be Left or Right")
        if self.two_hands and self.manipulator_hand != 'Right':
            raise ValueError("clutch mode uses fixed anatomical Left selection / Right manipulation roles")
        import math
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (self.feature_smoothing_s,self.feature_max_gap_s)) or not 0<=self.feature_smoothing_s<=.2 or not 0<self.feature_max_gap_s<=.5:
            raise ValueError('Feature smoothing must be 0–0.2 seconds; gap must be >0 and <=0.5 seconds')
        identity_values = (self.identity_confidence, self.identity_acquire_s,
                           self.identity_recover_s, self.identity_max_step, self.identity_separation)
        if not all(type(v) in (int, float) and math.isfinite(v) for v in identity_values):
            raise ValueError("identity settings must be finite numbers")
        if not .5 <= self.identity_confidence <= 1 or min(identity_values[1:]) <= 0:
            raise ValueError("identity confidence must be .5–1 and identity windows/distances positive")
        if not 0 < self.finger_open_exit < self.finger_open_enter <= 1:
            raise ValueError("need 0 < finger_open_exit < finger_open_enter <= 1")
        if not 0.0 <= self.smoothing < 1.0:
            raise ValueError("smoothing must be in [0, 1)")
        if not 0.0 < self.pinch_start < self.pinch_release:
            raise ValueError("need 0 < pinch_start < pinch_release")
        if self.pinch_approach <= self.pinch_release or self.open_hold_delta <= 0:
            raise ValueError("need pinch_approach > pinch_release and open_hold_delta > 0")
        if self.anchor_lookback_ms < 0 or self.approach_hold_max_s <= 0:
            raise ValueError("anchor_lookback_ms must be >= 0 and approach_hold_max_s > 0")
        if self.pinch_stable_ms < 0 or self.loss_cancel_s < 0:
            raise ValueError("pinch_stable_ms and loss_cancel_s must be >= 0")
        if self.emit_hz <= 0:
            raise ValueError("emit_hz must be > 0")

    def resolved_model_path(self) -> Path:
        if self.model_path:
            return Path(self.model_path).expanduser()
        env = os.environ.get("HAND_LANDMARKER_MODEL")
        return Path(env).expanduser() if env else DEFAULT_MODEL_PATH
