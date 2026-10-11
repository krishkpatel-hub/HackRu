"""Synthetic whole-hand motion arbitration. No physical calibration claims."""
import importlib.util
import math
from pathlib import Path
import sys
from uuid import uuid4

spec=importlib.util.spec_from_file_location('whole_intent',Path(__file__).parents[1]/'addon/air_modeler/intent.py')
intent=importlib.util.module_from_spec(spec);sys.modules[spec.name]=intent;spec.loader.exec_module(intent)


def right(angle=0., openness=1., palm=(.5,.5), **fields):
    value=dict(valid=True,shape_valid=True,shape_error=None,angle=angle,openness=openness,
        u=.5,v=.5,palm_u=palm[0],palm_v=palm[1],open=True,pinching=False,event='NONE',gesture_id=None,
        open_palm=openness>=.72,extrude_pose=openness>=.72,pinch_pending=False)
    value.update(fields)
    value['orientation']=fields.get('orientation',[math.cos(angle/2),0.,0.,math.sin(angle/2)])
    value['fingers']=fields.get('fingers',[openness]*4)
    return value


def state(obs=None):
    value=intent.Intent();assert value.update(0,right() if obs is None else obs) is None;return value


def activate(value,obs,mode):
    assert value.update(.1,obs) is None
    assert value.update(.2,obs) is None
    assert value.update(.26,obs)==mode


def test_no_owner_position_api_static_input_never_edits():
    value=state()
    for t in (.1,.3,1.,2.): assert value.update(t,right()) is None
    assert not hasattr(value,'owner_uv')
    assert intent.PROMPT=='Move palm, twist hand, close/open hand, or pinch to extrude.'


def test_right_open_translation_move_twist_rotate_and_shape_scale():
    activate(state(),right(palm=(.57,.5)),'MOVE')
    activate(state(),right(angle=.3),'ROTATE')
    activate(state(),right(openness=.65),'SCALE')
    activate(state(right(openness=.05)),right(openness=.4),'SCALE')


def test_whole_fist_contact_is_scale_never_extrude():
    fist=right(openness=.05,open=False,pinching=True,event='START',gesture_id=str(uuid4()),extrude_pose=False)
    activate(state(),fist,'SCALE')


def test_ambiguous_motion_requires_dominance_even_with_persistence():
    value=state()
    obs=right(angle=math.radians(16),palm=(.57,.5))
    for t in (.1,.3,.6): assert value.update(t,obs) is None
    assert 'clearer motion' in value.feedback
    assert value.update(.7,right(angle=.6,palm=(.57,.5))) is None
    assert value.update(.86,right(angle=.6,palm=(.57,.5)))=='ROTATE'


def test_candidate_hysteresis_keeps_noise_but_requires_activation_threshold():
    value=state();assert value.update(.1,right(palm=(.54,.5))) is None
    assert value.update(.2,right(palm=(.529,.5))) is None
    assert value.candidate=='MOVE'
    assert value.update(.27,right(palm=(.54,.5)))=='MOVE'
    value=state();value.update(.1,right(palm=(.54,.5)))
    value.update(.2,right(palm=(.52,.5)))
    assert value.candidate is None


def pinch(**changes):
    return right(openness=.8,open=False,open_palm=False,pinching=True,
        event='START',gesture_id=str(uuid4()),pinch_pending=True,fingers=[.2,1.,1.,1.],**changes)


def test_isolated_pinch_approach_blocks_incidental_move_before_start():
    value=state()
    approaching=right(palm=(.7,.5),pinch_pending=True,open=False)
    for t in (.1,.3,.6): assert value.update(t,approaching) is None
    obs=pinch(palm=(.7,.5));assert value.update(.7,obs) is None
    held=dict(obs,event='NONE')
    assert value.update(.86,held)=='EXTRUDE'
    assert value.pinch_id==obs['gesture_id']
    assert value.pinch_start==(.5,.5)


def test_already_held_or_simultaneous_selection_pinch_requires_reopen():
    obs=pinch();value=state(obs)
    for t in (.1,.3,.6): assert value.update(t,dict(obs,event='NONE')) is None
    value.update(.7,right())
    assert value.update(.75,right()) is None  # reopening is rearm, not SCALE
    fresh=pinch();assert value.update(.8,fresh) is None
    assert value.update(.96,dict(fresh,event='NONE'))=='EXTRUDE'


def test_pinch_priority_respects_override_and_fist_cannot_arm_extrude():
    value=state();obs=pinch(palm=(.8,.5))
    assert value.update(.1,obs,override='MOVE') is None
    assert value.update(.4,dict(obs,event='NONE'),override='MOVE') is None
    value=state();fist=right(openness=0,extrude_pose=False,open=False,pinching=True,event='START',gesture_id=str(uuid4()))
    assert value.update(.1,fist,override='EXTRUDE') is None
    assert value.update(.4,dict(fist,event='NONE'),override='EXTRUDE') is None


def test_override_only_changes_arbitration_not_required_open_pose():
    value=state();both=right(angle=.2,palm=(.56,.5))
    assert value.update(.1,both,override='ROTATE') is None
    assert value.update(.26,both,override='ROTATE')=='ROTATE'
    value=state(right(openness=.5,open_palm=False))
    for t in (.1,.3,.6): assert value.update(t,right(openness=.5,open_palm=False,palm=(.8,.5)),override='MOVE') is None


def test_twist_unwrap_and_invalid_measurement_reacquisition_reset_references():
    value=state(right(angle=math.radians(179)))
    value.update(.1,right(angle=math.radians(-171)))
    assert math.isclose(value.twist,math.radians(10))
    value.update(.2,right(shape_valid=False,shape_error='Degenerate palm'))
    assert value.feedback=='Degenerate palm'
    assert value.update(.4,right(angle=.8,palm=(.7,.5))) is None
    assert value.update(.8,right(angle=.8,palm=(.7,.5))) is None


def test_slow_pinch_timeout_never_falls_through_to_move_and_reopen_rearms():
    value=state()
    approach=right(palm=(.8,.3),pinch_pending=True,open=False)
    for t in (.1,.4,.8,1.2):
        assert value.update(t,approach) is None
        assert value.candidate != 'MOVE'
    assert 'timed out' in value.feedback
    late=pinch(palm=(.8,.3))
    for t in (1.3,1.5):
        assert value.update(t,late if t==1.3 else dict(late,event='NONE')) is None
    assert value.update(1.6,right()) is None
    fresh=pinch()
    assert value.update(1.7,fresh) is None
    assert value.update(1.86,dict(fresh,event='NONE'))=='EXTRUDE'


def test_gradual_closure_with_mcp_wobble_does_not_lock_rotate_first():
    value=state()
    outputs=[]
    for t,openness in ((.1,.98),(.2,.94),(.26,.925),(.32,.8),(.4,.65),(.5,.45),(.6,.2),(.7,.05),(.8,.05)):
        outputs.append(value.update(t,right(angle=.25,openness=openness)))
    assert 'ROTATE' not in outputs, outputs
    assert 'SCALE' in outputs, outputs


def test_sustained_closure_with_incidental_rotation_still_scales():
    value=state();obs=right(angle=math.radians(14),openness=.6)
    results=[value.update(t,obs) for t in (.1,.2,.3,.4)]
    assert 'SCALE' in results and 'ROTATE' not in results


def test_single_angular_spike_before_closure_never_wins():
    value=state();results=[value.update(.1,right(angle=.4))]
    for t,openness in ((.13,.96),(.18,.9),(.24,.8),(.3,.6),(.4,.3),(.5,.05),(.6,.05)):
        results.append(value.update(t,right(angle=.08,openness=openness)))
    assert 'ROTATE' not in results and 'SCALE' in results


def test_large_rotation_and_closure_remain_ambiguous_but_overrides_work():
    value=state();obs=right(angle=.8,openness=.4)
    for t in (.1,.2,.4,.6):assert value.update(t,obs) is None
    for mode in ('SCALE','ROTATE'):
        value=state()
        assert value.update(.1,obs,override=mode) is None
        assert value.update(.3,obs,override=mode)==mode


def test_reopening_with_wobble_and_static_fist_rotation_are_distinct():
    value=state(right(openness=.1,open_palm=False))
    obs=right(openness=.6,angle=.2)
    assert value.update(.1,obs) is None
    assert value.update(.3,obs)=='SCALE'
    value=state(right(openness=.1,open_palm=False))
    activate(value,right(openness=.1,open_palm=False,angle=.3),'ROTATE')


def test_rotation_candidate_is_reset_by_early_multifinger_change():
    value=state();assert value.update(.1,right(angle=.3)) is None
    assert value.candidate=='ROTATE'
    assert value.update(.2,right(angle=.3,openness=.94)) is None
    assert value.candidate is None and value.shape_changing
    for t in (.3,.4,.5):assert value.update(t,right(angle=.3,openness=.94)) is None


def test_sparse_single_spikes_cannot_survive_the_return_to_baseline():
    for obs in (right(angle=.5),right(openness=.5)):
        value=state()
        assert value.update(.1,obs) is None
        assert value.update(.29,right()) is None
        assert value.candidate is None


def test_minor_shape_adjustment_can_settle_then_deliberate_rotation_works():
    value=state()
    for t in (.1,.2,.3,.4):
        assert value.update(t,right(openness=.94)) is None
    obs=right(openness=.94,angle=.3)
    results=[value.update(t,obs) for t in (.5,.6,.7,.8)]
    assert 'ROTATE' in results


def test_early_whole_finger_contact_is_not_an_isolated_extrusion_pinch():
    value=state()
    early=right(openness=.94,open=False,pinching=True,event='START',gesture_id=str(uuid4()),pinch_pending=True)
    for t in (.1,.2,.3):
        assert value.update(t,early if t==.1 else dict(early,event='NONE')) is None
        assert value.pinch_id is None
    closing=dict(early,event='NONE',openness=.5,fingers=[.5]*4,extrude_pose=False)
    results=[value.update(t,closing) for t in (.4,.5,.6,.7)]
    assert 'SCALE' in results and 'EXTRUDE' not in results
