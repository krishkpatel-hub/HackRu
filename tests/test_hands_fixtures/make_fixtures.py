"""Regenerate the replay fixtures: python tests/test_hands_fixtures/make_fixtures.py"""
import json
from pathlib import Path

ASPECT = 4 / 3
PALM = 0.25  # wrist->middle MCP in image-height units


def hand(u, v, ratio):
    """Synthetic landmarks: index tip at (u, v), thumb tip ratio*palm away (to the left)."""
    thumb = (u - ratio * PALM / ASPECT, v)
    r = lambda p: [round(p[0], 4), round(p[1], 4)]
    return {"0": r((0.5, 0.8)), "4": r(thumb), "5": r((0.42, 0.6)),
            "8": r((u, v)), "9": r((0.5, 0.55)), "17": r((0.6, 0.62))}


def build(segments, fps=30):
    """segments: (n_frames, None | (u0, v0, u1, v1, ratio)) -> frames list."""
    frames, i = [], 0
    for n, spec in segments:
        for k in range(n):
            f = k / max(n - 1, 1)
            lm = None if spec is None else hand(spec[0] + (spec[2] - spec[0]) * f,
                                                spec[1] + (spec[3] - spec[1]) * f, spec[4])
            frames.append({"t": round(i / fps, 4), "lm": lm})
            i += 1
    return frames


OPEN, PINCH = 0.9, 0.15
SCENARIOS = {
    # open, pinch+drag left->right, release: exactly one start/end pair
    "normal_pinch": [(10, (0.3, 0.5, 0.3, 0.5, OPEN)), (15, (0.3, 0.5, 0.3, 0.5, PINCH)),
                     (30, (0.3, 0.5, 0.7, 0.6, PINCH)), (10, (0.7, 0.6, 0.7, 0.6, OPEN))],
    # held ~3 s
    "held_pinch": [(10, (0.5, 0.5, 0.5, 0.5, OPEN)), (90, (0.5, 0.5, 0.5, 0.5, PINCH)),
                   (10, (0.5, 0.5, 0.5, 0.5, OPEN))],
    # 0.2 s dropout while pinched, same gesture continues
    "short_loss": [(10, (0.4, 0.4, 0.4, 0.4, OPEN)), (15, (0.4, 0.4, 0.4, 0.4, PINCH)), (6, None),
                   (15, (0.4, 0.4, 0.6, 0.4, PINCH)), (10, (0.6, 0.4, 0.6, 0.4, OPEN))],
    # 0.7 s loss: cancel once; return pinched = no start; open, pinch again = new gesture
    "long_loss_recovery": [(10, (0.4, 0.4, 0.4, 0.4, OPEN)), (15, (0.4, 0.4, 0.4, 0.4, PINCH)),
                           (21, None), (15, (0.5, 0.5, 0.5, 0.5, PINCH)), (10, (0.5, 0.5, 0.5, 0.5, OPEN)),
                           (15, (0.5, 0.5, 0.5, 0.5, PINCH)), (10, (0.5, 0.5, 0.5, 0.5, OPEN))],
}

if __name__ == "__main__":
    out = Path(__file__).parent
    for name, segs in SCENARIOS.items():
        data = {"aspect": round(ASPECT, 4), "config": {}, "frames": build(segs)}
        (out / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
        print(name, len(data["frames"]), "frames")
