"""Viewport math and a passive cursor. No gesture state, timers or scene edits."""
import math
from types import SimpleNamespace

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector


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

    drag=client.drag
    if client.face_outline and drag and getattr(drag,'face_index',None) is not None and hasattr(drag,'locked_normal'):
        center=sum(client.face_outline,Vector())/len(client.face_outline)
        start=view3d_utils.location_3d_to_region_2d(context.region,context.space_data.region_3d,center)
        end=view3d_utils.location_3d_to_region_2d(context.region,context.space_data.region_3d,center+drag.locked_normal*.6)
        virtual=False
        if start is not None and (end is None or (end-start).length<=3):
            normal=drag.locked_normal.copy()
            if drag.plane.axis!='NONE':
                normal=Vector(tuple(v if i=='XYZ'.index(drag.plane.axis) else 0. for i,v in enumerate(normal)))
            direction=Vector((normal.dot(Vector(drag.plane.horizontal)),normal.dot(Vector(drag.plane.vertical))))
            if direction.length>=.25:
                end=start+direction.normalized()*42;virtual=True
        if start is not None and end is not None and (end-start).length>3:
            direction=(end-start).normalized();side=Vector((-direction.y,direction.x))
            shader.bind();shader.uniform_float('color',(0.2,1.,.5,1.))
            batch_for_shader(shader,'LINES',{'pos':[start,end,end,end-direction*10+side*5,end,end-direction*10-side*5]}).draw(shader)
            import blf
            blf.position(0,end.x+5,end.y+5,0);blf.size(0,12);blf.color(0,.2,1.,.5,1.)
            direction_label='IN' if drag.amount<0 else 'OUT'
            blf.draw(0,('OUT (virtual drag)' if virtual else 'OUT')+f' | face {drag.face_index} | {direction_label} {abs(drag.amount):.3f}')

    import blf
    blf.position(0, x + 16, y + 16, 0)
    blf.size(0, 14)
    blf.color(0, *color)
    blf.draw(0, client.mode_label())



CANDIDATE_COLOR=(.1,.8,1.,1.)
LOCKED_COLOR=(1.,.45,.05,1.)


def face_style(client):
    locked=client.drag is not None and getattr(client.drag,'face_index',None) is not None
    return LOCKED_COLOR if locked else CANDIDATE_COLOR


def draw_face(client):
    """Depth-tested world-space polygon overlay; no materials/objects/Undo."""
    context=bpy.context
    if (context.area is None or context.region is None
            or context.area.as_pointer()!=client.area_id
            or context.region.as_pointer()!=client.region_id or not client.face_outline):return
    import gpu
    from gpu_extras.batch import batch_for_shader
    rv=context.space_data.region_3d
    toward=rv.view_matrix.inverted().col[2].xyz.normalized()
    # Tiny view-facing bias prevents self z-fighting, without disabling occlusion.
    offset=toward*max(1e-6,rv.view_distance*1e-5)
    outline=[point+offset for point in client.face_outline]
    color=face_style(client)
    old=(gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get())
    try:
        gpu.state.depth_test_set('LESS_EQUAL');gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');shader.bind()
        shader.uniform_float('color',(*color[:3],.20))
        triangles=[p for i in range(1,len(outline)-1) for p in (outline[0],outline[i],outline[i+1])]
        batch_for_shader(shader,'TRIS',{'pos':triangles}).draw(shader)
        line_shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR');line_shader.bind()
        line_shader.uniform_float('viewportSize',gpu.state.viewport_get()[2:])
        line_shader.uniform_float('lineWidth',2.5);line_shader.uniform_float('color',color)
        batch_for_shader(line_shader,'LINE_STRIP',{'pos':[*outline,outline[0]]}).draw(line_shader)
    finally:
        gpu.state.depth_test_set(old[0]);gpu.state.depth_mask_set(old[1])
        gpu.state.blend_set(old[2])

def pick_extrusion(context, view, uv):
    from . import extrusion
    origin, direction = ray(view, uv)
    nearest = None
    for obj in context['view_layer'].objects:
        if obj.type != 'MESH' or not obj.visible_get(view_layer=context['view_layer'], viewport=context['area'].spaces.active):
            continue
        if abs(obj.matrix_world.determinant()) <= 1e-10:
            continue
        hit = extrusion.ray_hit(obj, origin, direction)
        if hit:
            point, index = hit
            distance = (point - origin).dot(direction)
            if distance >= 0 and (nearest is None or distance < nearest[0]):
                nearest = distance, obj, point, index
    if nearest is None:
        return None, 'No eligible face under cursor (singular transforms are unsupported)'
    _, obj, point, index = nearest
    try:
        if not eligible(obj, context):
            raise ValueError('EXTRUDE requires a visible editable unparented mesh without enabled modifiers')
        _, vertices = extrusion.face_info(obj, index)
    except ValueError as exc:
        return None, str(exc)
    return (obj, point, index, tuple(obj.matrix_world @ v for v in vertices)), None
