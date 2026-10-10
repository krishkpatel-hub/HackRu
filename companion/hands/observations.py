"""Coherent anatomical hand observations; no selection, tools, or Blender state.

The camera is mirrored exactly once before MediaPipe. Its selfie-image handedness
labels are used as anatomical identities; actual left/right labeling remains an
explicit physical acceptance check. No result-array ordering assigns identity.
"""

import math

from .engine import HandEngine
from .roles import center

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


def manipulation_features(points, aspect=1.0):
    """Return thumb/index/middle grip, 2D palm angle, aperture, and open palm.

    Angle is atan2(-dy, dx) of wrist→middle MCP in aspect-correct image units.
    Aperture is mean pairwise tip distance for 4/8/12 divided by palm size.
    Neither uses landmark z. Ring/pinky must be folded for a grip. Thumb must
    participate; index/middle may spread without being mistaken for release.
    """
    empty = dict(grip=False, angle=None, aperture=None, open_palm=False)
    if not _points_valid(points) or not math.isfinite(aspect) or aspect <= 0:
        return empty
    def p(i):
        return points[i][0] * aspect, points[i][1]
    def distance(a, b):
        return math.dist(p(a), p(b))
    def angle(a, b, c):
        x, y, z = p(a), p(b), p(c)
        u, v = (x[0]-y[0], x[1]-y[1]), (z[0]-y[0], z[1]-y[1])
        size = math.hypot(*u) * math.hypot(*v)
        if size <= 1e-8:
            return float('nan')
        return math.degrees(math.acos(max(-1, min(1, sum(a*b for a,b in zip(u,v))/size))))
    palm = max(distance(0, 9), distance(5, 17))
    orient = ((points[9][0]-points[0][0])*aspect, points[0][1]-points[9][1])
    if palm < 1e-4 or math.hypot(*orient) < palm * .25:
        return empty
    extended, folded = [], []
    for mcp in (5, 9, 13, 17):
        pip, dip, tip = mcp+1, mcp+2, mcp+3
        extended.append(angle(mcp,pip,dip) >= 135 and angle(pip,dip,tip) >= 135
                        and distance(tip,0) >= 1.05*distance(pip,0))
        folded.append(angle(mcp,pip,dip) <= 115 and distance(tip,0) <= 1.1*distance(pip,0))
    thumb = (angle(2,3,4) >= 125 and distance(4,1) >= 1.05*distance(3,1)
             and distance(4,0) >= .65*palm)
    open_palm = bool(thumb and all(extended))
    grip = bool(thumb and extended[0] and extended[1] and folded[2] and folded[3])
    aperture = sum(distance(a,b) for a,b in ((4,8),(8,12),(12,4))) / (3*palm)
    if not grip or not .03 <= aperture <= 10 or not math.isfinite(aperture):
        return dict(empty, open_palm=open_palm)
    return dict(grip=True, angle=math.atan2(orient[1],orient[0]),
                aperture=aperture, open_palm=False)


def absent_observation(event='NONE', gesture_id=None):
    return dict(valid=False, confidence=0.0, u=None, v=None, palm_u=None, palm_v=None,
                pinching=False, open=False, gesture_id=gesture_id, event=event,
                grip=False, angle=None, aperture=None, open_palm=False)


class TwoHandObservations:
    """One coherent snapshot per capture; independent cursor engines/UUID lifecycles."""

    def __init__(self, config):
        self.cfg = config
        self.identities = HandIdentities(config)
        self.engines = {identity: HandEngine(config) for identity in IDENTITIES}
        self.open_since = {identity: None for identity in IDENTITIES}
        self.frame_id = 0
        self.last_t = 0.0
        self.landmarks = {}

    def _frame(self, t, hands):
        self.frame_id += 1
        self.last_t = t
        return dict(type='hands_frame', payload=dict(frame_id=self.frame_id, t=t, hands=hands))

    def update(self, t, detections, aspect=4/3):
        protected = {identity: engine.pinching for identity, engine in self.engines.items()}
        # A wide three-finger grip/open palm need not have an active ordinary
        # pinch UUID. Keep its identity anchor locked while a left clutch could
        # require it, so an uncertain right hand cannot relocate and recover as
        # another path before Blender's required-hand timeout expires.
        protected['Right'] = protected['Right'] or protected['Left']
        accepted = self.identities.update(detections, t, protected)
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
            hands[identity] = dict(valid=True, confidence=float(score), u=uv[0], v=uv[1],
                palm_u=max(0.,min(1.,palm[0])), palm_v=max(0.,min(1.,palm[1])),
                pinching=engine.pinching, open=bool(observed_open or event == 'END'),
                gesture_id=gid, event=event, **manipulation_features(points,aspect))
        return self._frame(t, hands)

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
