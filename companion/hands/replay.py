"""Replay a landmark fixture through HandEngine without a webcam.

Fixture JSON: {"aspect": 1.333, "config": {...optional HandConfig overrides...},
               "frames": [{"t": 0.0, "lm": {"0": [x, y], "4": [x, y], ...} | null}, ...]}
Only landmark indices 0, 4, 5, 8, 9, 17 are needed. ``python -m companion.hands.replay f.json``
prints the emitted events as JSON lines.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

from .config import HandConfig
from .engine import HandEngine


def run_fixture(path, new_id=None) -> List[dict]:
    data = json.loads(Path(path).read_text())
    cfg = HandConfig.from_mapping(data.get("config"))
    engine = HandEngine(cfg, new_id) if new_id else HandEngine(cfg)
    events: List[dict] = []
    for fr in data["frames"]:
        lm = fr["lm"]
        if lm is not None:
            lm = {int(k): tuple(v) for k, v in lm.items()}
        events += engine.update(fr["t"], lm, data.get("aspect", 4 / 3))
    events += engine.shutdown()
    return events


if __name__ == "__main__":
    for ev in run_fixture(sys.argv[1]):
        print(json.dumps(ev, separators=(",", ":")))
