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
    manipulator_hand: str = "Right"

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
        if type(self.two_hands) is not bool or self.manipulator_hand not in {"Left", "Right"}:
            raise ValueError("two_hands must be bool; manipulator_hand must be Left or Right")
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
