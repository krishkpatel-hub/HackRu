"""Synthetic measured-observation sequences; not recorded/live hand evidence."""
import importlib.util
import math
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('air_intent', Path(__file__).parents[1]/'addon/air_modeler/intent.py')
intent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = intent
spec.loader.exec_module(intent)


def right(angle=0, aperture=1, palm=(.6,.5), grip=True, valid=True):
    return dict(valid=valid, grip=grip, angle=angle, aperture=aperture,
                open_palm=not grip, palm_u=palm[0], palm_v=palm[1])


def test_stationary_and_move_persistence():
    state=intent.Intent((.5,.5))
    assert state.update(0,(.5,.5),None) is None
    assert state.update(1,(.5,.5),None) is None
    assert state.update(2,(.54,.5),None,left_owner=False) is None
    assert state.update(2.16,(.54,.5),None,left_owner=False)=='MOVE'


def test_twist_only_scale_only_ambiguity_and_override():
    for mode, obs in [('ROTATE',right(.2)),('SCALE',right(aperture=1.2))]:
        state=intent.Intent((.5,.5))
        state.update(0,(.5,.5),right())
        assert state.update(.1,(.5,.5),obs) is None
        assert state.update(.26,(.5,.5),obs)==mode
    state=intent.Intent((.5,.5));state.update(0,(.5,.5),right())
    both=right(math.radians(16),1.24)
    assert state.update(.1,(.5,.5),both) is None
    assert state.update(1,(.5,.5),both) is None
    assert state.update(2,(.5,.5),both,override='SCALE') is None
    assert state.update(2.16,(.5,.5),both,override='SCALE')=='SCALE'


def test_unwrap_and_pose_loss_reset():
    state=intent.Intent((.5,.5));state.update(0,(.5,.5),right(math.radians(179)))
    state.update(.1,(.5,.5),right(math.radians(-171)))
    assert math.isclose(state.twist,math.radians(10))
    state.update(.2,(.5,.5),right(valid=False))
    assert state.update(.4,(.5,.5),right(.5)) is None
    assert state.update(.7,(.5,.5),right(.5)) is None


def test_open_palm_and_competing_owner_motion():
    state=intent.Intent((.5,.5));state.update(0,(.5,.5),right(grip=False))
    obs=right(palm=(.67,.5),grip=False)
    assert state.update(.1,(.55,.5),obs) is None  # equal normalized intent
    assert state.update(.4,(.55,.5),obs) is None
    assert state.update(.5,(.5,.5),obs) is None
    assert state.update(.66,(.5,.5),obs)=='EXTRUDE'
