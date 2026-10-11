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
    left, bottom, right, top = cursor_bounds(region)
    return left + uv[0] * (right-left), bottom + (1-uv[1]) * (top-bottom)


def cursor_bounds(region):
    """Pixel rectangle for this cursor; legacy gestures retain the full region."""
    return getattr(region, 'cursor_rect', (0., 0., region.width, region.height))


def cursor_uv(region, point):
    left, bottom, right, top = cursor_bounds(region)
    return (point[0]-left)/(right-left), 1-(point[1]-bottom)/(top-bottom)


def extrusion_mapping(context):
    """Map only the extrusion Right cursor across unobscured viewport pixels.

    Blender can draw its toolbar/sidebar over the WINDOW region. Keep full
    region dimensions for projection, while excluding only overlapping edge
    strips for normalized cursor coordinates. Non-overlapping region layouts
    already exclude these strips and therefore are not subtracted twice.
    """
    view = mapping(context)
    region, space = context['region'], context['area'].spaces.active
    left, bottom, right, top = 0., 0., float(region.width), float(region.height)
    visibility = {'UI': 'show_region_ui', 'TOOLS': 'show_region_toolbar',
                  'HEADER': 'show_region_header', 'TOOL_HEADER': 'show_region_tool_header'}
    for other in context['area'].regions:
        if other.type not in {'UI', 'TOOLS', 'HEADER', 'TOOL_HEADER', 'FOOTER'}:
            continue
        if not getattr(space, visibility.get(other.type, ''), True):
            continue
        if other.width <= 1 or other.height <= 1:
            continue
        x0, y0 = other.x-region.x, other.y-region.y
        x1, y1 = x0+other.width, y0+other.height
        if x1 <= left or x0 >= right or y1 <= bottom or y0 >= top:
            continue
        align = getattr(other, 'alignment', '')
        if align == 'LEFT' or (other.type == 'TOOLS' and x0 <= left):
            left = max(left, x1)
        elif align == 'RIGHT' or (other.type == 'UI' and x1 >= right):
            right = min(right, x0)
        elif align == 'TOP' or (other.type in {'HEADER','TOOL_HEADER'} and y1 >= top):
            top = min(top, y0)
        elif align == 'BOTTOM' or (other.type in {'HEADER','FOOTER'} and y0 <= bottom):
            bottom = max(bottom, y1)
    if right-left < 2 or top-bottom < 2:
        raise RuntimeError('Extrusion viewport is covered; narrow or close the sidebar')
    view[0].cursor_rect = (left, bottom, right, top)
    return view


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


def browser_buttons(client):
    """Visible, extrusion-only controls; rectangles use WINDOW pixel space."""
    drag = client.drag
    if (drag is None or drag.mode != 'EXTRUDE' or not hasattr(drag, 'dwell')
            or getattr(drag, 'face_index', None) is not None):
        return ()
    left, bottom, right, top = cursor_bounds(drag.view[0])
    specs = (('PREVIOUS', 'Previous Face'), ('NEXT', 'Next Face'),
             ('CONFIRM', 'Confirm / dwell'), ('HOVER', 'Hover targeting'))
    gap, x, y = 6., left+12., bottom+14.
    available = max(1., right-left-24.)
    columns = 4 if available >= 420 else (2 if available >= 210 else 1)
    width = min(126., (available-gap*(columns-1))/columns)
    return tuple((action, label, (x+(i%columns)*(width+gap), y+(i//columns)*35,
                  x+(i%columns)*(width+gap)+width, y+(i//columns)*35+29.))
                 for i, (action, label) in enumerate(specs))


def browser_action(client, event):
    """Hit testing only. The controller owns browse, confirm and dwell state."""
    if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
        return None
    region = client.context()['region']
    x, y = event.mouse_x-region.x, event.mouse_y-region.y
    for action, label, (left, bottom, right, top) in browser_buttons(client):
        if left <= x <= right and bottom <= y <= top:
            if action == 'CONFIRM' and getattr(client.drag, 'targeting_mode', 'HOVER') != 'BROWSE':
                return None
            return action
    return None


def face_candidate(client):
    drag = client.drag
    if drag is None or getattr(drag, 'mode', None) != 'EXTRUDE':
        return None
    index = getattr(drag, 'face_index', None)
    if index is None:
        index = getattr(drag, 'cursor_face', None)
    candidates = getattr(drag, 'browser_candidates', getattr(drag, 'all_candidates', ()))
    if (getattr(drag, 'targeting_mode', 'HOVER') == 'BROWSE'
            and getattr(drag, 'face_index', None) is None and candidates):
        selected = getattr(drag, 'browser_index', None)
        if selected is not None and 0 <= selected < len(candidates):
            return candidates[selected]
    return next((face for face in candidates if face[0] == index),
                next((face for face in getattr(drag, 'face_candidates', ()) if face[0] == index), None))


def browsed_occluded(client):
    drag, candidate = client.drag, face_candidate(client)
    return bool(drag and getattr(drag, 'targeting_mode', 'HOVER') == 'BROWSE' and candidate
                and not any(face[0] == candidate[0] for face in getattr(drag, 'face_candidates', ())))


def draw(client):
    context = bpy.context
    if (context.area is None or context.region is None
            or context.area.as_pointer() != client.area_id
            or context.region.as_pointer() != client.region_id):
        return
    import gpu
    import blf
    from gpu_extras.batch import batch_for_shader
    drag = client.drag
    extruding = drag is not None and drag.mode == 'EXTRUDE'
    show_cursor = client.tracking and client.cursor is not None
    if not show_cursor and not extruding:
        return
    region = drag.view[0] if extruding else context.region
    x, y = pixels(region, client.cursor if show_cursor else (.5, .5))
    color = face_style(client) if extruding else ((1, .55, .1, 1) if drag else
            ((.2, 1, .4, 1) if client.hovered else (.9, .9, .9, 1)))
    points = [(x + 11*math.cos(i*math.tau/32), y + 11*math.sin(i*math.tau/32)) for i in range(33)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind(); shader.uniform_float('color', color)
    if show_cursor:
        batch_for_shader(shader, 'LINE_STRIP', {'pos': points}).draw(shader)

    def text(text, x, y, color, size=12):
        blf.position(0, x, y, 0); blf.size(0, size); blf.color(0, *color); blf.draw(0, text)

    if client.face_outline and extruding and getattr(drag, 'face_index', None) is not None and hasattr(drag, 'locked_normal'):
        center = sum(client.face_outline, Vector())/len(client.face_outline)
        start = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, center)
        end = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, center+drag.locked_normal*.6)
        auto = getattr(drag, 'auto_mapping', None)
        virtual = False
        if start is not None and auto is not None:
            # Frozen at lock by the AUTO scalar mapper; show actual drag input,
            # including its stable upward fallback for camera-facing normals.
            end = start+Vector((auto.direction[0], -auto.direction[1]))*54
            virtual = auto.fallback
        elif start is not None and (end is None or (end-start).length <= 3):
            normal = drag.locked_normal.copy()
            if drag.plane.axis != 'NONE':
                normal = Vector(tuple(v if i == 'XYZ'.index(drag.plane.axis) else 0. for i, v in enumerate(normal)))
            direction = Vector((normal.dot(Vector(drag.plane.horizontal)), normal.dot(Vector(drag.plane.vertical))))
            if direction.length >= .25:
                end = start+direction.normalized()*42; virtual = True
        if start is not None and end is not None and (end-start).length > 3:
            direction = (end-start).normalized(); side = Vector((-direction.y, direction.x))
            shader.bind(); shader.uniform_float('color', (.2, 1., .5, 1.))
            batch_for_shader(shader, 'LINES', {'pos': [start, end, end, end-direction*10+side*5,
                                                     end, end-direction*10-side*5]}).draw(shader)
            label = 'OUT — upward fallback' if auto is not None and virtual else ('OUT — explicit plane' if virtual else 'OUT')
            text(label+f' | {drag.amount:+.3f}', end.x+5, end.y+5, (.2, 1., .5, 1.))

    left, bottom, right, top = cursor_bounds(region)
    if show_cursor:
        label_x = min(x+16, max(left+12, right-390)) if extruding else x+16
        label_y = min(y+16, top-20) if extruding else y+16
        text(client.mode_label(), label_x, label_y, color, 14)
    if not extruding or not hasattr(drag, 'dwell'):
        return
    candidate = face_candidate(client)
    mode = getattr(drag, 'targeting_mode', 'HOVER')
    records = getattr(drag, 'browser_candidates', getattr(drag, 'all_candidates', ()))
    position = next((i+1 for i, face in enumerate(records) if candidate and face[0] == candidate[0]), None)
    detail = f'Face {position} of {len(records)}' if position is not None else 'Choose a face'
    detail += ' | BROWSE / OCCLUDED' if browsed_occluded(client) else f' | {mode}'
    if candidate:
        detail += ' | world normal ('+', '.join(f'{v:+.2f}' for v in candidate[1])+')'
    text(detail, left+14, top-27, BROWSE_COLOR if browsed_occluded(client) else color)
    if getattr(drag, 'face_index', None) is None:
        text(client.target_message[:115], left+14, top-46, color)
        if getattr(drag, 'dwell', None) is not None:
            fraction = min(1., max(0., drag.dwell.progress/drag.dwell.config.duration))
            # Always visible at a fixed location, independent of cursor jitter.
            for length, shade in ((190, (.06,.08,.1,1.)), (190*fraction, color)):
                shader.bind(); shader.uniform_float('color', shade)
                batch_for_shader(shader, 'TRIS', {'pos': [(left+14,top-57), (left+14+length,top-57),
                    (left+14+length,top-62), (left+14,top-57), (left+14+length,top-62), (left+14,top-62)]}).draw(shader)
    for action, label, (x0,y0,x1,y1) in browser_buttons(client):
        enabled = action != 'CONFIRM' or mode == 'BROWSE'
        shader.bind(); shader.uniform_float('color', (.07,.10,.14,1.) if enabled else (.08,.08,.08,1.))
        batch_for_shader(shader, 'TRIS', {'pos': [(x0,y0),(x1,y0),(x1,y1),(x0,y0),(x1,y1),(x0,y1)]}).draw(shader)
        text(label, x0+6, y0+10, (.9,.95,1.,1.) if enabled else (.4,.4,.4,1.), 11)


CANDIDATE_COLOR = (.1,.8,1.,1.)
LOCKED_COLOR = (1.,.45,.05,1.)
BROWSE_COLOR = (1.,.2,.85,1.)


def face_style(client):
    locked = client.drag is not None and getattr(client.drag, 'face_index', None) is not None
    return LOCKED_COLOR if locked else CANDIDATE_COLOR


def dashed_outline(outline, region, rv):
    """Whole polygon perimeter, with approximately eight-pixel dash segments."""
    segments = []
    for start, end in zip(outline, outline[1:]+outline[:1]):
        a = view3d_utils.location_3d_to_region_2d(region, rv, start)
        b = view3d_utils.location_3d_to_region_2d(region, rv, end)
        length = (b-a).length if a is not None and b is not None else 64.
        count = min(256, max(2, math.ceil(length/8)))
        for i in range(0, count, 2):
            segments.extend((start.lerp(end, i/count), start.lerp(end, min(1., (i+1)/count))))
    return segments


def draw_face(client):
    """Depth-tested complete boundary plus explicit, dashed browse X-ray cue."""
    context = bpy.context
    if (context.area is None or context.region is None
            or context.area.as_pointer() != client.area_id
            or context.region.as_pointer() != client.region_id or not client.face_outline):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    rv = context.space_data.region_3d
    toward = rv.view_matrix.inverted().col[2].xyz.normalized()
    offset = toward*max(1e-6, rv.view_distance*1e-5)
    outline = [point+offset for point in client.face_outline]
    color = face_style(client)
    old = (gpu.state.depth_test_get(), gpu.state.depth_mask_get(), gpu.state.blend_get())
    try:
        gpu.state.depth_test_set('LESS_EQUAL'); gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        shader = gpu.shader.from_builtin('UNIFORM_COLOR'); shader.bind()
        shader.uniform_float('color', (*color[:3], .20))
        triangles = [p for i in range(1, len(outline)-1) for p in (outline[0], outline[i], outline[i+1])]
        batch_for_shader(shader, 'TRIS', {'pos': triangles}).draw(shader)
        line_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        line_shader.bind(); line_shader.uniform_float('viewportSize', gpu.state.viewport_get()[2:])
        boundary = batch_for_shader(line_shader, 'LINE_STRIP', {'pos': [*outline, outline[0]]})
        # Contrasting under-stroke separates even adjacent coplanar boundaries.
        for width, shade in ((7., (.015,.02,.025,1.)), (3.5, color)):
            line_shader.uniform_float('lineWidth', width); line_shader.uniform_float('color', shade)
            boundary.draw(line_shader)
        if browsed_occluded(client):
            # Only explicit browsing reveals hidden faces. Ordinary hover never
            # silently selects through the object or draws a hidden candidate.
            gpu.state.depth_test_set('NONE')
            line_shader.bind(); line_shader.uniform_float('lineWidth', 2.5)
            line_shader.uniform_float('color', BROWSE_COLOR)
            batch_for_shader(line_shader, 'LINES', {'pos': dashed_outline(outline, context.region, rv)}).draw(line_shader)
    finally:
        gpu.state.depth_test_set(old[0]); gpu.state.depth_mask_set(old[1]); gpu.state.blend_set(old[2])

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
