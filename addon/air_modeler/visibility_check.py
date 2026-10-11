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
                view=viewport.mapping(context);trees=[];faces,records=vis.visible_faces(obj,context,view,trees)
                assert index in [f[0] for f in faces],(projection,shape,index,records)
                assert all(f[1].dot(normal)>.04 for f in faces)
                axis='XYZ'[max(range(3),key=lambda i:abs(normal[i]))]
                plane='XY' if axis in 'XY' else 'XZ'
                mapping=planes.automatic(view[1].view_matrix.inverted().col[0].xyz,view[1].view_matrix.inverted().col[1].xyz,plane,axis)
                assert vis.observability(normal,mapping)>=.25
                assert vis.cursor_face(faces,view,(.5,.5),trees)==index
                # Polygon center lies on its triangulation seam: one identity.
                assert vis.cursor_face(faces,view,(.502,.5),trees)==index
            print('PASS',projection,shape,'each visible side, hidden exclusion, displayed center ray and same polygon across triangle seam',flush=True)
            bpy.data.objects.remove(obj,do_unlink=True)

    # World normals must agree with transformed face tangents under nonuniform
    # scale, rotation and reflection. Inspect every side in the actual viewport.
    for shape,scale in (('cube',(1.7,.6,1.2)),('cube',(-1.7,.6,1.2)),('prism',(1.7,.6,1.2))):
        with bpy.context.temp_override(**context):bpy.ops.air_modeler.create_primitive(shape=shape)
        obj=window.view_layer.objects.active;obj.rotation_euler=(.4,-.7,.2);obj.scale=scale
        window.view_layer.update()
        for polygon in obj.data.polygons:
            normal=(obj.matrix_world.to_3x3().inverted().transposed()@polygon.normal).normalized()
            center=obj.matrix_world@polygon.center
            points=[obj.matrix_world@obj.data.vertices[i].co for i in polygon.vertices]
            assert abs(normal.dot(points[1]-points[0]))<1e-6 and abs(normal.dot(points[2]-points[0]))<1e-6
            rv.view_rotation=normal.to_track_quat('Z','Y');rv.view_location=center;rv.view_distance=10;rv.view_perspective='ORTHO'
            area.tag_redraw();yield .2
            view=viewport.mapping(context);trees=[];faces,_=vis.visible_faces(obj,context,view,trees)
            actual=next(f for f in faces if f[0]==polygon.index)
            assert actual[1].dot(normal)>.99999
            pixel=vis.projected(view,center);uv=pixel.x/view[0].width,1-pixel.y/view[0].height
            assert vis.cursor_face(faces,view,uv,trees)==polygon.index,(shape,scale,polygon.index,uv,vis.cursor_face(faces,view,uv,trees),[(f[0],tuple(f[2])) for f in faces])
            mapping=planes.automatic(view[1].view_matrix.inverted().col[0].xyz,view[1].view_matrix.inverted().col[1].xyz)
            assert vis.observability(normal,mapping)>=.25
        bpy.data.objects.remove(obj,do_unlink=True)
    print('PASS rotated nonuniform/reflected world normals, transformed tangents and signed projected selection',flush=True)

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
        trees=[];faces,records=vis.visible_faces(obj,context,view,trees)
        assert vis.cursor_face(faces,view,(.5,.5),trees) is None, "occluder under cursor must block secondary cue"
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
    mapping=planes.automatic((1,0,0),(0,1,0),'XY')
    assert vis.observability(Vector((0,0,1)),mapping)==0
    assert vis.observability(Vector((1,0,0)),mapping)==1
    assert vis.cursor_face(fresh,view,(.99,.01),[]) is None
    print('PASS incompatible normal mapping reports zero observability; no alternative face selection',flush=True)
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
