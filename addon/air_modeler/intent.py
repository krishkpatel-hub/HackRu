"""Right whole-hand intent only; the Blender Client owns selection and Undo."""
from dataclasses import dataclass
from collections import deque
from statistics import median
import math
try:
    from . import spatial
except ImportError:
    from shared import spatial

PROMPT = 'Move palm, twist hand, close/open hand, or pinch to extrude.'


@dataclass(frozen=True)
class IntentConfig:
    move_threshold: float = .035  # right palm normalized image displacement
    twist_threshold: float = math.radians(8)
    openness_threshold: float = .15  # absolute whole-hand openness change
    stable_openness: float = .08
    persistence: float = .15
    dominance: float = 1.35
    hysteresis: float = .75  # retain an existing candidate above this score
    evidence_window: float = .20
    shape_deadband: float = .04  # reserve developing whole-finger change before activation
    scale_wobble: float = math.radians(25)  # larger mixed rotation/shape stays ambiguous
    pinch_entry_window: float = .6
    loss_timeout: float = .5
    extrusion_sensitivity: float = 12.0
    rotation_deadband: float = math.radians(2)
    rotation_sensitivity: float = 1.0
    scale_sensitivity: float = math.log(4)  # full openness difference → 4x


CONFIG = IntentConfig()


def angle_delta(current, previous):
    return (current - previous + math.pi) % math.tau - math.pi


class Intent:
    """No selecting-hand coordinates enter the classifier.

    Right must be observed released after selection/recovery before its next
    START can arm extrusion. Isolated pinch approach suppresses other candidates;
    a fist (remaining fingers folded) never becomes an extrusion candidate.
    """
    def __init__(self, config=CONFIG):
        self.config = config
        self.reference = None
        self.last_angle = None
        self.twist = 0.
        self.candidate = self.since = None
        self.pinch_armed = False
        self.pinch_id = None
        self.pinch_start = None
        self.isolated_pending = False
        self.approach_since = None
        self.scores = {}
        self.feedback = PROMPT
        self.evidence = deque(maxlen=32)
        self.shape_changing = False
        self.shape_anchor = None
        self.shape_changed_at = None

    def update(self, t, right, *, override=None):
        cfg = self.config
        if not right['valid'] or not right['shape_valid']:
            self.__init__(cfg)
            self.feedback = right.get('shape_error') or 'Right hand absent/uncertain; selection frozen'
            return None
        if self.evidence and t <= self.evidence[-1][0]:
            self.candidate = self.since = None
            self.feedback = 'Stale intent observation; hold steady'
            return None
        if self.reference is None:
            self.reference = dict(right)
            self.shape_anchor=tuple(right['fingers']);self.shape_changed_at=t
            self.last_angle = right['angle']
            self.pinch_armed = right['open']
            self.isolated_pending = right['pinch_pending']
            self.feedback = PROMPT if self.pinch_armed else 'Release Right pinch before pinching to extrude'
            return None
        if self.isolated_pending and not right['pinch_pending'] and right['open']:
            # Opening after a reserved/held extrusion pinch is rearming, not
            # an incidental SCALE or MOVE from the pinched shape reference.
            self.reference = dict(right)
            self.shape_anchor=tuple(right['fingers']);self.shape_changed_at=t
            self.last_angle = right['angle']
            self.twist = 0.
            self.pinch_armed = True
            self.pinch_id = self.candidate = self.since = None
            self.isolated_pending = False
            self.approach_since = None
            self.evidence.clear()
            self.feedback = PROMPT
            return None
        self.isolated_pending = right['pinch_pending']
        self.twist = spatial.distance(right['orientation'],self.reference['orientation'])
        self.last_angle = right['angle']
        if max(abs(a-b) for a,b in zip(right['fingers'],self.shape_anchor))>=cfg.shape_deadband/2:
            self.shape_anchor=tuple(right['fingers']);self.shape_changed_at=t
        self.evidence.append((t,self.twist,right['openness'],tuple(right['fingers'])))
        while len(self.evidence)>1 and t-self.evidence[0][0]>cfg.evidence_window+1e-9:
            self.evidence.popleft()
        if right['open']:
            self.pinch_armed = True
            self.pinch_id = None
        elif right['event'] == 'START':
            self.pinch_id = right['gesture_id'] if self.pinch_armed and right['extrude_pose'] else None
            self.pinch_start = (right['u'],right['v']) if self.pinch_id else None
            self.pinch_armed = False
        finger_changes=[a-b for a,b in zip(right['fingers'],self.reference['fingers'])]
        whole_closure=sum(x<=-cfg.shape_deadband for x in finger_changes)>=3
        isolated_stable=sum(abs(finger_changes[i])<.12 for i in (1,2,3))>=2
        if not right['extrude_pose'] or whole_closure or not isolated_stable or right['event'] == 'CANCEL':
            self.pinch_id = None
        scores = {}
        authorized = {'SCALE', 'EXTRUDE'}
        # Reserve developing isolated pinch for EXTRUDE, even before the
        # debounced contact START. Whole-fist closure has extrude_pose=False.
        if not right['pinch_pending']:
            self.approach_since=None
        if right['pinch_pending'] and not whole_closure:
            if self.approach_since is None:self.approach_since=t
            if self.pinch_id is None and t-self.approach_since>cfg.pinch_entry_window:
                self.pinch_armed=False
                self.feedback='Pinch entry timed out; open Right and try again'
                self.scores={};self.candidate=self.since=None
                return None
            if (self.pinch_id is not None and right['pinching']
                    and right['gesture_id'] == self.pinch_id and override in (None, 'EXTRUDE')):
                scores['EXTRUDE'] = 1.
                self.feedback = 'Right extrusion pinch pending; hold briefly'
            else:
                self.feedback = 'Release Right pinch, then pinch with remaining fingers open' if not self.pinch_armed else 'Isolated pinch approaching; other motion paused'
        else:
            # Early coherent shape change reserves SCALE before its activation
            # threshold. MCP orientation can wobble during finger closure even
            # though the producer correctly excludes moving fingertips.
            changes=[a-b for a,b in zip(right['fingers'],self.reference['fingers'])]
            self.shape_changing=max(sum(x>=cfg.shape_deadband for x in changes),
                                    sum(x<=-cfg.shape_deadband for x in changes))>=3
            self.shape_changing=self.shape_changing and (abs(right['openness']-self.reference['openness'])>cfg.stable_openness
                or t-self.shape_changed_at<cfg.evidence_window)
            recent_change=max(row[2] for row in self.evidence)-min(row[2] for row in self.evidence)
            stable=(abs(right['openness']-self.reference['openness'])<=cfg.stable_openness
                    and not self.shape_changing and recent_change<=cfg.stable_openness)
            twist=median(row[1] for row in self.evidence)
            shape_delta=median(row[2] for row in self.evidence)-self.reference['openness']
            finger_delta=[median(row[3][i] for row in self.evidence)-self.reference['fingers'][i] for i in range(4)]
            coherent=max(sum(x>=cfg.stable_openness for x in finger_delta),
                         sum(x<=-cfg.stable_openness for x in finger_delta))>=3
            # Scores contain only interpretable evidence. A suppressed angular
            # measurement must not beat otherwise valid SCALE in the ranking.
            if stable or override=='ROTATE':
                authorized.add('ROTATE')
                scores['ROTATE']=twist/cfg.twist_threshold if self.twist>=cfg.twist_threshold*cfg.hysteresis else 0.
            if right['open_palm'] and self.reference['open_palm'] and stable:
                scores['MOVE']=math.dist((right['palm_u'],right['palm_v']),
                    (self.reference['palm_u'],self.reference['palm_v']))/cfg.move_threshold
                if abs(self.twist)<=cfg.twist_threshold*2:authorized.add('MOVE')
            scores['SCALE']=abs(shape_delta)/cfg.openness_threshold
            current_coherent=max(sum(x>=cfg.stable_openness for x in changes),sum(x<=-cfg.stable_openness for x in changes))>=3
            if not coherent or not current_coherent or (twist>cfg.scale_wobble and override!='SCALE'):
                authorized.discard('SCALE')
            self.feedback = 'Hold a clearer motion or use a tool override'
        self.scores = scores
        if override in ('SCALE','ROTATE'):
            authorized.add(override)
        ranked = sorted(((mode, score) for mode,score in scores.items()
                         if override is None or mode == override), key=lambda item:item[1], reverse=True)
        choice = None
        if ranked:
            mode, score = ranked[0]
            threshold = cfg.hysteresis if mode == self.candidate else 1.
            if mode in authorized and score >= threshold and (len(ranked) == 1 or score >= cfg.dominance*ranked[1][1]):
                choice = mode
        if choice != self.candidate:
            self.candidate, self.since = choice, t
        if choice is None:
            self.since = None
        else:
            self.feedback = f'{choice} pending; hold deliberate motion'
            if scores[choice] >= 1 and t-self.since >= cfg.persistence:
                return choice
        return None
