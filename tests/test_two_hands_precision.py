"""Observation safety, deterministic grammar and v1 extension compatibility."""
import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest
from companion.hands.roles import Roles, pose
from companion.main import typed_event
from companion.voice.parser import parse_command
from shared.protocol import validate_event, ProtocolError

spec = importlib.util.spec_from_file_location('selection', Path(__file__).resolve().parents[1]/'addon/air_modeler/selection.py')
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


def points(x, y=.5):
    return [(x,y)] * 21


def det(x, role='Right', score=.99):
    return role, score, points(x)


def acquire(roles):
    data=[det(.2), det(.8,'Left')]
    assert roles.update(data, 0, False) == (None,None)
    return roles.update(data, .31, False)


def test_roles_use_labels_not_order_and_can_swap_configuration():
    r=Roles()
    assert acquire(r)==(points(.2),points(.8))
    assert r.update([det(.79,'Left'),det(.21)],.4,True)==(points(.21),points(.79))
    left=Roles('Left')
    assert acquire(left)==(points(.8),points(.2))


@pytest.mark.parametrize('bad', [[], [det(.2,score=.5)], [det(.2),det(.21)],
    [det(.49),det(.51,'Left')], [det(.8),det(.2,'Left')]])
def test_uncertain_active_identity_freezes_until_cancel_and_rearms(bad):
    r=Roles(); acquire(r)
    assert r.update(bad,.4,True)[0] is None
    assert r.update([det(.2),det(.8,'Left')],.5,True)[0] is None
    assert r.update([det(.2),det(.8,'Left')],1.,False)[0] is None
    r.update([det(.2),det(.8,'Left')],1.1,False)
    assert r.update([det(.2),det(.8,'Left')],1.41,False)[0]==points(.2)


def test_selector_debounce_unknown_absence_and_drag_lock():
    s=selection.Selector()
    s.observe('TWO',0,True); s.observe('TWO',.29,True)
    assert s.mode(.29)=='MOVE'
    s.observe('TWO',.31,True); assert s.mode(.31)=='ROTATE'
    s.observe('OPEN',.4,False); assert s.mode(.4)=='ROTATE'
    s.observe('UNKNOWN',.6,True); assert s.mode(.6)=='ROTATE'
    s.observe('ABSENT',.92,True); assert s.mode(.92)=='MOVE'
    s.observe('THREE',1.,True); s.observe('OPEN',1.2,True); s.observe('OPEN',1.51,True)
    assert s.mode(1.51)=='EXTRUDE'
    assert s.mode(2.2)=='MOVE'  # stale stream


def hand_pose(states):
    p=[(.5,.9)]*21
    for mcp,state in zip((5,9,13,17),states):
        x=.3+(mcp-5)*.025
        p[mcp]=(x,.7); p[mcp+1]=(x,.5)
        if state=='E':
            p[mcp+2]=(x,.3); p[mcp+3]=(x,.1)
        else:
            p[mcp+2]=(x+.03,.65); p[mcp+3]=(x+.04,.8)
    return p


@pytest.mark.parametrize('states,expected',[('FFFF','FIST'),('EEFF','TWO'),('EEEF','THREE'),('EEEE','OPEN'),('EFEF','UNKNOWN')])
def test_pose_criteria_and_ignored_thumb(states,expected):
    p=hand_pose(states)
    assert pose(p,16/9)==expected
    p[4]=(.1,.1)
    assert pose(p,16/9)==expected
    assert pose(points(float('nan')))=='UNKNOWN'
    assert pose(points(.5))=='UNKNOWN'


@pytest.mark.parametrize('phrase,mode,value,axis',[
    ('Rotate X 45 degrees.','ROTATE',45,'X'),('rotate y -45 degrees','ROTATE',-45,'Y'),
    ('Move Z -2 units.','MOVE',-2,'Z'),('Scale by 1.5.','SCALE',1.5,None),
    ('extrude 0.5 units','EXTRUDE',.5,None),('Extend .5 units.','EXTRUDE',.5,None)])
def test_numeric_commands_use_real_typed_parser_and_validator(phrase,mode,value,axis):
    event=typed_event(phrase); validate_event(event)
    assert event['payload']['mode']==mode and event['payload']['value']==value
    assert event['payload'].get('axis')==axis
    assert event['payload']['id'] != typed_event(phrase)['payload']['id']


@pytest.mark.parametrize('phrase', ['scale by 0','scale by -2','scale by 11','scale by nan',
    'scale by 1e2','scale by 1.2.3','move q 2 units','move x 101 units',
    'rotate x 361 degrees','extrude 0 units','extend -1 units','extrude 5 units',
    'please scale by 1.5','rotate x 45 degrees and undo'])
def test_numeric_rejections(phrase):
    assert parse_command(phrase) is None


def test_new_payload_validation_is_strict_and_legacy_unchanged():
    validate_event({'type':'hand_frame','payload':dict(u=None,v=None,present=False,pinching=True)})
    validate_event({'type':'selector_frame','payload':dict(pose='OPEN',manipulator='Right',selector='Left')})
    for payload in [dict(pose='SCALE',manipulator='Right',selector='Left'),dict(pose='OPEN',manipulator='Right',selector='Right')]:
        with pytest.raises(ProtocolError): validate_event({'type':'selector_frame','payload':payload})
    for value in (float('nan'),float('inf'),True):
        with pytest.raises(ProtocolError):
            validate_event({'type':'command','payload':dict(id=str(uuid4()),action='precision',mode='MOVE',axis='X',value=value)})
    assert parse_command('extend')==dict(action='set_mode',mode='EXTRUDE')


def test_numeric_transcripts_only_committed_once_and_intentional_repeat():
    import threading
    from companion.voice.transcripts import TranscriptHandler
    events=[]
    stop=threading.Event()
    h=TranscriptHandler(events.append,stop,lambda _:None)
    event=dict(text='Scale by 1.5.',words=[dict(start=1,end=2)])
    h.handle(dict(event,message_type='partial_transcript'))
    h.handle(dict(event,message_type='committed_transcript'))
    assert not events
    timestamped=dict(event,message_type='committed_transcript_with_timestamps')
    h.handle(timestamped); h.handle(timestamped)
    assert len(events)==1
    h.handle(dict(timestamped,words=[dict(start=3,end=4)]))
    assert len(events)==2 and events[0]['payload']['id']!=events[1]['payload']['id']
    stop.set(); h.handle(dict(timestamped,words=[dict(start=5,end=6)]))
    assert len(events)==2


def test_idle_identity_can_reacquire_after_crossing_timeout():
    r=Roles(); acquire(r)
    assert r.update([det(.8),det(.2,'Left')],.4,False)==(None,None)
    r.update([det(.8),det(.2,'Left')],1.,False)
    assert r.update([det(.8),det(.2,'Left')],1.31,False)==(points(.8),points(.2))


def test_unstable_valid_poses_do_not_keep_an_old_special_mode_forever():
    s=selection.Selector()
    s.observe('TWO',0,True); s.observe('TWO',.31,True)
    for n in range(8):
        s.observe('OPEN' if n%2 else 'THREE', .4+n*.1,True)
    assert s.mode(1.11)=='MOVE'


def test_still_confirmed_selector_survives_long_drag_without_changing_it():
    s=selection.Selector()
    s.observe('THREE',0,True);s.observe('THREE',.31,True)
    s.observe('THREE',2.,False)
    assert s.mode(2.)=='SCALE'
