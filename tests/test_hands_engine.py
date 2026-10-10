"""Detection-logic tests: no webcam, no OpenCV/MediaPipe needed."""
import itertools
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent / "test_hands_fixtures"))

from companion.hands.config import HandConfig  # noqa: E402
from companion.hands.engine import HandEngine, pinch_ratio  # noqa: E402
from companion.hands.replay import run_fixture  # noqa: E402
import make_fixtures as mf  # noqa: E402

FIX = Path(__file__).parent / "test_hands_fixtures"


def replay(segments, **cfg):
    counter = itertools.count()
    e = HandEngine(HandConfig.from_mapping(cfg), lambda: f"g{next(counter)}")
    out = []
    for fr in mf.build(segments):
        lm = None if fr["lm"] is None else {int(k): tuple(v) for k, v in fr["lm"].items()}
        out += e.update(fr["t"], lm, mf.ASPECT)
    return e, out


def types(events, kind):
    return [x for x in events if x["type"] == kind]


O, P = mf.OPEN, mf.PINCH


def test_normal_pinch_one_pair_and_direction():
    _, ev = replay(mf.SCENARIOS["normal_pinch"], smoothing=0.0)
    starts, ends = types(ev, "gesture_start"), types(ev, "gesture_end")
    assert len(starts) == len(ends) == 1 and not types(ev, "gesture_cancel")
    s, e = starts[0]["payload"], ends[0]["payload"]
    assert s["gesture_id"] == e["gesture_id"]
    assert abs(s["u"] - 0.3) < 0.01 and abs(s["v"] - 0.5) < 0.01   # where the pinch began
    assert e["u"] > s["u"] + 0.2 and e["v"] > s["v"]                # moved right and down
    pinch_frames = [x for x in types(ev, "hand_frame") if x["payload"]["pinching"]]
    assert pinch_frames and all(0 <= x["payload"]["u"] <= 1 for x in pinch_frames)


def test_held_pinch_single_start_no_end_until_release():
    e, ev = replay(mf.SCENARIOS["held_pinch"][:2])
    assert len(types(ev, "gesture_start")) == 1 and not types(ev, "gesture_end")
    assert e.pinching
    _, ev = replay(mf.SCENARIOS["held_pinch"])
    assert len(types(ev, "gesture_start")) == len(types(ev, "gesture_end")) == 1


def test_first_pinch_requires_open_hand():
    _, ev = replay([(30, (0.5, 0.5, 0.5, 0.5, P))])
    assert not types(ev, "gesture_start")


def test_short_loss_keeps_gesture():
    _, ev = replay(mf.SCENARIOS["short_loss"])
    assert len(types(ev, "gesture_start")) == len(types(ev, "gesture_end")) == 1
    assert not types(ev, "gesture_cancel")
    absent = [x["payload"] for x in types(ev, "hand_frame") if not x["payload"]["present"]]
    assert absent and all(p["u"] is None and p["v"] is None and p["pinching"] for p in absent)  # frozen, still "pinching"


def test_long_loss_cancels_once_then_needs_release():
    _, ev = replay(mf.SCENARIOS["long_loss_recovery"])
    starts, cancels, ends = (types(ev, k) for k in ("gesture_start", "gesture_cancel", "gesture_end"))
    assert len(starts) == 2 and len(cancels) == 1 and len(ends) == 1
    assert cancels[0]["payload"] == {"gesture_id": starts[0]["payload"]["gesture_id"], "reason": "tracking_lost"}
    assert ends[0]["payload"]["gesture_id"] == starts[1]["payload"]["gesture_id"] != starts[0]["payload"]["gesture_id"]
    # order: start, cancel, start, end -- the still-pinched return in between produced nothing
    kinds = [x["type"] for x in ev if x["type"] != "hand_frame"]
    assert kinds == ["gesture_start", "gesture_cancel", "gesture_start", "gesture_end"]


def test_present_false_is_immediate_and_cancel_is_about_half_a_second():
    e = HandEngine(HandConfig.from_mapping({}))
    t, out = 0.0, []
    for spec in [(10, (0.5, 0.5, 0.5, 0.5, O)), (15, (0.5, 0.5, 0.5, 0.5, P))]:
        for fr in mf.build([spec]):
            out = e.update(t, {int(k): tuple(v) for k, v in fr["lm"].items()}, mf.ASPECT); t += 1 / 30
    assert e.pinching
    first = e.update(t, None, mf.ASPECT)
    assert first[-1]["payload"]["present"] is False and first[-1]["type"] == "hand_frame"
    cancel_t = None
    for i in range(1, 40):
        if types(e.update(t + i / 30, None, mf.ASPECT), "gesture_cancel"):
            cancel_t = i / 30
            break
    assert cancel_t is not None and 0.45 <= cancel_t <= 0.6


def test_hysteresis_deadband_and_flicker():
    mid = (0.35 + 0.60) / 2
    # in the dead band between thresholds: never starts
    _, ev = replay([(10, (0.5, 0.5, 0.5, 0.5, O)), (30, (0.5, 0.5, 0.5, 0.5, mid))])
    assert not types(ev, "gesture_start")
    # two-frame pinch blip (< 80 ms stability) does not start
    _, ev = replay([(10, (0.5, 0.5, 0.5, 0.5, O)), (2, (0.5, 0.5, 0.5, 0.5, P)), (10, (0.5, 0.5, 0.5, 0.5, O))])
    assert not types(ev, "gesture_start")
    # once pinching, dead band keeps it; a 2-frame open blip does not end it
    e, ev = replay([(10, (0.5, 0.5, 0.5, 0.5, O)), (15, (0.5, 0.5, 0.5, 0.5, P)),
                    (20, (0.5, 0.5, 0.5, 0.5, mid)), (2, (0.5, 0.5, 0.5, 0.5, O)),
                    (10, (0.5, 0.5, 0.5, 0.5, P))])
    assert len(types(ev, "gesture_start")) == 1 and not types(ev, "gesture_end") and e.pinching


def test_cursor_direction_and_bounds():
    e = HandEngine(HandConfig.from_mapping({"smoothing": 0.0}))
    lm = lambda u, v: {int(k): tuple(x) for k, x in mf.hand(u, v, O).items()}
    e.update(0.0, lm(0.2, 0.3), mf.ASPECT)
    e.update(0.034, lm(0.8, 0.9), mf.ASPECT)
    assert e.cursor == pytest.approx((0.8, 0.9))          # u: left->right, v: top->bottom
    e.update(0.07, lm(1.2, -0.3), mf.ASPECT)              # tip outside the frame: clamped
    assert e.cursor == (1.0, 0.0)


def test_smoothing_reduces_jitter_and_converges():
    lm = lambda u: {int(k): tuple(x) for k, x in mf.hand(u, 0.5, O).items()}
    raw, smooth = HandEngine(HandConfig(smoothing=0.0)), HandEngine(HandConfig(smoothing=0.7))
    for e in (raw, smooth):
        e.update(0.0, lm(0.2), mf.ASPECT)
    raw.update(1 / 30, lm(0.6), mf.ASPECT); smooth.update(1 / 30, lm(0.6), mf.ASPECT)
    assert raw.cursor[0] == pytest.approx(0.6) and 0.2 < smooth.cursor[0] < 0.6
    for i in range(2, 80):
        smooth.update(i / 30, lm(0.6), mf.ASPECT)
    assert smooth.cursor[0] == pytest.approx(0.6, abs=0.01)


def test_frame_rate_is_capped_near_30hz():
    e = HandEngine(HandConfig())
    n = 0
    for i in range(120):  # 60 fps camera for 2 s
        n += len(types(e.update(i / 60, {int(k): tuple(x) for k, x in mf.hand(0.5, 0.5, O).items()}, mf.ASPECT), "hand_frame"))
    assert 55 <= n <= 66


def test_ratio_normalised_by_palm_size_and_degenerate():
    near, far = mf.hand(0.5, 0.5, 0.3), None
    r = pinch_ratio({int(k): tuple(v) for k, v in near.items()}, mf.ASPECT)
    assert r == pytest.approx(0.3, abs=0.01)
    # same hand at half scale (farther from the camera) -> same ratio
    half = {int(k): (0.5 + (v[0] - 0.5) / 2, 0.5 + (v[1] - 0.5) / 2) for k, v in near.items()}
    assert pinch_ratio(half, mf.ASPECT) == pytest.approx(r, rel=0.02)
    flat = {i: (0.5, 0.5) for i in (0, 4, 5, 8, 9, 17)}
    assert pinch_ratio(flat, mf.ASPECT) is None
    e = HandEngine(HandConfig())
    assert e.update(0.0, flat, mf.ASPECT)[-1]["payload"]["present"] is False


def test_shutdown_cancels_active_gesture_once():
    e, _ = replay(mf.SCENARIOS["held_pinch"][:2])
    gid = e.gesture_id
    out = e.shutdown()
    assert out == [{"type": "gesture_cancel", "payload": {"gesture_id": gid, "reason": "shutdown"}}]
    assert e.shutdown() == []


@pytest.mark.parametrize("name,starts,ends,cancels", [
    ("normal_pinch", 1, 1, 0), ("held_pinch", 1, 1, 0), ("short_loss", 1, 1, 0), ("long_loss_recovery", 2, 1, 1)])
def test_replay_fixture_files(name, starts, ends, cancels):
    ev = run_fixture(FIX / f"{name}.json")
    assert (len(types(ev, "gesture_start")), len(types(ev, "gesture_end")), len(types(ev, "gesture_cancel"))) == (starts, ends, cancels)
    for x in ev:
        assert set(x) == {"type", "payload"}
        p = x["payload"]
        if x["type"] == "hand_frame" and p["present"]:
            assert 0 <= p["u"] <= 1 and 0 <= p["v"] <= 1


def test_config_validation():
    for bad in ({"pinch_start": 0.7, "pinch_release": 0.5}, {"smoothing": 1.0}, {"nope": 1}, {"emit_hz": 0}):
        with pytest.raises(ValueError):
            HandConfig.from_mapping(bad)
