"""Extrusion-only evidence window and baseline deadband; no gesture ownership.

The producer already smooths corrected palm motion once. Only face recognition
uses a short median window; continuous deformation never receives another EMA.
"""
from collections import deque
import math
from statistics import median

DIRECTION_WINDOW = .12
DIRECTION_SPAN = .08
DEADBAND_HEIGHT = .003


class DirectionWindow:
    def __init__(self):
        self.samples = deque(maxlen=24)
        self.ready = False
        self.span = 0.
        self.coherence = 0.

    def update(self, t, delta):
        if not math.isfinite(t) or any(not math.isfinite(v) for v in delta):
            raise ValueError('Nonfinite extrusion direction evidence')
        if self.samples and t <= self.samples[-1][0]:
            raise ValueError('Extrusion direction timestamps must increase')
        self.samples.append((t,tuple(delta)))
        while len(self.samples)>1 and t-self.samples[0][0]>DIRECTION_WINDOW+1e-9:
            self.samples.popleft()
        value=tuple(median(sample[1][i] for sample in self.samples) for i in (0,1))
        length=math.hypot(*value)
        aligned=0
        for _,point in self.samples:
            size=math.hypot(*point)
            if length>1e-9 and size>1e-9 and sum(a*b for a,b in zip(value,point))/(length*size)>=math.cos(math.radians(15)):
                aligned+=1
        self.span=t-self.samples[0][0]
        self.coherence=aligned/len(self.samples)
        self.ready=len(self.samples)>=3 and self.span>=DIRECTION_SPAN-1e-9 and self.coherence>=.75
        return value


def distance(raw, band):
    """Continuous symmetric deadband around original geometry, no stored deltas."""
    if not math.isfinite(raw) or not math.isfinite(band) or band<0:
        raise ValueError('Invalid extrusion distance/deadband')
    return math.copysign(max(0.,abs(raw)-band),raw)
