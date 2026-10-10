"""Pure motion intent scoring; the existing Blender Client owns the transaction."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class IntentConfig:
    move_threshold: float = .025
    palm_threshold: float = .035
    twist_threshold: float = math.radians(8)
    aperture_threshold: float = .12
    persistence: float = .15
    dominance: float = 1.35
    loss_timeout: float = .5
    rotation_sensitivity: float = 1.0  # world radians / measured image-plane radian


CONFIG = IntentConfig()


def angle_delta(current, previous):
    return (current - previous + math.pi) % math.tau - math.pi


class Intent:
    def __init__(self, owner_uv, config=CONFIG):
        self.config = config
        self.owner_uv = tuple(owner_uv)
        self.reset_right()
        self.candidate = None
        self.since = None
        self.scores = {}

    def reset_right(self):
        self.angle = self.last_angle = self.aperture = self.palm = None
        self.twist = 0.0

    def update(self, t, owner_uv, right, *, left_owner=True, override=None):
        cfg = self.config
        scores = {'MOVE': math.dist(owner_uv, self.owner_uv) / cfg.move_threshold}
        if left_owner and right and right['valid']:
            if right['grip']:
                if self.angle is None:
                    self.angle = self.last_angle = right['angle']
                    self.aperture = right['aperture']
                    self.twist = 0.0
                self.twist += angle_delta(right['angle'], self.last_angle)
                self.last_angle = right['angle']
                scores['ROTATE'] = abs(self.twist) / cfg.twist_threshold
                scores['SCALE'] = abs(right['aperture'] / self.aperture - 1) / cfg.aperture_threshold
            else:
                self.angle = self.last_angle = self.aperture = None
                self.twist = 0.0
            if right['open_palm']:
                uv = right['palm_u'], right['palm_v']
                if self.palm is None:
                    self.palm = uv
                scores['EXTRUDE'] = math.dist(uv, self.palm) / cfg.palm_threshold
            else:
                self.palm = None
        else:
            self.reset_right()
        self.scores = scores
        eligible = {mode: score for mode, score in scores.items() if override is None or mode == override}
        ranked = sorted(eligible.items(), key=lambda item: item[1], reverse=True)
        choice = None
        if ranked and ranked[0][1] >= 1:
            if len(ranked) == 1 or ranked[0][1] >= cfg.dominance * ranked[1][1]:
                choice = ranked[0][0]
        if choice != self.candidate:
            self.candidate, self.since = choice, t
        if choice is None:
            self.since = None
        elif self.since is not None and t - self.since >= cfg.persistence:
            return choice
        return None
