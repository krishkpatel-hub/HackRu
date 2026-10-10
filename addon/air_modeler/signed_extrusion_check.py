"""Installed ZIP: clean convex shortening, limits, ownership and native API probe."""
import os,sys,importlib.util
from pathlib import Path
import bpy,bmesh,addon_utils
from mathutils import Vector
assert os.environ.get('BLENDER_USER_RESOURCES')
root=Path(__file__).resolve().parents[2]
bpy.ops.preferences.addon_install(filepath=str(root/'dist/air_modeler.zip'))
module=addon_utils.enable('air_modeler',default_set=False)
from air_modeler import signed_extrusion as sx,extrusion as ex
spec=importlib.util.spec_from_file_location('geometry_helpers',Path(__file__).with_name('extrusion_geometry_check.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

def remove(obj):
    mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
    if mesh.users==0:bpy.data.meshes.remove(mesh)

for shape in ('cube','prism'):
    for transform in ('identity','rotated_scaled','reflected'):
        bpy.ops.air_modeler.create_primitive(shape=shape);obj=bpy.context.object
        if transform!='identity':
            obj.rotation_euler=(.3,.4,.5);obj.scale=(-1.2 if transform=='reflected' else 1.2,.8,1.5)
            bpy.context.view_layer.update()
        mesh=obj.data
        attr=mesh.attributes.new('sentinel','FLOAT','POINT')
        for i,v in enumerate(attr.data):v.value=i+.25
        mesh.uv_layers.new(name='Preserved UV')
        for i,v in enumerate(mesh.uv_layers.active.data):v.uv=(i/30,.75)
        before=g.snapshot(mesh);count=len(bpy.data.meshes)
        for index in range(len(mesh.polygons)):
            preview=sx.SignedPreview(obj,index);assert preview.plan,preview.inward_error
            for amount in (-.2,0,.4,.2,0,-100,-.15,.3,0,-.2):
                preview.update(amount)
                if preview.amount:
                    preview.validate_result();g.inspect(obj.data)
                else:assert obj.data==mesh and g.snapshot(obj.data)==before
                if amount<0:
                    assert len(obj.data.vertices)==len(mesh.vertices) and len(obj.data.polygons)==len(mesh.polygons)
                if amount==-100:
                    assert preview.amount==-preview.plan.limit and 'limit' in preview.limit_reason
                assert g.snapshot(mesh)==before
            expected=g.snapshot(obj.data);preview.restore(obj)
            assert obj.data==mesh and g.snapshot(mesh)==before and len(bpy.data.meshes)==count
            # Deterministic native commit produces exactly the last preview.
            backup=mesh.copy()
            sx.commit(obj,index,-.2);assert g.snapshot(obj.data)==expected
            committed=obj.data;obj.data=backup;bpy.data.meshes.remove(committed)
            mesh=backup;before=g.snapshot(mesh)
            assert len(bpy.data.meshes)==count
        remove(obj)
        print('PASS all',shape,'faces',transform,'signed/zero/limit/exact attributes/commit parity',flush=True)

# Repeated outward rings impose an earlier inward topology event, not an
# opposite-wall or bounding-box estimate. Tapered prism side planes remain fixed.
for shape in ('cube','prism'):
    bpy.ops.air_modeler.create_primitive(shape=shape);obj=bpy.context.object
    index=max(range(len(obj.data.polygons)),key=lambda i:obj.data.polygons[i].center.z)
    sx.commit(obj,index,.5)
    index=max(range(len(obj.data.polygons)),key=lambda i:obj.data.polygons[i].center.z)
    p=sx.SignedPreview(obj,index);assert p.plan,p.inward_error
    assert abs(p.plan.limit-.495)<1e-5
    p.update(-10);p.validate_result();p.restore(obj)
    sx.commit(obj,index,.25)
    index=max(range(len(obj.data.polygons)),key=lambda i:obj.data.polygons[i].center.z)
    p=sx.SignedPreview(obj,index);assert abs(p.plan.limit-.2475)<1e-5
    p.update(-10);p.validate_result();p.restore(obj);remove(obj)
    print('PASS repeated',shape,'cap inward bound at prior ring',flush=True)

bpy.ops.air_modeler.create_primitive(shape='cube');obj=bpy.context.object
for v in obj.data.vertices:
    if v.co.z>0:v.co.x*=.5;v.co.y*=.5
obj.data.update();index=max(range(6),key=lambda i:obj.data.polygons[i].center.z)
p=sx.SignedPreview(obj,index);assert p.plan,p.inward_error
p.update(-.5);p.validate_result();assert g.inspect(obj.data)>0;p.restore(obj)
# An unsupported concave baseline cannot gain inward permission.
obj.data.vertices[0].co=(0,0,0);obj.data.update()
try:sx.InwardPlan(obj,index)
except ValueError:pass
else:raise AssertionError('Concave inward geometry accepted')
remove(obj);print('PASS tapered side-plane shortening and unsupported concavity rejection',flush=True)

# Exercise the installed native API rather than assuming its name guarantees
# valid inward geometry. Cube/top-prism clean; prism side may be edge-manifold
# while failing convex support/orientation. The signed path does not use it.
for shape in ('cube','prism'):
    for side in (False,True):
        bpy.ops.air_modeler.create_primitive(shape=shape);obj=bpy.context.object
        axis='x' if side else 'z';index=max(range(len(obj.data.polygons)),key=lambda i:getattr(obj.data.polygons[i].normal,axis))
        normal=obj.data.polygons[index].normal.copy()
        bpy.context.tool_settings.mesh_select_mode=(False,False,True)
        for v in obj.data.vertices:v.select=False
        for e in obj.data.edges:e.select=False
        for f in obj.data.polygons:f.select=f.index==index
        bpy.ops.object.mode_set(mode='EDIT')
        result=bpy.ops.mesh.extrude_manifold('EXEC_DEFAULT',MESH_OT_extrude_region={'use_dissolve_ortho_edges':True},TRANSFORM_OT_translate={'value':tuple(normal*-.5)})
        bpy.ops.object.mode_set(mode='OBJECT');assert result=={'FINISHED'}
        bm=bmesh.new();bm.from_mesh(obj.data)
        try:sx.validate_convex(bm);clean=True
        except ValueError:clean=False
        finally:bm.free()
        assert clean==(shape=='cube' or not side),(shape,side,clean)
        remove(obj)
print('PASS installed native Manifold API evaluation: clean cube/caps; prism side fails clean convex result',flush=True)
