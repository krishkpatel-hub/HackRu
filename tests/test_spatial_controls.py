"""Generated 3D skeletons verify logic, never physical camera usability."""
import math
import json
import os
import pytest
from companion.hands.articulation import measure
from companion.hands.config import HandConfig
from companion.hands.observations import TwoHandObservations
from companion.hands.recording import Recorder,replay_events
from shared import spatial as s
from shared.protocol import validate_event
from test_hand_observations import skeletal_hand
from test_intent import state,right,activate


def world(closure=0,pinch=False):
    return [(x,y,0.) for x,y in skeletal_hand(closure,pinch)]


def turn(points,axis,angle):
    c=math.cos(angle);sn=math.sin(angle)
    a=[0.,0.,0.];a[axis]=1.
    return [tuple(c*v+(1-c)*s.dot(p,a)*aa+sn*cr for v,aa,cr in zip(p,a,s.cross(a,p))) for p in points]


def measured(points):return measure(points,config=HandConfig())


@pytest.mark.parametrize('axis',range(3))
@pytest.mark.parametrize('angle',[.2,.7,math.pi/2,math.pi,3.4])
def test_open_fingers_together_tilt_sideways_knuckles_never_close(axis,angle):
    before=measured(world());after=measured(turn(world(),axis,angle))
    assert before['shape_valid'] and after['shape_valid']
    assert before['open_palm'] and after['open_palm']
    assert after['fingers']==pytest.approx(before['fingers'])
    assert s.distance(before['orientation'],after['orientation'])==pytest.approx(min(angle,2*math.pi-angle))
    v=state(right(orientation=before['orientation'],openness=before['openness'],fingers=before['fingers']))
    obs=right(orientation=after['orientation'],openness=after['openness'],fingers=after['fingers'])
    v.update(.1,obs);v.update(.3,obs)
    assert v.scores['SCALE']<1e-10 and v.candidate=='ROTATE'


def test_closure_is_independent_of_orientation_and_thumb():
    for closure in (0,.25,.5,.75,1,.75,.5,.25,0):
        p=world(closure,True)
        a=measured(p);b=measured(turn(p,1,1.4))
        assert a['shape_valid'] and b['shape_valid']
        assert a['openness']==pytest.approx(b['openness'])
        if closure==1:assert a['openness']<.25 and not a['extrude_pose'] and not a['pinch_pending']
    a=measured(world());b=measured(world(1))
    assert s.distance(a['orientation'],b['orientation'])<1e-7


def test_orientation_sign_continuity_and_degenerate_failure():
    p=world();prior=measured(p)
    for degrees in range(1,362):
        result=measure(turn(p,2,math.radians(degrees)),prior,HandConfig())
        assert s.dot(prior['orientation'],result['orientation'])>0
        prior=result
    assert not measured([(0.,0.,0.)]*21)['shape_valid']
    assert not measured(None)['shape_valid']


def test_sparse_finger_change_does_not_activate_scale():
    v=state();obs=right(openness=.5,fingers=[0,0,1,1],open_palm=False)
    for t in (.1,.3,.6):assert v.update(t,obs) is None


def test_metric_frame_jump_is_invalid_then_recovers_without_reassignment():
    model=TwoHandObservations(HandConfig(two_hands=True))
    points=skeletal_hand();t=0
    for n in range(20):
        frame=model.update(n/30,[('Right',.99,points,world())]);validate_event(frame)
    frame=model.update(20/30,[('Right',.99,points,turn(world(),1,2))])
    assert not frame['payload']['hands']['Right']['shape_valid']
    frame=model.update(21/30,[('Right',.99,points,world())])
    assert frame['payload']['hands']['Right']['shape_valid']


def test_recording_is_bounded_private_and_recomputes_deterministically(tmp_path):
    path=tmp_path/'capture.jsonl';recorder=Recorder(path,1)
    model=TwoHandObservations(HandConfig(two_hands=True))
    for n in range(35):
        detections=[('Right',.99,skeletal_hand(),world())]
        event=model.update(n/30,detections,4/3)
        recorder.write(n/30,detections,4/3,event)
    recorder.close()
    assert os.stat(path).st_mode&0o777==0o600
    with pytest.raises(FileExistsError):Recorder(path)
    a=list(replay_events(path));b=list(replay_events(path))
    assert a==b and len(a)==31
    for event in a:validate_event(event)
    assert a[-1]['payload']['hands']['Right']['shape_valid']
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    assert set(rows[1])=={'t','detections','aspect','event'}


def test_multifinger_closing_contact_cannot_lock_extrusion_early():
    from uuid import uuid4
    v=state()
    obs=right(openness=.8,open=False,pinching=True,event='START',gesture_id=str(uuid4()),pinch_pending=True,fingers=[.8]*4)
    assert v.update(.1,obs) is None
    assert v.update(.3,dict(obs,event='NONE'))=='SCALE'
    assert v.pinch_id is None


def test_closed_hand_orientation_is_valid_rotation_not_projection_scale():
    v=state(right(openness=.1,open_palm=False))
    obs=right(openness=.1,open_palm=False,orientation=[math.cos(.2),math.sin(.2),0,0])
    activate(v,obs,'ROTATE')


def test_uncompleted_pinch_window_expires_without_incidental_move():
    v=state();obs=right(open=False,pinch_pending=True,palm=(.8,.5))
    assert v.update(.1,obs) is None
    assert v.update(.8,obs) is None
    assert 'timed out' in v.feedback and not v.pinch_armed
    v.update(.9,right())
    assert v.pinch_armed
    assert v.update(1.,obs) is None and v.pinch_armed


def test_replay_stops_at_session_change_even_when_already_reconnected(tmp_path):
    from companion.hands.recording import run_replay
    path=tmp_path/'sessions.jsonl';recorder=Recorder(path)
    model=TwoHandObservations(HandConfig(two_hands=True))
    for n in range(3):
        event=model.update(n/1000,[],4/3)
        recorder.write(n/1000,[],4/3,event)
    recorder.close()
    class Stop:
        def wait(self,timeout):return False
    sessions=iter(('first','first','first','second'))
    emitted=[]
    run_replay(path,emitted.append,Stop(),lambda:next(sessions,'second'))
    assert len(emitted)==1


def test_fixed_wrist_mcp_frame_ignores_fingertip_flexion_and_camera_distance():
    baseline=measured(world())
    for closure in (0,.25,.5,.75,1,.5,0):
        points=world(closure)
        obs=measured(points)
        assert s.distance(obs['orientation'],baseline['orientation'])<1e-7
        for size in (.4,2.5):
            moved=[tuple(size*x+offset for x,offset in zip(p,(.2,-.3,.7))) for p in points]
            scaled=measured(moved)
            assert scaled['openness']==pytest.approx(obs['openness'])
            assert s.distance(scaled['orientation'],obs['orientation'])<1e-7
