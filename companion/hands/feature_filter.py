"""One elapsed-time filter for articulation/orientation; never filters the cursor.

Raw geometry validity and orientation-jump rejection run before this filter.
Missing/unreliable observations clear its state; recovery starts at the raw pose.
"""
import math
from shared import spatial
from .articulation import invalid


class FeatureFilter:
    def __init__(self, tau=.05, max_gap=.20):
        self.tau,self.max_gap=tau,max_gap
        self.reset()

    def reset(self):
        self.t=self.orientation=self.fingers=None

    def update(self,t,features):
        if not features['shape_valid']:
            self.reset()
            return features
        if not math.isfinite(t) or self.t is not None and t<=self.t:
            self.reset()
            return invalid('Stale articulation observation')
        q=tuple(features['orientation']);fingers=tuple(features['fingers'])
        dt=t-self.t if self.t is not None else None
        if dt is not None and dt<=self.max_gap and self.tau>0:
            alpha=-math.expm1(-dt/self.tau)
            dot=spatial.dot(self.orientation,q)
            if dot<0:q=tuple(-v for v in q);dot=-dot
            angle=math.acos(min(1.,max(-1.,dot)))
            if angle<1e-6:
                q=spatial.unit(tuple((1-alpha)*a+alpha*b for a,b in zip(self.orientation,q)))
            else:
                q=tuple((math.sin((1-alpha)*angle)*a+math.sin(alpha*angle)*b)/math.sin(angle)
                        for a,b in zip(self.orientation,q))
            fingers=tuple(a+alpha*(b-a) for a,b in zip(self.fingers,fingers))
        self.t,self.orientation,self.fingers=t,q,fingers
        # Pose gates are raw/hysteretic so a real fist cannot inherit an old
        # filtered open-hand permission to extrude. Filtered values drive motion.
        return dict(features,orientation=list(q),fingers=list(fingers),openness=sum(fingers)/4)
