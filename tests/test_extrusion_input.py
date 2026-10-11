"""Recognition-only filtering and stateless deformation; no live calibration claims."""
import importlib.util
from pathlib import Path
import math

import pytest

spec = importlib.util.spec_from_file_location('extrusion_input', Path(__file__).parents[1] / 'addon/air_modeler/extrusion_input.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


@pytest.mark.parametrize('hz', [24, 30, 60, 120])
def test_stable_direction_requires_time_and_survives_one_direction_spike(hz):
    window = control.DirectionWindow()
    for i in range(round(hz * .4)):
        delta = (0, .03) if i == round(hz * .2) else (.03, 0)
        result = window.update(i / hz, delta)
        if i / hz < .08:
            assert not window.ready
    assert window.ready and result == (.03, 0)
    assert len(window.samples) <= 24


def test_reversal_must_replace_window_and_zero_never_arms():
    window = control.DirectionWindow()
    for i in range(10):
        window.update(i / 30, (.03, 0))
    assert window.ready
    window.update(10 / 30, (-.03, 0))
    window.update(11 / 30, (-.03, 0))
    assert not window.ready
    for i in range(12, 17):
        result = window.update(i / 30, (-.03, 0))
    assert window.ready and result == (-.03, 0)
    for i in range(17, 24):
        window.update(i / 30, (0, 0))
    assert not window.ready


def test_sparse_or_mixed_evidence_cannot_lock():
    window = control.DirectionWindow()
    for i in range(10):
        window.update(i * .2, (.03, 0))
        assert not window.ready
    window = control.DirectionWindow()
    for i in range(10):
        window.update(i / 30, (.03, 0) if i % 2 else (0, .03))
        assert not window.ready


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_and_duplicate_observations_rejected(bad):
    window = control.DirectionWindow()
    with pytest.raises(ValueError):
        window.update(bad, (0, 0))
    with pytest.raises(ValueError):
        window.update(0, (bad, 0))
    window.update(0, (.03, 0))
    with pytest.raises(ValueError):
        window.update(0, (.03, 0))


def test_signed_deadband_is_continuous_baseline_derived_and_does_not_accumulate():
    band = .036
    for raw, expected in [(0, 0), (.02, 0), (-.02, 0), (band, 0),
                          (.6, .564), (-.6, -.564), (band + 1e-7, 1e-7)]:
        for _ in range(100):
            assert control.distance(raw, band) == pytest.approx(expected)
    assert control.distance(0, band) == 0
    for raw, band in [(math.nan, .03), (.2, math.inf), (.2, -.01)]:
        with pytest.raises(ValueError):
            control.distance(raw, band)
