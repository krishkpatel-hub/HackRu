"""Extrusion-only scalar regression vectors; not camera acceptance evidence."""
from dataclasses import FrozenInstanceError
import importlib.util
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location(
    'air_extrusion_mapping', Path(__file__).resolve().parents[1] /
    'addon/air_modeler/extrusion_mapping.py')
mapping = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mapping
spec.loader.exec_module(mapping)


@pytest.mark.parametrize('normal', [(1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                     (0, -1, 0), (0, 0, 1), (0, 0, -1)])
def test_all_six_world_normals_have_signed_outward_and_inward_drag(normal):
    # Oblique camera basis: each cardinal face projects visibly. Opposite
    # normal signs must reverse the drag direction, never lose reachability.
    right = (2 ** -.5, -(2 ** -.5), 0)
    up = (-6 ** -.5, -6 ** -.5, (2 / 3) ** .5)
    projected = (sum(a * b for a, b in zip(normal, right)),
                 -sum(a * b for a, b in zip(normal, up)))
    control = mapping.mapping(projected, aspect=1.6)
    dx, dy = control.direction
    assert not control.fallback
    assert control.distance(dx * .1 / control.aspect, dy * .1) == pytest.approx(1.164)
    assert control.distance(-dx * .1 / control.aspect, -dy * .1) == pytest.approx(-1.164)


@pytest.mark.parametrize('aspect', [.5, 1., 2., 3.2])
@pytest.mark.parametrize('projected', [(1, 0), (0, -1), (-3, 4), (.1, -.3)])
def test_equal_pixel_travel_has_equal_gain_and_no_inverse_projection_gain(aspect, projected):
    control = mapping.mapping(projected, aspect=aspect)
    dx, dy = control.direction
    assert control.raw_distance(dx * .05 / aspect, dy * .05) == pytest.approx(.6)
    assert control.distance(dx * .05 / aspect, dy * .05) == pytest.approx(.564)
    assert control.raw_distance(-dy * .05 / aspect, dx * .05) == pytest.approx(0, abs=1e-14)
    near_edge = mapping.mapping(tuple(value * .01 for value in projected),
                               aspect=aspect, observability=.09)
    assert near_edge.distance(dx * .05 / aspect, dy * .05) == pytest.approx(.564)


@pytest.mark.parametrize('projected,observability', [((0, 0), 1), ((1e-12, 1e-12), 1),
                                                   ((1, 0), 0), ((-1, 1), .079)])
def test_near_zero_normal_projection_uses_stable_upward_outward_fallback(projected, observability):
    control = mapping.mapping(projected, observability=observability, aspect=1.8)
    assert control.fallback and control.direction == (0., -1.)
    assert 'Upward' in control.label and 'fallback' in control.label
    assert control.distance(0, -.1) == pytest.approx(1.164)
    assert control.distance(0, .1) == pytest.approx(-1.164)
    assert control.distance(.25, 0) == 0


def test_mapping_is_frozen_and_copies_mutable_projection():
    projection = [2., -1.]
    control = mapping.mapping(projection)
    expected = control.direction
    projection[:] = [-2., 1.]
    assert control.direction == expected
    with pytest.raises(FrozenInstanceError):
        control.direction = (0., -1.)
    assert not control.fallback and 'Projected normal' in control.label


def test_no_lock_jump_symmetric_deadband_original_baseline_and_raw_clamp():
    control = mapping.mapping((1, 0), aspect=2)
    assert control.raw_distance(0, 0) == control.distance(0, 0) == 0
    assert control.deadband == .003 and control.distance_band == pytest.approx(.036)
    for delta, expected in ((.003, 0), (-.003, 0), (.1, 1.164), (-.1, -1.164)):
        for _ in range(100):
            assert control.distance(delta / 2, 0) == pytest.approx(expected)
    assert control.distance((.003 + 1e-7) / 2, 0) == pytest.approx(1.2e-6)
    assert control.raw_distance(1, 0) == 4
    assert control.distance(1, 0) == pytest.approx(3.964)
    assert control.distance(-1, 0) == pytest.approx(-3.964)
    assert control.distance(.02, 0) == pytest.approx(.444)


def test_finite_virtual_references_cannot_overflow_or_create_nan():
    control = mapping.mapping((1e308, -1e308), aspect=2)
    assert control.raw_distance(1e308, -1e308) == 4
    assert control.raw_distance(-1e308, 1e308) == -4
    diagonal = mapping.mapping((1, 1))
    assert diagonal.raw_distance(1e308, -1e308) == 0


@pytest.mark.parametrize('projected', [None, 1, (), (1,), (1, 2, 3),
                                     (True, 0), (float('nan'), 0), (0, float('inf'))])
def test_invalid_normal_projection_rejected(projected):
    with pytest.raises(ValueError):
        mapping.mapping(projected)


@pytest.mark.parametrize('kwargs', [dict(aspect=0), dict(aspect=-1), dict(aspect=True),
    dict(aspect=float('inf')), dict(observability=-.1), dict(observability=1.1),
    dict(observability=float('nan')), dict(observability=True), dict(sensitivity=0),
    dict(sensitivity=False), dict(maximum=float('inf')), dict(deadband=-.001),
    dict(deadband=True), dict(deadband=float('nan')), dict(deadband=1e308, sensitivity=1e308)])
def test_invalid_mapping_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        mapping.mapping((1, 0), **kwargs)


@pytest.mark.parametrize('delta', [(float('nan'), 0), (0, float('inf')), (True, 0), (0, None)])
def test_invalid_motion_rejected(delta):
    with pytest.raises(ValueError):
        mapping.mapping((1, 0)).distance(*delta)
