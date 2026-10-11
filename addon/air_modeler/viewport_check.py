"""Isolated native WINDOW bounds, browser controls and occluded GPU overlay."""
import os, sys, time, traceback
from pathlib import Path
from types import SimpleNamespace as NS
import bpy, addon_utils, gpu
from mathutils import Vector, Matrix
assert os.environ.get('BLENDER_USER_RESOURCES'), 'Use isolated factory startup'
root = Path(__file__).resolve().parents[2]
bpy.ops.preferences.addon_install(filepath=str(root/'dist/air_modeler.zip'))
addon_utils.enable('air_modeler', default_set=False)
from air_modeler import viewport
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
rv = area.spaces.active.region_3d
context = dict(window=window, area=area, region=region, scene=window.scene, view_layer=window.view_layer)
client = NS(area_id=area.as_pointer(), region_id=region.as_pointer(), face_outline=(), drag=None)
errors, captures, handlers = [], [], []


def synthetic_bounds():
    r = NS(width=1000, height=700, x=100, y=50)
    space = NS(region_quadviews=(), region_3d=NS(view_matrix=Matrix.Identity(4),
        perspective_matrix=Matrix.Identity(4), is_perspective=False, view_perspective='ORTHO'),
        show_region_ui=True, show_region_toolbar=True, show_region_header=True)
    regions = [NS(type='UI', alignment='RIGHT', x=850,y=50,width=250,height=700),
               NS(type='TOOLS', alignment='LEFT', x=100,y=50,width=50,height=700),
               NS(type='HEADER', alignment='TOP', x=100,y=725,width=1000,height=25)]
    c = dict(region=r, area=NS(spaces=NS(active=space), regions=regions))
    full = viewport.mapping(c)
    assert viewport.pixels(full[0], (.5,.5)) == (500,350)
    view = viewport.extrusion_mapping(c)
    assert viewport.cursor_bounds(view[0]) == (50,0,750,675)
    for uv in ((0,0), (1,1), (.31,.77)):
        assert all(abs(a-b)<1e-12 for a,b in zip(uv,viewport.cursor_uv(view[0],viewport.pixels(view[0],uv))))
    # Regions outside WINDOW have already been removed by Blender layout.
    r.width=750; r.x=150
    regions[0].x=900; regions[1].x=100
    space.show_region_header=False
    assert viewport.cursor_bounds(viewport.extrusion_mapping(c)[0]) == (0,0,750,700)
    space.show_region_ui=False; space.show_region_toolbar=False
    assert viewport.pixels(viewport.extrusion_mapping(c)[0], (.5,.5)) == (375,350)
    print('PASS overlap strips excluded only for extrusion; inverse pixels; nonoverlap not removed twice; legacy mapping unchanged',flush=True)


def draw():
    if bpy.context.area != area or bpy.context.region != region: return
    try:
        before=(gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get(),gpu.state.line_width_get())
        viewport.draw_face(client)
        assert before==(gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get(),gpu.state.line_width_get())
    except Exception: errors.append(traceback.format_exc())


def read():
    if bpy.context.area != area or bpy.context.region != region: return
    try:
        x,y,w,h=gpu.state.viewport_get()
        # The synthetic outline sits inside the center of the occluding cube.
        data=gpu.state.active_framebuffer_get().read_color(x,y,w,h,4,0,'FLOAT')
        count=0
        for row in data:
            for rgba in row:
                if rgba[0]>.35 and rgba[2]>.25 and rgba[1]<rgba[0]*.65: count+=1
        captures.append(count)
    except Exception: errors.append(traceback.format_exc())


def settle():
    count=len(captures)
    for _ in range(5): area.tag_redraw(); yield .08
    assert not errors,'\n'.join(errors)
    assert len(captures)>count


def sequence():
    synthetic_bounds()
    space=area.spaces.active
    space.show_region_ui=True; space.show_region_toolbar=True
    for projection in ('PERSP','ORTHO'):
        rv.view_perspective=projection; area.tag_redraw(); yield .2
        full=viewport.mapping(context); view=viewport.extrusion_mapping(context)
        bounds=viewport.cursor_bounds(view[0])
        assert 0<=bounds[0]<bounds[2]<=region.width and 0<=bounds[1]<bounds[3]<=region.height
        for uv in ((.05,.05),(.5,.5),(.95,.95)):
            pixel=viewport.pixels(view[0],uv)
            legacy_uv=pixel[0]/region.width,1-pixel[1]/region.height
            actual=viewport.ray(view,uv); expected=viewport.ray(full,legacy_uv)
            assert (actual[0]-expected[0]).length<1e-5 and (actual[1]-expected[1]).length<1e-6
    print('PASS native perspective/orthographic Right ray matches displayed usable-window cursor with sidebar and toolbar',flush=True)
    face=(9,Vector((0,0,-1)),Vector((0,0,-1)),())
    other=(2,Vector((0,0,1)),Vector((0,0,1)),())
    drag=NS(mode='EXTRUDE',view=view,face_index=None,cursor_face=2,targeting_mode='BROWSE',
            browser_index=0,browser_candidates=[face,other],face_candidates=[other])
    client.drag=drag; client.context=lambda:context
    assert viewport.browser_buttons(client)==(), 'Legacy extrusion must not acquire browse controls'
    drag.dwell=None
    assert viewport.face_candidate(client)==face and viewport.browsed_occluded(client)
    assert viewport.face_style(client)==viewport.CANDIDATE_COLOR
    for action,label,(x0,y0,x1,y1) in viewport.browser_buttons(client):
        event=NS(type='LEFTMOUSE',value='PRESS',mouse_x=region.x+(x0+x1)/2,mouse_y=region.y+(y0+y1)/2)
        assert viewport.browser_action(client,event)==action
    drag.face_index=9
    assert viewport.browser_buttons(client)==() and viewport.face_style(client)==viewport.LOCKED_COLOR
    drag.face_index=None; drag.targeting_mode='HOVER'
    assert not viewport.browsed_occluded(client)
    print('PASS explicit browser candidate overrides stale hover cue; all four control hit targets; lock disables browsing; cyan/orange stages',flush=True)
    for obj in list(window.scene.objects): bpy.data.objects.remove(obj,do_unlink=True)
    space.shading.type='SOLID'; space.overlay.show_overlays=False
    rv.view_rotation=Vector((0,0,1)).to_track_quat('Z','Y'); rv.view_location=(0,0,0); rv.view_distance=8; rv.view_perspective='ORTHO'
    with bpy.context.temp_override(**context): bpy.ops.mesh.primitive_cube_add(size=2)
    outline=tuple(Vector(p) for p in ((-.6,-.6,-1),(.6,-.6,-1),(.6,.6,-1),(-.6,.6,-1)))
    face=(9,Vector((0,0,-1)),Vector((0,0,-1)),outline)
    drag.browser_candidates=[face]; drag.face_candidates=[]; drag.cursor_face=9
    client.face_outline=outline
    handlers.extend((bpy.types.SpaceView3D.draw_handler_add(draw,(),'WINDOW','POST_VIEW'),
                     bpy.types.SpaceView3D.draw_handler_add(read,(),'WINDOW','POST_PIXEL')))
    yield from settle(); normal=captures[-1]
    drag.targeting_mode='BROWSE'
    yield from settle(); browse=captures[-1]
    assert browse>normal+60,(normal,browse)
    drag.targeting_mode='HOVER'
    yield from settle(); assert abs(captures[-1]-normal)<10
    assert len(window.scene.objects)==1 and len(window.view_layer.objects.active.data.polygons)==6
    print('PASS actual GPU: hidden candidate has dashed magenta X-ray only in explicit browse; normal hover stays depth tested; GPU state restored; no geometry edits',flush=True)
    for handler in handlers: bpy.types.SpaceView3D.draw_handler_remove(handler,'WINDOW')
    bpy.ops.wm.quit_blender()

steps=sequence(); deadline=0

def advance():
    global deadline
    if time.monotonic()<deadline:return .03
    try:deadline=time.monotonic()+next(steps);return .03
    except StopIteration:return None
    except Exception:
        traceback.print_exc();sys.stdout.flush();sys.stderr.flush();os._exit(1)
bpy.app.timers.register(advance,first_interval=.3)
