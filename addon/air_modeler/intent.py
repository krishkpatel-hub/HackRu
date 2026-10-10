"""Right whole-hand intent only; the Blender Client owns selection and Undo."""
from dataclasses import dataclass
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

    def update(self, t, right, *, override=None):
        cfg = self.config
        if not right['valid'] or not right['shape_valid']:
            self.__init__(cfg)
            self.feedback = right.get('shape_error') or 'Right hand absent/uncertain; selection frozen'
            return None
        if self.reference is None:
            self.reference = dict(right)
            self.last_angle = right['angle']
            self.pinch_armed = right['open']
            self.isolated_pending = right['pinch_pending']
            self.feedback = PROMPT if self.pinch_armed else 'Release Right pinch before pinching to extrude'
            return None
        if self.isolated_pending and not right['pinch_pending'] and right['open']:
            # Opening after a reserved/held extrusion pinch is rearming, not
            # an incidental SCALE or MOVE from the pinched shape reference.
            self.reference = dict(right)
            self.last_angle = right['angle']
            self.twist = 0.
            self.pinch_armed = True
            self.pinch_id = self.candidate = self.since = None
            self.isolated_pending = False
            self.approach_since = None
            self.feedback = PROMPT
            return None
        self.isolated_pending = right['pinch_pending']
        self.twist = spatial.distance(right['orientation'],self.reference['orientation'])
        self.last_angle = right['angle']
        if right['open']:
            self.pinch_armed = True
            self.pinch_id = None
        elif right['event'] == 'START':
            self.pinch_id = right['gesture_id'] if self.pinch_armed and right['extrude_pose'] else None
            self.pinch_start = (right['u'],right['v']) if self.pinch_id else None
            self.pinch_armed = False
        finger_changes=[a-b for a,b in zip(right['fingers'],self.reference['fingers'])]
        whole_closure=sum(x<=-.08 for x in finger_changes)>=3
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
            shape_delta = right['openness'] - self.reference['openness']
            stable = abs(shape_delta) <= cfg.stable_openness
            scores['ROTATE'] = abs(self.twist) / cfg.twist_threshold
            if stable:authorized.add('ROTATE')
            if right['open_palm'] and self.reference['open_palm']:
                scores['MOVE'] = math.dist((right['palm_u'],right['palm_v']),
                    (self.reference['palm_u'],self.reference['palm_v'])) / cfg.move_threshold
                if stable:
                    authorized.add('ROTATE')
                    if abs(self.twist) <= cfg.twist_threshold * 2:
                        authorized.add('MOVE')
            changes=[a-b for a,b in zip(right['fingers'],self.reference['fingers'])]
            coherent=max(sum(x>=.08 for x in changes),sum(x<=-.08 for x in changes))>=3
            if not coherent or abs(self.twist)>cfg.twist_threshold:
                authorized.discard('SCALE')
            scores['SCALE'] = abs(shape_delta) / cfg.openness_threshold
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
