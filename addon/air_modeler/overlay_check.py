"""Actual GPU framebuffer checks in an isolated foreground Blender viewport."""
import os,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
import bpy,addon_utils,gpu
from mathutils import Vector
assert os.environ.get('BLENDER_USER_RESOURCES')
root=Path(__file__).resolve().parents[2]
bpy.ops.preferences.addon_install(filepath=str(root/'dist/air_modeler.zip'))
module=addon_utils.enable('air_modeler',default_set=False)
from air_modeler import viewport
window=bpy.context.window;area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW');rv=area.spaces.active.region_3d
context=dict(window=window,area=area,region=region,scene=window.scene,view_layer=window.view_layer)
for obj in list(window.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
area.spaces.active.shading.type='SOLID';area.spaces.active.overlay.show_overlays=False
rv.view_rotation=Vector((0,0,1)).to_track_quat('Z','Y');rv.view_location=(0,0,0);rv.view_distance=8;rv.view_perspective='ORTHO'
client=SimpleNamespace(area_id=area.as_pointer(),region_id=region.as_pointer(),face_outline=(),drag=None)
errors=[];pixels=[];draws=0

def draw():
    global draws
    if bpy.context.area!=area:return
    try:
        before=(gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get(),gpu.state.line_width_get())
        viewport.draw_face(client)
        after=(gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get(),gpu.state.line_width_get())
        assert before==after,(before,after)
        draws+=1
    except Exception:errors.append(traceback.format_exc())

def read():
    if bpy.context.area!=area or bpy.context.region!=region:return
    try:
        x,y,w,h=gpu.state.viewport_get()
        data=gpu.state.active_framebuffer_get().read_color(x+w//2,y+h//2,1,1,4,0,'FLOAT')
        pixels.append(tuple(data[0][0]))
    except Exception:errors.append(traceback.format_exc())

handlers=[bpy.types.SpaceView3D.draw_handler_add(draw,(),'WINDOW','POST_VIEW'),
          bpy.types.SpaceView3D.draw_handler_add(read,(),'WINDOW','POST_PIXEL')]

def difference(a,b):return max(abs(x-y) for x,y in zip(a[:3],b[:3]))
def settle():
    count=len(pixels)
    for _ in range(8):area.tag_redraw();yield .08
    assert not errors,'\n'.join(errors)
    assert len(pixels)>count and draws>0,'GPU callback did not execute'

def sequence():
    with bpy.context.temp_override(**context):bpy.ops.mesh.primitive_cube_add()
    obj=window.view_layer.objects.active
    outline=tuple(Vector(v) for v in ((-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)))
    snapshot=tuple(tuple(v.co) for v in obj.data.vertices),len(obj.data.materials)
    yield from settle();plain=pixels[-1]
    client.face_outline=outline
    yield from settle();candidate=pixels[-1]
    assert difference(candidate,plain)>.03,(plain,candidate)
    client.drag=SimpleNamespace(face_index=5)
    yield from settle();locked=pixels[-1]
    assert difference(candidate,locked)>.03,(candidate,locked)
    assert viewport.face_style(client)==viewport.LOCKED_COLOR
    print('PASS visible polygon tint renders; tentative cyan and locked orange are distinct; GPU state restored',flush=True)
    with bpy.context.temp_override(**context):bpy.ops.mesh.primitive_cube_add(location=(0,0,3))
    blocker=window.view_layer.objects.active;blocker.scale=(2,2,.1);window.view_layer.update()
    client.face_outline=();yield from settle();blocked_plain=pixels[-1]
    client.face_outline=outline;yield from settle();blocked_overlay=pixels[-1]
    assert difference(blocked_plain,blocked_overlay)<.01,(blocked_plain,blocked_overlay)
    print('PASS foreground geometry occludes face highlight in actual depth buffer',flush=True)
    bpy.data.objects.remove(blocker,do_unlink=True)
    client.face_outline=();client.drag=None;yield from settle()
    assert difference(plain,pixels[-1])<.01,(plain,pixels[-1])
    assert snapshot==(tuple(tuple(v.co) for v in obj.data.vertices),len(obj.data.materials))
    print('PASS clearing overlay restores pixels without mesh/material edits',flush=True)
    for handler in handlers:bpy.types.SpaceView3D.draw_handler_remove(handler,'WINDOW')
    bpy.ops.wm.quit_blender()

steps=sequence();deadline=0

def advance():
    global deadline
    if time.monotonic()<deadline:return .03
    try:deadline=time.monotonic()+next(steps);return .03
    except StopIteration:return None
    except Exception:
        traceback.print_exc();sys.stdout.flush();sys.stderr.flush();os._exit(1)
bpy.app.timers.register(advance,first_interval=.3)
