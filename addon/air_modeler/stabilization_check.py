"""Installed-package spatial/geometry regressions. Synthetic, not live acceptance."""
import os
import math
from pathlib import Path
import bpy
import addon_utils
from mathutils import Matrix,Quaternion,Vector

assert os.environ.get('BLENDER_USER_RESOURCES')
root=Path(__file__).resolve().parents[2]
bpy.ops.preferences.addon_install(filepath=str(root/'dist/air_modeler.zip'))
module=addon_utils.enable('air_modeler',default_set=False)
ex=module.bridge.extrusion;tr=module.bridge.transforms;planes=module.bridge.planes
bpy.ops.air_modeler.create_primitive(shape='cube')
obj=bpy.context.object
obj.location=(3,-2,1);obj.rotation_euler=(.3,.4,.5);obj.scale=(-1.2,.8,1.5)
bpy.context.view_layer.update()
base=obj.matrix_world.copy();signs=tuple(obj.scale)
tr.validate_rigid_scale(obj)
view=Quaternion(Vector((.3,.5,.7)).normalized(),.6)
reference=Quaternion(Vector((1,2,3)).normalized(),.4)
for axis in 'XYZ':
    camera_axis=Vector(tuple(1. if c==axis else 0. for c in 'XYZ'))
    current=Quaternion(camera_axis,.4)@reference
    delta=tr.hand_rotation(current,reference,view)
    expected=view@Quaternion(camera_axis,.4)@view.conjugated()
    assert delta.rotation_difference(expected).angle<1e-5
    final=delta.to_matrix().to_4x4()@base;final.translation=base.translation
    tr.apply_matrix(obj,final,signs);bpy.context.view_layer.update()
    assert (obj.matrix_world.translation-base.translation).length<1e-6
    assert all(abs(abs(a)-abs(b))<1e-5 and (a<0)==(b<0) for a,b in zip(obj.scale,signs))
    for constraint in 'XYZ':
        constrained=tr.hand_rotation(current,reference,view,constraint)
        a,angle=constrained.to_axis_angle()
        assert angle<1e-6 or abs(a['XYZ'.index(constraint)])>.9999
    neg=Quaternion(tuple(-x for x in current))
    assert delta.rotation_difference(tr.hand_rotation(neg,reference,view)).angle<1e-5
# Crossing the shortest-angle branch remains continuous even at non-unit gain.
for gain in (.5,1.,2.):
    a=tr.hand_rotation(Quaternion((0,1,0),math.pi-1e-5),Quaternion(),Quaternion(),'FREE',gain,.035)
    b=tr.hand_rotation(Quaternion((0,1,0),math.pi+1e-5),Quaternion(),Quaternion(),'FREE',gain,.035)
    assert max(abs(a.to_matrix()[i][j]-b.to_matrix()[i][j]) for i in range(3) for j in range(3))<1e-3
tr.apply_matrix(obj,base,signs);bpy.context.view_layer.update()
print('PASS FREE XYZ, viewport conjugation, quaternion sign, explicit constraints and reflected nonuniform rotated target',flush=True)

for sign in (1,-1):
    obj.scale=(sign*1.2,.8,1.5);obj.rotation_euler=(.3,.4,.5);bpy.context.view_layer.update()
    original=obj.data
    faces=ex.candidates(obj)
    for index,normal,center,outline in faces:
        choice=ex.choose_face(faces,normal)
        assert choice[0]==index
        preview=ex.Preview(obj,index)
        preview.update(.4);preview.validate_result()
        assert (preview.world_vector-normal*.4).length<1e-5
        preview.restore(obj)
        assert obj.data==original
print('PASS all transformed face normals, positive/reflected transforms, exact restore',flush=True)
obj.rotation_euler=(0,0,0);obj.scale=(1,1,1);bpy.context.view_layer.update()
faces=ex.candidates(obj)
for axis,plane in [('X','XY'),('Y','YZ'),('Z','XZ')]:
    for sign in (-1,1):
        direction=Vector(tuple(sign if c==axis else 0 for c in 'XYZ'))
        mapping=planes.automatic((1,0,0),(0,1,0),plane,axis)
        du=direction.dot(Vector(mapping.horizontal))*.05
        dv=-direction.dot(Vector(mapping.vertical))*.05
        vector=mapping.displacement(du,dv)
        assert Vector(vector).dot(direction)>.59
        choice=ex.choose_face(faces,vector)
        assert choice and choice[1].dot(direction)>.999
        for aspect in (4/3,16/9):
            pixel_motion=du/aspect*1920
            assert Vector(mapping.displacement(pixel_motion/1920*aspect,dv)).dot(direction)>.59
assert ex.choose_face(faces,(1,1,0)) is None
# Equivalent parallel directions use outermost center, then smallest original index.
a=Vector((1,0,0));outline=faces[0][3]
ties=[(9,a,Vector((2,0,0)),outline),(3,a,Vector((2,0,0)),outline),(1,a,Vector((1,0,0)),outline)]
assert ex.choose_face(ties,a)[0]==3
for n in range(2):
    choice=ex.choose_face(ex.candidates(obj),(0,0,1))
    center=max(v.co.z for v in obj.data.vertices)
    assert ex.commit(obj,choice[0],.4)
    assert abs(max(v.co.z for v in obj.data.vertices)-center-.4)<1e-5
print('PASS all six signed directions, independent AUTO mapping, gain/aspect invariance, ambiguity/ties/repeated outer cap',flush=True)
# Reject shear before allocation. Bypass Blender TRS setter by direct validation proxy.
from types import SimpleNamespace
shear=Matrix.Identity(4);shear[0][1]=.2
try:
    tr.validate_rigid_scale(SimpleNamespace(parent=None,constraints=[],animation_data=None,matrix_world=shear))
    raise AssertionError('shear accepted')
except ValueError:pass
print('PASS unsupported shear rejected before mutation; Blender Python '+__import__('sys').version.split()[0],flush=True)
bpy.ops.wm.quit_blender()
