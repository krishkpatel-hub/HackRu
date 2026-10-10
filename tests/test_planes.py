"""Synthetic screen-displacement vectors, not physical camera evidence."""
import importlib.util
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location('air_planes', Path(__file__).resolve().parents[1] / 'addon/air_modeler/planes.py')
planes = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = planes
spec.loader.exec_module(planes)


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_plane_cardinal_controls_reach_both_signs_of_each_axis(plane):
    m = planes.mapping((1, 0, 0), plane=plane)
    vectors = [m.displacement(.25, 0), m.displacement(-.25, 0),
               m.displacement(0, .25), m.displacement(0, -.25)]
    expected = [tuple(sign*x for x in planes.AXES[axis]) for axis in plane for sign in (-1, 1)]
    assert set(vectors) == set(expected)
    assert m.displacement(.2, -.1) == tuple(-x for x in m.displacement(-.2, .1))


def test_auto_uses_face_and_viewport_with_deterministic_ties():
    assert planes.mapping((1, 0, 0)).plane == 'XY'
    assert planes.mapping((0, 1, 0)).plane == 'XY'
    assert planes.mapping((0, 0, -1)).plane == 'XZ'
    assert planes.mapping((1, 0, 0), view_right=(0, 0, -1), view_up=(1, 0, 0)).plane == 'XZ'
    assert planes.mapping((1, 0, 0), axis='Z').plane == 'XZ'
    assert planes.mapping((0, 0, 1), axis='Y').plane == 'YZ'


def test_viewport_projection_assigns_signs_and_swaps_controls():
    m = planes.mapping((0, 1, 0), (0, -1, 0), (0, 0, 1), plane='YZ')
    assert m.horizontal == (0, -1, 0)
    assert m.vertical == (0, 0, 1)
    assert m.displacement(.25, -.5) == (0, -1, 2)
    m = planes.mapping((0, 1, 0), (0, 0, 1), (0, -1, 0), plane='YZ')
    assert m.horizontal == (0, 0, 1)
    assert m.vertical == (0, -1, 0)


def test_edge_on_plane_remains_bounded_and_exact_not_inverse_projection():
    m = planes.mapping((0, 0, 1), plane='XZ')
    assert m.displacement(.25, -.25) == (1, 0, 1)
    assert sum(x*x for x in m.displacement(1, -1)) == pytest.approx(16)
    assert m.displacement(0, 0) == (0, 0, 0)


@pytest.mark.parametrize('plane,axis', [('XY', 'X'), ('XY', 'Y'), ('XZ', 'Z'), ('YZ', 'Y')])
def test_axis_constraint_suppresses_other_plane_component(plane, axis):
    m = planes.mapping((1, 0, 0), plane=plane, axis=axis)
    vector = m.displacement(.25, -.25)
    assert vector == planes.AXES[axis]


@pytest.mark.parametrize('kwargs', [dict(plane='XY', axis='Z'), dict(plane='XYZ'), dict(axis='x'),
    dict(sensitivity=0), dict(sensitivity=True), dict(maximum=float('inf')),
    dict(view_right=(0, 0, 0)), dict(view_up=(1, 0, 0)), dict(view_up=(0, float('nan'), 0))])
def test_invalid_mapping_references_or_settings_rejected(kwargs):
    with pytest.raises(ValueError): planes.mapping((1, 0, 0), **kwargs)


@pytest.mark.parametrize('delta', [(float('nan'), 0), (0, float('inf')), (True, 0)])
def test_invalid_motion_rejected(delta):
    with pytest.raises(ValueError): planes.mapping((1, 0, 0)).displacement(*delta)


def test_short_loss_virtual_reference_can_continue_then_reverse_at_bound():
    m = planes.mapping((1, 0, 0), plane='XZ', axis='X')
    accepted_delta = .8
    recovered_palm = .05
    virtual_reference = recovered_palm - accepted_delta
    assert m.displacement(recovered_palm - virtual_reference, 0) == pytest.approx((3.2, 0, 0))
    assert m.displacement(.75 - virtual_reference, 0) == pytest.approx((4, 0, 0))
    assert m.displacement(0 - virtual_reference, 0) == pytest.approx((3, 0, 0))


def test_huge_finite_delta_clamps_without_nan_or_losing_direction():
    m = planes.mapping((1, 0, 0), plane='XY')
    assert m.displacement(1e308, -1e308) == pytest.approx((8**.5, 8**.5, 0))
    assert m.displacement(-1e308, 0) == (-4, 0, 0)
