"""Fresh-observation hover timing and signed baseline deadband (no bpy)."""
from dataclasses import dataclass
import math

DEADBAND_HEIGHT = .003


@dataclass(frozen=True)
class DwellConfig:
    duration: float = 2.0
    max_gap: float = .20  # stricter targeting continuity; loss cancellation stays .5 s


DWELL_CONFIG = DwellConfig()


class FaceDwell:
    def __init__(self, config=DWELL_CONFIG):
        self.config = config
        self.last_capture = self.last_received = None
        self.reset()

    def reset(self):
        self.face = self.started_capture = self.started_received = None
        self.progress = 0.

    def update(self, capture, received, face, *, fresh=True):
        """Only call for new observations. Both clocks must cover valid dwell.

        Capture elapsed time prevents queued old frames from counting as hover;
        receiver monotonic time prevents compressed/replayed timestamps from
        manufacturing a two-second hold. Gaps reset rather than pause progress.
        """
        if (not math.isfinite(capture) or not math.isfinite(received)
                or self.last_capture is not None and capture<=self.last_capture
                or self.last_received is not None and received<self.last_received):
            self.reset()
            return False
        gap=(self.last_capture is not None and
             (capture-self.last_capture>self.config.max_gap+1e-9
              or received-self.last_received>self.config.max_gap+1e-9))
        self.last_capture,self.last_received=capture,received
        if not fresh or face is None:
            self.reset()
            return False
        if gap or face!=self.face:
            self.reset()
            self.face=face
            self.started_capture,self.started_received=capture,received
        self.progress=min(capture-self.started_capture,received-self.started_received)
        return self.progress+1e-9>=self.config.duration


def distance(raw, band):
    """Continuous symmetric deadband around original geometry, no stored deltas."""
    if not math.isfinite(raw) or not math.isfinite(band) or band<0:
        raise ValueError('Invalid extrusion distance/deadband')
    return math.copysign(max(0.,abs(raw)-band),raw)
