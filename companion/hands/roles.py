"""Conservative anatomical role tracking and selector observations; no modes/edits."""
import math


def center(points):
    return tuple(sum(points[i][j] for i in (0, 5, 9, 17)) / 4 for j in (0, 1))


def pose(points, aspect=1.0):
    def p(i):
        return (points[i][0] * aspect, points[i][1])
    def distance(a, b):
        return math.dist(p(a), p(b))
    def angle(a, b, c):
        x, y, z = p(a), p(b), p(c)
        u, v = (x[0]-y[0], x[1]-y[1]), (z[0]-y[0], z[1]-y[1])
        denom = math.hypot(*u) * math.hypot(*v)
        if denom < 1e-8:
            return float("nan")
        return math.degrees(math.acos(max(-1, min(1, sum(a*b for a,b in zip(u,v))/denom))))
    try:
        states = []
        if len(points) != 21 or not all(math.isfinite(v) for pnt in points for v in pnt):
            return 'UNKNOWN'
        for mcp in (5, 9, 13, 17):
            pip, dip, tip = mcp+1, mcp+2, mcp+3
            if angle(mcp,pip,dip) >= 160 and angle(pip,dip,tip) >= 160 and distance(tip,0) >= 1.15*distance(pip,0):
                states.append('E')
            elif angle(mcp,pip,dip) <= 110 and distance(tip,0) <= 1.1*distance(pip,0):
                states.append('F')
            else:
                states.append('?')
        return {('F',)*4:'FIST', ('E','E','F','F'):'TWO',
                ('E','E','E','F'):'THREE', ('E',)*4:'OPEN'}.get(tuple(states),'UNKNOWN')
    except (TypeError, ValueError, IndexError):
        return 'UNKNOWN'


class Roles:
    def __init__(self, manipulator='Right'):
        self.manipulator = manipulator
        self.selector = 'Left' if manipulator == 'Right' else 'Right'
        self.previous = {}
        self.candidate_since = {}
        self.last_seen = {}
        self.quarantined = False

    def update(self, detections, t, active):
        # Detections: anatomical label, confidence, 21 image-space points.
        if not active:
            for role in list(self.previous):
                if role in self.last_seen and t - self.last_seen[role] > .6:
                    self.previous.pop(role, None)
                    self.candidate_since.pop(role, None)
                    self.last_seen.pop(role, None)
        by_role = {}
        for label, score, points in detections:
            if label in ('Left','Right'):
                by_role.setdefault(label, []).append((score, points))
        candidates = {}
        for role in ('Left','Right'):
            values = by_role.get(role, [])
            if len(values) == 1 and values[0][0] >= .8:
                pts = values[0][1]
                if len(pts) == 21 and all(math.isfinite(v) for p in pts for v in p):
                    candidates[role] = pts
        if len(candidates) == 2 and math.dist(*(center(p) for p in candidates.values())) < .12:
            candidates.clear()
        # A candidate nearer the opposite previous identity is ambiguous even
        # when the detector confidently swaps labels during a crossing.
        if len(self.previous) == 2:
            for role, pts in list(candidates.items()):
                other = 'Left' if role == 'Right' else 'Right'
                if math.dist(center(pts), self.previous[other]) < math.dist(center(pts), self.previous[role]):
                    candidates.clear()
                    break
        accepted = {}
        for role in ('Left','Right'):
            pts = candidates.get(role)
            if pts is None:
                self.candidate_since.pop(role, None)
                continue
            pos = center(pts)
            previous = self.previous.get(role)
            if previous is not None and math.dist(previous, pos) > .18:
                self.candidate_since.pop(role, None)
                # Never relocate an active role; idle can acquire after a stable window.
                if not active:
                    self.previous[role] = pos
                continue
            self.previous[role] = pos
            since = self.candidate_since.setdefault(role, t)
            if t - since >= .3:
                accepted[role] = pts
                self.last_seen[role] = t
        if active and self.manipulator not in accepted:
            self.quarantined = True
        if self.quarantined:
            accepted.pop(self.manipulator, None)
            if not active:
                self.quarantined = False
                self.candidate_since.pop(self.manipulator, None)
        return accepted.get(self.manipulator), accepted.get(self.selector)
