"""Synthetic landmark sequences for coherent identity/cursor/pose observations.

The existing real_still_pinch.json regression remains genuine recorded evidence;
all skeletons generated in this file are synthetic and prove no physical demo.
"""
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent / 'test_hands_fixtures'))
import make_fixtures as mf

from companion.hands.config import HandConfig
from companion.hands.observations import HandIdentities, TwoHandObservations, manipulation_features
from shared.protocol import validate_event


def cursor_hand(u=.25, ratio=.9, drop=0.):
    tiny = mf.hand(u,.4,ratio,tip_dropout=drop)
    return [tuple(tiny.get(str(i),(u,.4))) for i in range(21)]


def detection(identity, u=.25, ratio=.9, score=.99, drop=0.):
    return identity, score, cursor_hand(u,ratio,drop)


class Sequence:
    def __init__(self):
        self.model = TwoHandObservations(HandConfig(two_hands=True,smoothing=0))
        self.n = 0
        self.events = []

    def frames(self, count, detections):
        events = []
        for _ in range(count):
            event = self.model.update(self.n/30, detections, mf.ASPECT)
            validate_event(event)
            self.n += 1
            self.events.append(event)
            events.append(event)
        return events

    def hand(self, identity):
        return self.events[-1]['payload']['hands'][identity]


@pytest.mark.parametrize('owner',['Left','Right'])
def test_each_hand_corrected_aim_palm_motion_frozen_release(owner):
    s = Sequence()
    s.frames(25,[detection(owner)])
    # Closing the fingertips alone must keep the pre-close cursor.
    s.frames(10,[detection(owner,ratio=.15,drop=.16)])
    start = next(event['payload']['hands'][owner] for event in s.events
                 if event['payload']['hands'][owner]['event']=='START')
    assert (start['u'],start['v']) == pytest.approx((.25,.4))
    gid = start['gesture_id']
    s.frames(6,[detection(owner,u=.35,ratio=.15,drop=.16)])
    assert s.hand(owner)['u'] == pytest.approx(.35)
    # Opening plus incidental palm movement must not change final output.
    s.frames(5,[detection(owner,u=.4,ratio=.9,drop=0)])
    end = next(event['payload']['hands'][owner] for event in s.events
               if event['payload']['hands'][owner]['event']=='END')
    assert (end['u'],end['v']) == pytest.approx((.35,.4))
    assert end['gesture_id']==gid and end['open'] and not end['pinching']


def test_simultaneous_pinches_have_independent_ids_in_one_frame():
    s=Sequence()
    s.frames(25,[detection('Left'),detection('Right',.75)])
    events=s.frames(10,[detection('Right',.75,.15),detection('Left',.25,.15)])
    starts=[event for event in events if event['payload']['hands']['Left']['event']=='START']
    assert len(starts)==1
    hands=starts[0]['payload']['hands']
    assert hands['Right']['event']=='START'
    assert hands['Left']['gesture_id'] != hands['Right']['gesture_id']
    assert all(event['payload']['frame_id']==i+1 for i,event in enumerate(s.events))


def test_unrelated_hand_loss_does_not_interrupt_owner():
    s=Sequence()
    s.frames(25,[detection('Left'),detection('Right',.75)])
    s.frames(10,[detection('Left',ratio=.15),detection('Right',.75)])
    gid=s.hand('Left')['gesture_id']
    events=s.frames(25,[detection('Left',.3,.15)])
    assert all(event['payload']['hands']['Left']['valid'] for event in events)
    assert all(event['payload']['hands']['Left']['event']=='NONE' for event in events)
    assert s.hand('Left')['gesture_id']==gid
    assert not s.hand('Right')['valid']


def test_short_loss_freezes_and_reacquires_without_jump():
    s=Sequence()
    s.frames(25,[detection('Left')])
    s.frames(10,[detection('Left',ratio=.15)])
    gid=s.hand('Left')['gesture_id']
    s.frames(3,[])
    assert s.hand('Left')['u'] is None and not s.hand('Left')['open']
    events=s.frames(5,[detection('Left',.35,.15)])
    recovered=next(event['payload']['hands']['Left'] for event in events
                   if event['payload']['hands']['Left']['valid'])
    assert recovered['u']==pytest.approx(.25)
    assert recovered['gesture_id']==gid
    s.frames(3,[detection('Left',.38,.15)])
    assert s.hand('Left')['u']==pytest.approx(.28)


def test_sustained_loss_cancels_once_and_pinched_return_needs_observed_open():
    s=Sequence()
    s.frames(25,[detection('Right',.75)])
    s.frames(10,[detection('Right',.75,.15)])
    gid=s.hand('Right')['gesture_id']
    events=s.frames(25,[])
    cancels=[event['payload']['hands']['Right'] for event in events
             if event['payload']['hands']['Right']['event']=='CANCEL']
    assert len(cancels)==1 and cancels[0]['gesture_id']==gid
    assert not any(event['payload']['hands']['Right']['open'] for event in events)
    s.frames(25,[detection('Right',.75,.15)])
    assert not s.hand('Right')['pinching'] and not s.hand('Right')['open']
    s.frames(6,[detection('Right',.75)])
    assert s.hand('Right')['open']
    s.frames(6,[detection('Right',.75,.15)])
    assert s.hand('Right')['pinching'] and s.hand('Right')['gesture_id'] != gid


def test_crossing_confident_label_swap_cannot_transfer_owner():
    s=Sequence()
    s.frames(25,[detection('Left'),detection('Right',.75)])
    s.frames(10,[detection('Left',ratio=.15),detection('Right',.75)])
    events=s.frames(20,[detection('Left',.75,.15),detection('Right',.25)])
    assert all(not h['valid'] for event in events for h in event['payload']['hands'].values())
    assert len([event for event in events if event['payload']['hands']['Left']['event']=='CANCEL'])==1
    assert not any(event['payload']['hands']['Right']['event']=='START' for event in events)


def test_duplicate_or_low_confidence_identity_does_not_poison_other_hand():
    s=Sequence()
    s.frames(25,[detection('Left'),detection('Right',.75)])
    event=s.frames(1,[detection('Left'),detection('Right',.75),detection('Right',.8)])[0]
    assert event['payload']['hands']['Left']['valid']
    assert not event['payload']['hands']['Right']['valid']
    event=s.frames(1,[detection('Left'),detection('Right',.75,score=.6)])[0]
    assert event['payload']['hands']['Left']['valid']
    assert not event['payload']['hands']['Right']['valid']


def skeletal_grip(aperture=1., open_palm=False):
    """Synthetic palm-facing skeleton, thumb/index/middle participating."""
    p=[(.5,.8)]*21
    p[1]=(.4,.72);p[2]=(.33,.63);p[3]=(.26,.54);p[4]=(.19,.45)
    for mcp,x in ((5,.42),(9,.5),(13,.58),(17,.66)):
        p[mcp]=(x,.6)
        if mcp in (5,9) or open_palm:
            p[mcp+1]=(x,.45);p[mcp+2]=(x,.3);p[mcp+3]=(x,.15)
        else:
            p[mcp+1]=(x,.46);p[mcp+2]=(x+.02,.62);p[mcp+3]=(x+.02,.72)
    # Scale the three tip spread about their mean; interpolate their joints.
    tips=(4,8,12)
    c=tuple(sum(p[i][axis] for i in tips)/3 for axis in (0,1))
    for base,tip in ((1,4),(5,8),(9,12)):
        end=tuple(c[a]+(p[tip][a]-c[a])*aperture for a in (0,1))
        start=p[base]
        for j in (1,2,3):
            p[base+j]=tuple(start[a]+(end[a]-start[a])*j/3 for a in (0,1))
    return p


def rotate(points,radians):
    c,s=math.cos(radians),math.sin(radians)
    return [(.5+c*(x-.5)-s*(y-.5),.5+s*(x-.5)+c*(y-.5)) for x,y in points]


def test_grip_spread_changes_aperture_without_changing_orientation_or_pose():
    narrow=manipulation_features(skeletal_grip(.65))
    wide=manipulation_features(skeletal_grip(1.35))
    assert narrow['grip'] and wide['grip']
    assert not narrow['open_palm'] and not wide['open_palm']
    assert wide['angle']==pytest.approx(narrow['angle'])
    assert wide['aperture']/narrow['aperture']==pytest.approx(1.35/.65)


def test_twist_changes_orientation_without_changing_normalized_aperture():
    points=skeletal_grip()
    before=manipulation_features(points)
    after=manipulation_features(rotate(points,.6))
    assert before['grip'] and after['grip']
    assert after['angle']-before['angle']==pytest.approx(-.6)
    assert after['aperture']==pytest.approx(before['aperture'])


def test_thumb_required_ring_not_substituted_and_open_palm_distinct():
    p=skeletal_grip()
    p[4]=p[1]  # tucked thumb cannot be accepted as a three-finger grip
    assert not manipulation_features(p)['grip']
    full=skeletal_grip(open_palm=True)
    assert manipulation_features(full)['open_palm'] and not manipulation_features(full)['grip']
    for i in (13,14,15,16):
        p[i]=full[i]
    assert not manipulation_features(p)['grip']
    assert not manipulation_features([(.5,.5)]*21)['grip']


def test_aperture_can_cross_pinch_release_while_grip_and_left_clutch_remain_valid():
    s=Sequence()
    def right(spread):
        return 'Right',.99,[(x+.22,y) for x,y in skeletal_grip(spread)]
    s.frames(25,[detection('Left'),right(1.)])
    s.frames(10,[detection('Left',ratio=.15),right(.15)])
    clutch=s.hand('Left')['gesture_id']
    assert s.hand('Left')['pinching'] and s.hand('Right')['grip']
    assert s.hand('Right')['pinching']
    events=s.frames(10,[detection('Left',ratio=.15),right(1.)])
    assert any(event['payload']['hands']['Right']['event']=='END' for event in events)
    assert all(event['payload']['hands']['Right']['grip'] for event in events)
    assert all(event['payload']['hands']['Left']['gesture_id']==clutch for event in events)
    assert s.hand('Left')['pinching'] and not s.hand('Left')['open']


def test_left_clutch_protects_wide_right_grip_identity_from_relocation():
    s=Sequence()
    def right(shift):
        return 'Right',.99,[(x+shift,y) for x,y in skeletal_grip(1.)]
    s.frames(25,[detection('Left'),right(.22)])
    s.frames(10,[detection('Left',ratio=.15),right(.22)])
    assert s.hand('Right')['grip'] and not s.hand('Right')['pinching']
    # This exceeds the continuity limit but does not approach the Left path.
    # Right must not acquire the new position while Left remains clutched.
    events=s.frames(25,[detection('Left',ratio=.15),right(.42)])
    assert all(not event['payload']['hands']['Right']['valid'] for event in events)
    assert all(event['payload']['hands']['Left']['pinching'] for event in events)
    s.frames(20,[detection('Left'),right(.42)])
    assert s.hand('Right')['valid'] and s.hand('Right')['grip']


def test_shutdown_cancels_each_active_id_once():
    s=Sequence()
    s.frames(25,[detection('Left'),detection('Right',.75)])
    s.frames(10,[detection('Left',ratio=.15),detection('Right',.75,.15)])
    event=s.model.shutdown()
    validate_event(event)
    assert all(h['event']=='CANCEL' for h in event['payload']['hands'].values())
    assert s.model.shutdown() is None


@pytest.mark.parametrize('bad',[dict(identity_confidence=float('nan')),
    dict(identity_recover_s=0),dict(identity_confidence=.1),dict(two_hands=True,manipulator_hand='Left')])
def test_identity_config_rejections(bad):
    with pytest.raises(ValueError):
        HandConfig.from_mapping(bad)
