"""Frozen, deterministic screen-to-world extrusion controls (no bpy).

Normalized u increases rightward and v downward. The two cardinal plane axes
are assigned to horizontal and vertical by their viewport projection, then
signed to follow screen right/up. At a projection tie, canonical plane order
and the positive axis win. This deliberately avoids inverse-projection gain
at edge-on views: feedback must display the resulting signed axis mapping.
"""
from dataclasses import dataclass
import math


AXES = {'X': (1., 0., 0.), 'Y': (0., 1., 0.), 'Z': (0., 0., 1.)}
PLANES = {'XY': ('X', 'Y'), 'XZ': ('X', 'Z'), 'YZ': ('Y', 'Z')}


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(value):
    try:
        value = tuple(value)
    except TypeError as exc:
        raise ValueError('Mapping requires finite three-component vectors') from exc
    if len(value) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float))
                              or not math.isfinite(x) for x in value):
        raise ValueError('Mapping requires finite three-component vectors')
    length = math.sqrt(_dot(value, value))
    if not math.isfinite(length) or length <= 1e-10:
        raise ValueError('Mapping requires nonzero reference vectors')
    return tuple(x / length for x in value)


@dataclass(frozen=True)
class Mapping:
    plane: str
    axis: str
    horizontal: tuple
    vertical: tuple
    sensitivity: float = 4.0
    maximum: float = 4.0

    def displacement(self, du, dv):
        """World vector; positive du is right, negative dv is up.

        Axis constraint removes the other plane component. The final vector
        length is clamped to maximum while preserving its direction/signs.
        """
        if any(isinstance(x, bool) or not isinstance(x, (int, float))
               or not math.isfinite(x) for x in (du, dv)):
            raise ValueError('Palm displacement must be finite')
        # A short-loss reanchor may put the virtual reference outside [0, 1].
        # Its accumulated delta can exceed one even though observations cannot.
        vector = tuple(h * du - v * dv
                       for h, v in zip(self.horizontal, self.vertical))
        if self.axis != 'NONE':
            vector = tuple(x if AXES[self.axis][i] else 0. for i, x in enumerate(vector))
        peak = max(abs(x) for x in vector)
        if peak == 0:
            return vector
        # Normalize before applying sensitivity to avoid overflow for huge but
        # finite deltas. Cardinal plane axes never sum the two input components.
        direction = tuple(x / peak for x in vector)
        length = math.hypot(*direction)
        distance = min(self.maximum, self.sensitivity * peak * length)
        return tuple(x / length * distance for x in direction)


def mapping(normal, view_right=(1., 0., 0.), view_up=(0., 1., 0.),
            plane='AUTO', axis='NONE', sensitivity=4., maximum=4.):
    """Capture one mapping using a world face normal and viewport world axes.

    AUTO contains the face normal's dominant world axis (X wins exact ties).
    Among compatible planes it chooses the largest projected area; visibility
    breaks an area tie, then XY/XZ/YZ order. A requested axis must be included.
    The frozen result never depends on subsequent viewport or hand motion.
    """
    normal, right, up = _unit(normal), _unit(view_right), _unit(view_up)
    if abs(_dot(right, up)) > 1e-5:
        raise ValueError('Viewport right/up references must be orthogonal')
    if plane not in ('AUTO', *PLANES) or axis not in ('NONE', *AXES):
        raise ValueError('Choose plane AUTO/XY/XZ/YZ and axis NONE/X/Y/Z')
    for value in (sensitivity, maximum):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Mapping sensitivity and bound must be finite and positive')
    if plane == 'AUTO':
        dominant = max(AXES, key=lambda name: abs(_dot(normal, AXES[name])))
        candidates = [name for name, names in PLANES.items()
                      if dominant in names and (axis == 'NONE' or axis in names)]

        def visibility(name):
            a, b = (AXES[label] for label in PLANES[name])
            ar, au, br, bu = _dot(a, right), _dot(a, up), _dot(b, right), _dot(b, up)
            return abs(ar * bu - br * au), ar*ar + au*au + br*br + bu*bu

        plane = max(candidates, key=visibility)
    if axis != 'NONE' and axis not in PLANES[plane]:
        raise ValueError('Extrusion axis must belong to the chosen plane')
    a, b = (AXES[label] for label in PLANES[plane])
    if abs(_dot(b, right)) + abs(_dot(a, up)) > abs(_dot(a, right)) + abs(_dot(b, up)):
        a, b = b, a
    horizontal = tuple(x * (-1 if _dot(a, right) < 0 else 1) for x in a)
    vertical = tuple(x * (-1 if _dot(b, up) < 0 else 1) for x in b)
    return Mapping(plane, axis, horizontal, vertical, sensitivity, maximum)


def automatic(view_right, view_up, plane='AUTO', axis='NONE', sensitivity=12., maximum=4.):
    """Resolve from viewport/override BEFORE faces; edge-on axes use virtual axes."""
    if plane=='AUTO':
        right,up=_unit(view_right),_unit(view_up)
        candidates=[name for name,names in PLANES.items() if axis=='NONE' or axis in names]
        def area(name):
            a,b=(AXES[x] for x in PLANES[name])
            return abs(_dot(a,right)*_dot(b,up)-_dot(a,up)*_dot(b,right))
        plane=max(candidates,key=area)
    return mapping((1,0,0),view_right,view_up,plane,axis,sensitivity,maximum)
