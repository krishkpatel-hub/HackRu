"""Fresh-observation dwell authorization and baseline distance; not live evidence."""
import importlib.util
from pathlib import Path
import sys
import pytest
spec=importlib.util.spec_from_file_location('extrusion_input',Path(__file__).parents[1]/'addon/air_modeler/extrusion_input.py')
control=importlib.util.module_from_spec(spec);sys.modules[spec.name]=control;spec.loader.exec_module(control)


@pytest.mark.parametrize('hz',[10,15,24,30,60,120])
def test_no_lock_before_two_seconds_at_each_rate(hz):
    dwell=control.FaceDwell()
    for i in range(2*hz+1):
        t=i/hz
        assert dwell.update(t,20+t,5)==(i==2*hz)
    assert dwell.face==5 and dwell.progress==pytest.approx(2)


def test_same_face_cursor_movement_is_not_part_of_dwell_identity():
    dwell=control.FaceDwell()
    for i in range(61):
        assert dwell.update(i/30,10+i/30,7)==(i==60)


def test_face_switch_and_missing_ineligible_hits_restart():
    dwell=control.FaceDwell()
    for i in range(50):dwell.update(i/30,i/30,1)
    assert not dwell.update(50/30,50/30,2) and dwell.progress==0
    assert not dwell.update(51/30,51/30,None) and dwell.face is None
    assert not dwell.update(52/30,52/30,2) and dwell.progress==0


@pytest.mark.parametrize('cause',['capture_gap','receive_gap','duplicate','invalid','stale','timer'])
def test_interruptions_cannot_complete_nearly_finished_hover(cause):
    dwell=control.FaceDwell()
    for i in range(58):dwell.update(i/30,i/30,1)
    if cause=='capture_gap':assert not dwell.update(2.2,1.95,1)
    elif cause=='receive_gap':assert not dwell.update(1.95,2.2,1)
    elif cause=='duplicate':assert not dwell.update(1.9,2.1,1)
    elif cause in ('invalid','stale'):assert not dwell.update(1.95,1.95,1,fresh=False)
    else:
        for _ in range(20):assert not dwell.update(1.9,2.2,1)
    assert dwell.progress==0


def test_burst_replay_cannot_manufacture_receiver_elapsed_time():
    dwell=control.FaceDwell()
    for i in range(100):assert not dwell.update(i/30,i/3000,1)
    assert dwell.progress<.04


def test_reset_cannot_resume_previous_progress_and_nonfinite_is_rejected():
    dwell=control.FaceDwell()
    for i in range(58):dwell.update(i/30,i/30,1)
    dwell.reset();assert not dwell.update(1.94,1.94,1) and dwell.progress==0
    assert not dwell.update(float('nan'),2,1) and dwell.face is None


def test_signed_deadband_is_continuous_and_does_not_accumulate():
    for raw,expected in ((0,0),(.02,0),(-.02,0),(.036,0),(.6,.564),(-.6,-.564)):
        for _ in range(100):assert control.distance(raw,.036)==pytest.approx(expected)
    assert control.distance(.036+1e-7,.036)==pytest.approx(1e-7)
    for raw,band in ((float('nan'),.03),(.2,float('inf')),(.2,-.01)):
        with pytest.raises(ValueError):control.distance(raw,band)
