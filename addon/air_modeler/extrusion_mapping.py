"""Frozen screen-to-normal distance for unconstrained AUTO extrusion (no bpy).

The caller projects the selected face's world normal at its world center using
the actual viewport, then captures this mapping once at face lock. Pixel-space
directions use +x right and +y down, like normalized hand cursor coordinates.
Explicit plane/axis controls continue to use the existing planes module.
"""
from dataclasses import dataclass
import math


MIN_OBSERVABILITY = .08
DEADBAND_HEIGHT = .003


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


@dataclass(frozen=True)
class ScalarMapping:
    direction: tuple
    aspect: float
    observability: float
    fallback: bool
    sensitivity: float
    maximum: float
    deadband: float

    @property
    def label(self):
        return ('Upward drag = outward (fallback)' if self.fallback else
                'Projected normal drag = outward')

    @property
    def distance_band(self):
        return self.deadband * self.sensitivity

    def raw_distance(self, du, dv):
        """Bounded world distance before the original symmetric deadband.

        Horizontal motion is corrected for usable viewport width/height, so
        equal pixel travel has equal gain in every screen direction. There is
        no division by projected-normal length, hence no edge-on gain spike.
        The caller applies this scalar along the frozen world-space face normal.
        """
        if not all(_finite(value) for value in (du, dv)):
            raise ValueError('Extrusion cursor displacement must be finite')
        peak = max(abs(du), abs(dv))
        if peak == 0:
            return 0.
        weights = self.direction[0] * self.aspect, self.direction[1]
        weight_peak = max(abs(value) for value in weights)
        # Normalize both inputs and weights before taking the dot product.
        # A recovered virtual reference can exceed the camera's [0, 1] range;
        # even huge finite deltas must clamp without becoming NaN.
        projected = math.fsum((du / peak * (weights[0] / weight_peak),
                               dv / peak * (weights[1] / weight_peak)))
        if projected == 0:
            return 0.
        magnitude = abs(projected) * peak * weight_peak * self.sensitivity
        return math.copysign(min(self.maximum, magnitude), projected)

    def distance(self, du, dv):
        """Continuous signed distance; targeting motion is not accumulated.

        Preserve the existing order: clamp raw travel, then subtract the
        deadband. Numeric distance remains a separate caller-owned override.
        """
        raw = self.raw_distance(du, dv)
        return math.copysign(max(0., abs(raw) - self.distance_band), raw)


def mapping(projected, *, aspect=1., observability=1., sensitivity=12.,
            maximum=4., deadband=DEADBAND_HEIGHT):
    """Capture a signed scalar mapping from a projected world face normal.

    ``projected`` is a pixel-space direction, with +y down. ``observability``
    measures angular screen visibility of the normal in [0, 1], supplied by
    the Blender caller at the face center for its perspective/orthographic
    view. A nearly view-aligned normal or degenerate projection uses stable
    upward=outward / downward=inward controls. This choice never changes while
    the frozen mapping is in use; it does not infer depth from the hand.
    """
    try:
        projected = tuple(projected)
    except TypeError as exc:
        raise ValueError('Projected normal must have two finite components') from exc
    if len(projected) != 2 or not all(_finite(value) for value in projected):
        raise ValueError('Projected normal must have two finite components')
    if not _finite(observability) or not 0 <= observability <= 1:
        raise ValueError('Normal observability must be between zero and one')
    if any(not _finite(value) or value <= 0
           for value in (aspect, sensitivity, maximum)):
        raise ValueError('Extrusion aspect, sensitivity and bound must be finite and positive')
    if not _finite(deadband) or deadband < 0 or not math.isfinite(deadband * sensitivity):
        raise ValueError('Extrusion deadband must be finite and nonnegative')
    peak = max(abs(value) for value in projected)
    fallback = peak <= 1e-10 or observability < MIN_OBSERVABILITY
    if fallback:
        direction = (0., -1.)
    else:
        scaled = tuple(value / peak for value in projected)
        length = math.hypot(*scaled)
        direction = tuple(value / length for value in scaled)
    return ScalarMapping(direction, aspect, observability, fallback,
                         sensitivity, maximum, deadband)
