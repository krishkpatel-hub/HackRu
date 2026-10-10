"""Real WINDOW-region projection and scene occlusion; synthetic, not live hands."""
import os,sys,time,traceback
from pathlib import Path
import bpy,addon_utils
from mathutils import Vector
assert os.environ.get('BLENDER_USER_RESOURCES')
root=Path(__file__).resolve().parents[2]
bpy.ops.preferences.addon_install(filepath=str(root/'dist/air_modeler.zip'))
module=addon_utils.enable('air_modeler',default_set=False)
from air_modeler import visibility as vis,viewport,planes,signed_extrusion as sx
window=bpy.context.window;area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW');rv=area.spaces.active.region_3d
context=dict(window=window,area=area,region=region,scene=window.scene,view_layer=window.view_layer)
for o in list(window.scene.objects):bpy.data.objects.remove(o,do_unlink=True)

def sequence():
    for projection in ('PERSP','ORTHO'):
        for shape in ('cube','prism'):
            with bpy.context.temp_override(**context):bpy.ops.air_modeler.create_primitive(shape=shape)
            obj=window.view_layer.objects.active
            for index in range(len(obj.data.polygons)):
                normal=obj.data.polygons[index].normal.copy();center=obj.data.polygons[index].center.copy()
                rv.view_rotation=normal.to_track_quat('Z','Y');rv.view_location=center;rv.view_distance=8;rv.view_perspective=projection
                area.tag_redraw();yield .2
                view=viewport.mapping(context);faces,records=vis.visible_faces(obj,context,view)
                assert index in [f[0] for f in faces],(projection,shape,index,records)
                assert all(f[1].dot(normal)>.04 for f in faces)
                axis='XYZ'[max(range(3),key=lambda i:abs(normal[i]))]
                plane='XY' if axis in 'XY' else 'XZ'
                mapping=planes.automatic(view[1].view_matrix.inverted().col[0].xyz,view[1].view_matrix.inverted().col[1].xyz,plane,axis)
                for sign in (1,-1):
                    chosen,scores,error=vis.choose(faces,normal*sign,mapping)
                    assert chosen and chosen[0]==index,(shape,index,scores,error)
            print('PASS',projection,shape,'each visible side, hidden exclusion, same face for signed intent',flush=True)
            bpy.data.objects.remove(obj,do_unlink=True)

    with bpy.context.temp_override(**context):bpy.ops.air_modeler.create_primitive(shape='cube')
    obj=window.view_layer.objects.active
    for projection in ('PERSP','ORTHO'):
        rv.view_rotation=Vector((0,0,1)).to_track_quat('Z','Y');rv.view_location=(0,0,0);rv.view_distance=8;rv.view_perspective=projection
        area.tag_redraw();yield .2
        view=viewport.mapping(context);top=max(obj.data.polygons,key=lambda p:p.center.z).index
        with bpy.context.temp_override(**context):bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,3))
        blocker=window.view_layer.objects.active;blocker.scale=(2,2,.1);window.view_layer.update()
        faces,records=vis.visible_faces(obj,context,view)
        assert top not in [f[0] for f in faces],records
        blocker.scale=(.18,.18,.1);window.view_layer.update()
        faces,records=vis.visible_faces(obj,context,view)
        assert top in [f[0] for f in faces],records
        assert 0<next(r for r in records if r['face']==top)['clear_samples']<25
        stamp=vis.scene_stamp(context,obj);blocker.data.vertices[0].co.z+=.1;blocker.data.update();window.view_layer.update()
        assert stamp!=vis.scene_stamp(context,obj)
        bpy.data.objects.remove(blocker,do_unlink=True)
        print('PASS',projection,'fully occluded excluded, blocked-center partial face retained, occluder edit detected',flush=True)
    before,_=vis.visible_faces(obj,context,view)
    obj.rotation_euler=(3.14159265,0,0);window.view_layer.update()
    after,_=vis.visible_faces(obj,context,view)
    assert set(f[0] for f in before)!=set(f[0] for f in after)
    index=after[0][0];sx.commit(obj,index,.4);window.view_layer.update()
    fresh,_=vis.visible_faces(obj,context,view)
    assert all(f[2].z>1.39 for f in fresh)
    assert vis.view_unchanged(context,view)
    rv.view_distance=10;area.tag_redraw();yield .2
    assert not vis.view_unchanged(context,view)
    print('PASS fresh face identities after rotation/extrusion and viewport navigation invalidation',flush=True)
    # Competing visible orthogonal normals must stay ambiguous, while a normal
    # excluded by the plane gets an explicit unobservable diagnostic.
    fake=[(0,Vector((1,0,0)),Vector(),()),(1,Vector((0,1,0)),Vector(),())]
    mapping=planes.automatic((1,0,0),(0,1,0),'XY')
    assert vis.choose(fake,(1,1,0),mapping)[0] is None
    assert vis.choose([(2,Vector((0,0,1)),Vector(),())],(1,0,0),mapping)[0] is None
    parallel=[(0,Vector((1,0,0)),Vector((1,0,0)),()),(1,Vector((1,0,0)),Vector((1,1,0)),())]
    assert vis.choose(parallel,(1,0,0),mapping)[0] is None
    print('PASS materially ambiguous, distinct parallel patches and unobservable mappings remain pending',flush=True)
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
