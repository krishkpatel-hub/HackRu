"""Bounded observation filtering: generated noisy geometry, not camera acceptance."""
import math
import random
import statistics

import pytest

from companion.hands.articulation import invalid, measure
from companion.hands.config import HandConfig
from companion.hands.feature_filter import FeatureFilter
from companion.hands.observations import TwoHandObservations
from shared import spatial
from test_hand_observations import skeletal_hand
from test_spatial_controls import world, turn
from test_intent import intent, right


def noisy(points, rng, sigma=.002):
    return [tuple(v+rng.gauss(0,sigma) for v in p) for p in points]


def features(points):
    return measure(points,config=HandConfig())


def test_stationary_noisy_geometry_reduces_feature_jitter_without_cursor_filter():
    rng=random.Random(13);base=features(world(.3));f=FeatureFilter()
    raw=[];filtered=[]
    for n in range(360):
        value=features(noisy(world(.3),rng))
        assert value['shape_valid']
        output=f.update(n/30,value)
        if n>=30:raw.append(value);filtered.append(output)
    rms=lambda rows:math.degrees(math.sqrt(statistics.mean(spatial.distance(x['orientation'],base['orientation'])**2 for x in rows)))
    jitter=lambda rows:statistics.pstdev(x['openness'] for x in rows)
    assert rms(filtered)<rms(raw)*.8
    assert jitter(filtered)<jitter(raw)*.8
    print(f'GENERATED stationary: angular RMS {rms(raw):.4f} -> {rms(filtered):.4f} deg; openness SD {jitter(raw):.6f} -> {jitter(filtered):.6f}')


@pytest.mark.parametrize('fps',[15,30,60,120])
def test_elapsed_time_step_response_is_bounded_and_rate_independent(fps):
    f=FeatureFilter();a=features(world());b=features(turn(world(1),2,.3));f.update(0,a)
    for n in range(1,round(fps*.2)+1):out=f.update(n/fps,b)
    expected=1-math.exp(-.2/.05)
    assert spatial.distance(a['orientation'],out['orientation'])==pytest.approx(.3*expected)
    assert out['openness']==pytest.approx(a['openness']+expected*(b['openness']-a['openness']))
    # Raw pose gate cannot keep an old open-hand/fresh-pinch permission on a fist.
    assert not out['open_palm'] and not out['extrude_pose'] and not out['pinch_pending']
    for n in range(round(fps*.2)+1,2*fps):out=f.update(n/fps,b)
    assert out['openness']==pytest.approx(b['openness'])


def test_missing_stale_and_gap_reset_instead_of_blending_old_pose():
    a=features(world());b=features(world(1));f=FeatureFilter()
    f.update(0,a);assert not f.update(.03,invalid('missing'))['shape_valid']
    assert f.update(.06,b)==b
    assert f.update(.30,a)==a
    assert not f.update(.30,b)['shape_valid']
    assert f.update(.31,b)==b
    assert not f.update(float('nan'),a)['shape_valid']


def test_quaternion_sign_changes_do_not_create_rotation():
    a=features(world());f=FeatureFilter();f.update(0,a)
    for n in range(1,30):
        out=f.update(n/30,dict(a,orientation=[-v for v in a['orientation']]))
        assert spatial.distance(a['orientation'],out['orientation'])<1e-7


def test_unused_thumb_joints_can_be_partial_but_required_geometry_fails_closed():
    p=world();base=features(p)
    p[1]=None;p[2]=(float('nan'),0,0);p[3]=None
    assert features(p)==base
    for index in (0,4,5,6,7,8,9,17,20):
        broken=list(p);broken[index]=None
        assert not features(broken)['shape_valid']


def test_pipeline_filter_preserves_identical_cursor_and_identity_outputs():
    models=[TwoHandObservations(HandConfig(two_hands=True,feature_smoothing_s=tau)) for tau in (0,.05)]
    rng=random.Random(5)
    fields=('u','v','palm_u','palm_v','valid','event','pinching','open')
    for n in range(120):
        p=skeletal_hand();w=noisy(world(.2),rng)
        detections=[('Left',.99,[(x-.22,y) for x,y in p],w),('Right',.99,[(x+.12,y) for x,y in p],w)]
        if n%2:detections.reverse()
        frames=[m.update(n/30,detections)['payload']['hands'] for m in models]
        for hand in ('Left','Right'):
            assert {k:frames[0][hand][k] for k in fields}=={k:frames[1][hand][k] for k in fields}
    assert frames[0]['Left']['valid'] and frames[0]['Right']['valid']


def flexed_world(closure):
    # Constant bone lengths through the motion; linear interpolation of the old
    # planar fixture collapses its DIP bone halfway through closing.
    points=world()
    for m in (5,9,13,17):
        for j,bend in enumerate((.2,1.6,2.8),1):
            x,y,z=points[m+j-1]
            points[m+j]=(x,y-.15*math.cos(closure*bend),z-.15*math.sin(closure*bend))
    return points


def recognize(kind,tau,fps=30):
    rng=random.Random(42);f=FeatureFilter(tau);recognizer=intent.Intent()
    result=None;trigger=None
    for n in range(4*fps):
        t=n/fps;motion=max(0.,min(1.,(t-1)/.4))
        close=.8*motion if kind=='SCALE' else 0
        angle=(.10 if kind=='SCALE' else .50)*motion if kind!='STILL' else 0
        value=features(noisy(turn(flexed_world(close),2,angle),rng,.0015))
        assert value['shape_valid']
        value=f.update(t,value)
        obs=right(**value)
        candidate=recognizer.update(t,obs)
        if candidate and result is None:result,trigger=candidate,t-1
    return result,trigger


@pytest.mark.parametrize('kind',['STILL','SCALE','ROTATE'])
def test_noisy_deliberate_motion_stays_distinct_without_long_activation_delay(kind):
    before=recognize(kind,0);after=recognize(kind,.05)
    if kind=='STILL':assert before==after==(None,None)
    else:
        assert before[0]==after[0]==kind
        assert after[1]<.8 and after[1]<=before[1]+.15
    print(f'GENERATED recognition {kind}: unfiltered={before}, filtered={after}')


@pytest.mark.parametrize('field,value',[('feature_smoothing_s',-.1),('feature_smoothing_s',float('nan')),('feature_max_gap_s',0),('feature_max_gap_s',.6)])
def test_filter_configuration_rejects_unbounded_values(field,value):
    with pytest.raises(ValueError):HandConfig.from_mapping({field:value})
