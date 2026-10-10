"""Viewport math and a passive cursor. No gesture state, timers or scene edits."""
import math
from types import SimpleNamespace

import bpy
from bpy_extras import view3d_utils


def mapping(context):
    area, region = context['area'], context['region']
    if area.spaces.active.region_quadviews:
        raise RuntimeError('Quad View is unsupported; use one viewport')
    rv = area.spaces.active.region_3d
    return (SimpleNamespace(width=region.width, height=region.height),
            SimpleNamespace(view_matrix=rv.view_matrix.copy(),
                            perspective_matrix=rv.perspective_matrix.copy(),
                            is_perspective=rv.is_perspective,
                            view_perspective=rv.view_perspective))


def pixels(region, uv):
    return uv[0] * region.width, (1 - uv[1]) * region.height


def ray(view, uv):
    region, rv = view
    coord = pixels(region, uv)
    return (view3d_utils.region_2d_to_origin_3d(region, rv, coord),
            view3d_utils.region_2d_to_vector_3d(region, rv, coord))


def eligible(obj, context):
    layer = context['view_layer']
    return (obj.type == 'MESH' and obj.is_editable and obj.data.is_editable
            and obj.parent is None and not obj.hide_select
            and obj.visible_get(view_layer=layer, viewport=context['area'].spaces.active)
            and not obj.constraints and not obj.animation_data
            # Conservative first milestone: all enabled modifiers are unsupported.
            and not any(m.show_viewport for m in obj.modifiers)
            and abs(obj.matrix_world.determinant()) > 1e-10)


def pick(context, view, uv):
    origin, direction = ray(view, uv)
    nearest, rejected = None, False
    with bpy.context.temp_override(**context):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for obj in context['view_layer'].objects:
            if obj.type != 'MESH' or not obj.visible_get(view_layer=context['view_layer'], viewport=context['area'].spaces.active):
                continue
            if abs(obj.matrix_world.determinant()) < 1e-10:
                continue
            inverse = obj.matrix_world.inverted()
            hit, point, _, _ = obj.ray_cast(inverse @ origin,
                                          (inverse.to_3x3() @ direction).normalized(),
                                          depsgraph=depsgraph)
            if not hit:
                continue
            point = obj.matrix_world @ point
            distance = (point - origin).dot(direction)
            if distance < 0:
                continue
            if not eligible(obj, context):
                rejected = True
                continue
            if nearest is None or distance < nearest[0]:
                nearest = distance, obj, point
    return (nearest[1:] if nearest else None), rejected


def plane_point(view, uv, point, normal):
    origin, direction = ray(view, uv)
    denominator = direction.dot(normal)
    if abs(denominator) < 1e-6:
        return None
    distance = (point - origin).dot(normal) / denominator
    result = origin + direction * distance
    if distance < 0 or not all(math.isfinite(v) for v in result):
        return None
    return result


def draw(client):
    context = bpy.context
    if (context.area is None or context.region is None
            or context.area.as_pointer() != client.area_id
            or context.region.as_pointer() != client.region_id
            or not client.tracking or client.cursor is None):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    x, y = pixels(context.region, client.cursor)
    color = (1, .55, .1, 1) if client.drag else ((.2, 1, .4, 1) if client.hovered else (.9, .9, .9, 1))
    points = [(x + 11 * math.cos(i * math.tau / 32), y + 11 * math.sin(i * math.tau / 32)) for i in range(33)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'LINE_STRIP', {'pos': points}).draw(shader)
