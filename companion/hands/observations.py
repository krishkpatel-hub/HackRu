"""Coherent anatomical hand observations; no selection, tools, or Blender state.

The camera is mirrored exactly once before MediaPipe. Its selfie-image handedness
labels are used as anatomical identities; actual left/right labeling remains an
explicit physical acceptance check. No result-array ordering assigns identity.
"""

import math

from .engine import HandEngine
from .roles import center
from .articulation import measure, invalid
from shared import spatial

IDENTITIES = ("Left", "Right")


def _points_valid(points):
    try:
        return len(points) == 21 and all(len(p) == 2 and all(
            type(v) in (int, float) and math.isfinite(v) for v in p) for p in points)
    except (TypeError, ValueError):
        return False


class HandIdentities:
    """Independent confidence/continuity gates, with conservative crossing rejection.

    Missing or uncertain one-hand detections invalidate only that identity. Two
    close hands or labels inconsistent with both previous paths invalidate both.
    Anchors never relocate during an active pinch. Stable reacquisition is quicker
    than first acquisition and cannot transfer a still-active gesture to a new path.
    """

    def __init__(self, config):
        self.cfg = config
        self.previous = {}
        self.last_seen = {}
        self.candidate_since = {}
        self.established = set()
        self.last_accepted = set()

    def update(self, detections, t, active):
        for identity in tuple(self.previous):
            if not active.get(identity, False) and t - self.last_seen.get(identity, t) > .6:
                self.previous.pop(identity, None)
                self.candidate_since.pop(identity, None)
                self.last_seen.pop(identity, None)
                self.established.discard(identity)
        grouped = {identity: [] for identity in IDENTITIES}
        for detection in detections:
            try:
                label, score, points = detection
                if label in grouped:
                    grouped[label].append((score, points))
            except (TypeError, ValueError):
                continue
        candidates = {}
        for identity, entries in grouped.items():
            if len(entries) != 1:
                continue
            score, points = entries[0]
            if (type(score) in (int, float) and math.isfinite(score)
                    and self.cfg.identity_confidence <= score <= 1 and _points_valid(points)):
                candidates[identity] = (score, points)
        if len(candidates) == 2 and math.dist(*(
                center(entry[1]) for entry in candidates.values())) < self.cfg.identity_separation:
            candidates.clear()
        if len(self.previous) == 2:
            for identity, (_, points) in candidates.items():
                other = 'Right' if identity == 'Left' else 'Left'
                pos = center(points)
                if math.dist(pos, self.previous[other]) + .03 < math.dist(pos, self.previous[identity]):
                    candidates.clear()
                    break
        accepted = {}
        for identity in IDENTITIES:
            value = candidates.get(identity)
            if value is None:
                self.candidate_since.pop(identity, None)
                continue
            score, points = value
            pos = center(points)
            previous = self.previous.get(identity)
            if previous is not None and math.dist(previous, pos) > self.cfg.identity_max_step:
                self.candidate_since.pop(identity, None)
                if not active.get(identity, False):
                    self.previous[identity] = pos
                    self.established.discard(identity)
                continue
            self.previous[identity] = pos
            if identity in self.last_accepted:
                ready = True
            else:
                since = self.candidate_since.setdefault(identity, t)
                delay = (self.cfg.identity_recover_s if identity in self.established
                         else self.cfg.identity_acquire_s)
                ready = t - since >= delay
            if ready:
                accepted[identity] = (score, points)
                self.last_seen[identity] = t
                self.established.add(identity)
        self.last_accepted = set(accepted)
        return accepted


def manipulation_features(points, aspect=1.0, previous=None, config=None):
    """Historical 0.8 measurement fixture helper; NOT used by live observations.

    Whole-finger flexion and palm twist, invariant to image-plane scale/rotation.

    Each of index/middle/ring/pinky contributes PIP/DIP flexion and tip reach
    normalized by palm size. This is not the old three-tip aperture. A fist is
    a valid low-openness shape. No landmark z is used as camera depth.
    """
    from .config import HandConfig
    cfg = config or HandConfig()
    previous = previous or {}
    empty = dict(shape_valid=False, shape_error='Degenerate whole-hand landmarks',
                 angle=None, openness=None, open_palm=False,
                 extrude_pose=False, pinch_pending=False)
    if not _points_valid(points) or not math.isfinite(aspect) or aspect <= 0:
        return empty
    def p(i):
        return points[i][0]*aspect, points[i][1]
    def distance(a,b):
        return math.dist(p(a),p(b))
    def angle(a,b,c):
        x,y,z = p(a),p(b),p(c)
        u,v = (x[0]-y[0],x[1]-y[1]),(z[0]-y[0],z[1]-y[1])
        length = math.hypot(*u)*math.hypot(*v)
        if length <= 1e-10:
            return float('nan')
        return math.degrees(math.acos(max(-1,min(1,sum(a*b for a,b in zip(u,v))/length))))
    def clamp(value):
        return max(0.,min(1.,value))
    palm = max(distance(0,9),distance(5,17))
    orient = ((points[9][0]-points[0][0])*aspect,points[0][1]-points[9][1])
    if palm < 1e-4 or math.hypot(*orient) < .25*palm:
        return empty
    fingers = []
    for mcp in (5,9,13,17):
        angles = angle(mcp,mcp+1,mcp+2),angle(mcp+1,mcp+2,mcp+3)
        if not all(math.isfinite(value) for value in angles):
            return empty
        bend = min(angles)
        flexion = clamp((bend-50)/110)
        reach = clamp((distance(mcp,mcp+3)/palm-.15)/1.2)
        fingers.append(.7*flexion+.3*reach)
    thumb_angle = angle(2,3,4)
    if not math.isfinite(thumb_angle):
        return empty
    open_cutoff = cfg.finger_open_exit if previous.get('open_palm') else cfg.finger_open_enter
    thumb_open = thumb_angle >= (115 if previous.get('open_palm') else 125) and distance(4,0) >= .65*palm
    open_palm = thumb_open and min(fingers) >= open_cutoff
    extrude_cutoff = cfg.finger_open_exit if previous.get('extrude_pose') else cfg.finger_open_enter
    extrude_pose = sorted(fingers[1:],reverse=True)[1] >= extrude_cutoff
    ratio = distance(4,8)/palm
    return dict(shape_valid=True, shape_error=None,
                angle=math.atan2(orient[1],orient[0]), openness=sum(fingers)/4,
                open_palm=bool(open_palm), extrude_pose=bool(extrude_pose),
                pinch_pending=bool(extrude_pose and ratio <= cfg.pinch_approach))


def absent_observation(event='NONE', gesture_id=None):
    return dict(valid=False, confidence=0.0, u=None, v=None, palm_u=None, palm_v=None,
                pinching=False, open=False, gesture_id=gesture_id, event=event,
                shape_valid=False, shape_error='Hand absent or identity uncertain',
                angle=None, openness=None, open_palm=False,
                extrude_pose=False, pinch_pending=False, orientation=None, fingers=None)


class TwoHandObservations:
    """One coherent snapshot per capture; independent cursor engines/UUID lifecycles."""

    def __init__(self, config):
        self.cfg = config
        self.identities = HandIdentities(config)
        self.engines = {identity: HandEngine(config) for identity in IDENTITIES}
        self.open_since = {identity: None for identity in IDENTITIES}
        self.shapes = {identity: {} for identity in IDENTITIES}
        self.measurements = {}
        self.frame_id = 0
        self.last_t = 0.0
        self.landmarks = {}

    def _frame(self, t, hands, aspect=4/3):
        self.frame_id += 1
        self.last_t = t
        return dict(type='hands_frame', payload=dict(profile='left_clutch_v3', frame_id=self.frame_id, t=t, aspect=aspect, hands=hands))

    def update(self, t, detections, aspect=4/3):
        protected = {identity: engine.pinching for identity, engine in self.engines.items()}
        # A whole-hand controller need not have an active ordinary
        # pinch UUID. Keep its identity anchor locked while a left clutch could
        # require it, so an uncertain right hand cannot relocate and recover as
        # another path before Blender's required-hand timeout expires.
        protected['Right'] = protected['Right'] or protected['Left']
        # Preserve the existing 2D cursor/identity input, associate metric landmarks
        # by the same unique label (never by array order after acceptance).
        planar=[tuple(d[:3]) for d in detections]
        worlds={d[0]: d[3] for d in detections if len(d)==4}
        accepted = self.identities.update(planar, t, protected)
        self.landmarks = {identity: value[1] for identity,value in accepted.items()}
        hands = {}
        for identity, engine in self.engines.items():
            score, points = accepted.get(identity, (0.0, None))
            events = engine.update(t, points, aspect)
            transitions = [event for event in events if event['type'].startswith('gesture_')]
            transition = transitions[-1] if transitions else None
            event = transition['type'].removeprefix('gesture_').upper() if transition else 'NONE'
            valid = engine.present and points is not None
            gid = transition['payload']['gesture_id'] if transition else engine.gesture_id
            if not valid:
                self.open_since[identity] = None
                self.shapes[identity] = {}
                hands[identity] = absent_observation(event, gid if event == 'CANCEL' else None)
                continue
            if engine.ratio >= self.cfg.pinch_release:
                if self.open_since[identity] is None:
                    self.open_since[identity] = t
            else:
                self.open_since[identity] = None
            since = self.open_since[identity]
            observed_open = (not engine.pinching and since is not None
                             and t-since >= self.cfg.pinch_stable_ms/1000)
            uv = (transition['payload']['u'],transition['payload']['v']) if event == 'END' else engine.cursor
            palm = engine._smooth_palm
            features = measure(worlds.get(identity),self.shapes[identity],self.cfg)
            last=self.measurements.get(identity)
            if features['shape_valid'] and last and 0 < t-last[0] <= .5:
                if spatial.distance(features['orientation'],last[1]) > min(math.radians(55), math.radians(12+900*(t-last[0]))):
                    features=invalid('Implausible palm orientation jump; hold steady')
            if features['shape_valid']:
                self.measurements[identity]=(t,features['orientation'])
            self.shapes[identity] = features
            hands[identity] = dict(valid=True, confidence=float(score), u=uv[0], v=uv[1],
                palm_u=max(0.,min(1.,palm[0])), palm_v=max(0.,min(1.,palm[1])),
                pinching=engine.pinching, open=bool(observed_open or event == 'END'),
                gesture_id=gid, event=event, **features)
        return self._frame(t, hands, aspect)

    def shutdown(self):
        hands = {}
        active = False
        for identity, engine in self.engines.items():
            events = engine.shutdown()
            if events:
                active = True
                hands[identity] = absent_observation('CANCEL',events[0]['payload']['gesture_id'])
            else:
                hands[identity] = absent_observation()
        return self._frame(self.last_t + 1e-6, hands) if active else None
