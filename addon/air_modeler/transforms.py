"""P-owned transform configuration and baseline-relative matrix calculations."""
from dataclasses import dataclass
import math

from mathutils import Matrix


@dataclass(frozen=True)
class TransformConfig:
    rotation_sensitivity: float = math.tau  # radians per normalized viewport width
    scale_sensitivity: float = math.log(10)  # upward full height = 10x
    scale_min: float = 0.1
    scale_max: float = 10.0
    matrix_tolerance: float = 1e-6  # absolute per-element tolerance


CONFIG = TransformConfig()


def preview_matrix(initial, mode, axis, start, current, config):
    """Return (world matrix, angle radians or scale factor), without mutation."""
    if mode == 'ROTATE':
        amount = config.rotation_sensitivity * (current[0] - start[0])
        delta = Matrix.Rotation(amount, 4, axis)
    elif mode == 'SCALE':
        exponent = config.scale_sensitivity * (start[1] - current[1])
        amount = math.exp(max(math.log(config.scale_min), min(math.log(config.scale_max), exponent)))
        delta = Matrix.Scale(amount, 4)
    else:
        raise ValueError('Expected ROTATE or SCALE')
    # Premultiply the original basis, then restore the original origin. This
    # equals T(origin) @ delta @ T(-origin) @ initial without cancellation of
    # large translation values or decomposing the original orientation/scale.
    matrix = delta @ initial
    matrix.translation = initial.translation
    return matrix, amount


def changed(initial, final, tolerance):
    return any(abs(final[i][j] - initial[i][j]) > tolerance for i in range(4) for j in range(4))


def flatten(matrix):
    return tuple(value for row in matrix for value in row)


def apply_matrix(obj, matrix, scale_signs):
    """Assign a world matrix while retaining the original scale-sign convention.

    Blender's setter canonicalizes a reflection to three negative components.
    Compensate paired sign flips in the rotation channels; this does not change
    the world matrix or decompose/recompose the preview calculation itself.
    """
    obj.matrix_world = matrix
    flips = tuple(1 if (value < 0) == (sign < 0) else -1 for value, sign in zip(obj.scale, scale_signs))
    if flips == (1, 1, 1):
        return
    if obj.rotation_mode == 'QUATERNION':
        rotation = obj.rotation_quaternion.to_matrix()
    elif obj.rotation_mode == 'AXIS_ANGLE':
        from mathutils import Quaternion
        rotation = Quaternion(obj.rotation_axis_angle[1:], obj.rotation_axis_angle[0]).to_matrix()
    else:
        rotation = obj.rotation_euler.to_matrix()
    rotation = rotation @ Matrix.Diagonal(flips)
    if obj.rotation_mode == 'QUATERNION':
        obj.rotation_quaternion = rotation.to_quaternion()
    elif obj.rotation_mode == 'AXIS_ANGLE':
        axis, angle = rotation.to_quaternion().to_axis_angle()
        obj.rotation_axis_angle = (angle, *axis)
    else:
        obj.rotation_euler = rotation.to_euler(obj.rotation_mode, obj.rotation_euler)
    obj.scale = tuple(value * flip for value, flip in zip(obj.scale, flips))


def precise_matrix(initial, mode, axis, value):
    """One relative world-space edit; validation is shared with wire/sidebar."""
    if mode == 'MOVE':
        matrix = initial.copy()
        matrix.translation['XYZ'.index(axis)] += value
        return matrix
    delta = Matrix.Rotation(math.radians(value), 4, axis) if mode == 'ROTATE' else Matrix.Scale(value, 4)
    matrix = delta @ initial
    matrix.translation = initial.translation
    return matrix


def commit_precision(context, payload):
    from . import viewport
    from .bridge import protocol
    import bpy
    protocol.validate_precision(dict(payload, id='internal', action='precision'))
    if context.mode != 'OBJECT':
        raise RuntimeError('Precision edits require Object Mode')
    obj = context.view_layer.objects.active
    lookup = dict(view_layer=context.view_layer, window=context.window, area=context.area)
    if obj is None or not obj.select_get() or not viewport.eligible(obj, lookup):
        raise RuntimeError('Select an eligible editable mesh first')
    if payload['mode'] == 'EXTRUDE':
        raise RuntimeError('Extrusion must be armed for a face pinch')
    baseline, signs, name = obj.matrix_world.copy(), tuple(obj.scale), obj.name
    if not all(math.isfinite(v) for row in baseline for v in row):
        raise RuntimeError('Target transform must be finite')
    final = precise_matrix(baseline, payload['mode'], payload.get('axis','Z'), payload['value'])
    if not changed(baseline, final, CONFIG.matrix_tolerance):
        return False
    result = bpy.ops.air_modeler.commit_transform('EXEC_DEFAULT', True, target_name=name,
                                                matrix=flatten(final), scale_signs=signs)
    if result != {'FINISHED'}:
        raise RuntimeError('Precision transform commit failed')

    return True
