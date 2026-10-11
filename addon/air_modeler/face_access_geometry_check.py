"""Isolated native geometry regression for current face access and world normals.

No controller/socket or physical hand input. Run against the installed final ZIP;
AIR_MODELER_TEST_SOURCE=1 is only a development shortcut before packaging.
"""
import os
import sys
import importlib.util
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
assert os.environ.get('BLENDER_USER_RESOURCES'), 'Use an isolated Blender profile'
if os.environ.get('AIR_MODELER_TEST_SOURCE') == '1':
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'addon'))
    import air_modeler
    air_modeler.register()
else:
    bpy.ops.preferences.addon_install(filepath=os.environ.get('AIR_MODELER_TEST_ZIP', str(ROOT / 'dist/air_modeler.zip')))
    addon_utils.enable('air_modeler', default_set=False)
from air_modeler import extrusion as ex, edit_extrusion as edit

spec = importlib.util.spec_from_file_location('face_access_geometry_helpers', Path(__file__).with_name('extrusion_geometry_check.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def context():
    win = bpy.context.window
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return dict(window=win, area=area, region=region, scene=win.scene, view_layer=win.view_layer)


def create():
    bpy.ops.air_modeler.create_primitive(shape='cube')
    return bpy.context.object


def remove(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def completed(obj, index, amount):
    tx = edit.EditTransaction(obj, context())
    preview = edit.SignedEditPreview(tx, obj, index)
    preview.update(amount)
    preview.validate_result()
    token = tx.finish(obj, keep=True)
    try:
        assert bpy.ops.air_modeler.commit_extrusion('EXEC_DEFAULT', True, target_name=obj.name, prepared_id=token) == {'FINISHED'}
    finally:
        edit.discard(token)


for transform, scale in (('identity', (1, 1, 1)), ('rotated_nonuniform', (1.6, .7, 1.2)),
                         ('single_negative', (-1.6, .7, 1.2)), ('three_negative', (-1.6, -.7, -1.2))):
    obj = create()
    if transform != 'identity':
        obj.rotation_euler = (.31, -.47, .68)
        obj.scale = scale
        bpy.context.view_layer.update()
    original, matrix = obj.data, obj.matrix_world.copy()
    before, mesh_count = helpers.snapshot(original), len(bpy.data.meshes)
    faces, reasons = ex.candidate_report(obj)
    assert len(faces) == 6 and not reasons
    if transform == 'identity':
        assert {tuple(round(v) for v in normal) for _, normal, _, _ in faces} == {
            (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)}
    for index, normal, center, _ in faces:
        # Independent half-space check: each baseline point lies inward of the
        # claimed world normal. This catches an erroneous reflection sign flip.
        assert all((matrix @ vertex.co - center).dot(normal) < 1e-5 for vertex in original.vertices)
        assert (center - matrix.translation).dot(normal) > 0
        tx = edit.EditTransaction(obj, context())
        assert obj.mode == 'EDIT'
        live, omitted = ex.candidate_report(obj)
        assert len(live) == 6 and not omitted
        assert helpers.snapshot(original) == before
        preview = edit.SignedEditPreview(tx, obj, index)
        assert (preview.world_normal - normal).length < 1e-6
        for amount in (.125, .35, -.1, 0., .25):
            preview.update(amount)
            if amount:
                preview.validate_result()
            if amount > 0:
                for vertex, base in zip(preview.cap_vertices, preview.base):
                    step = matrix @ vertex.co - matrix @ base
                    assert (step - normal * amount).length < 2e-6
                    assert abs(step.dot(normal) - amount) < 2e-6
            assert obj.matrix_world == matrix and helpers.snapshot(original) == before
        assert preview.topology_builds == 1
        tx.restore(obj)
        assert obj.mode == 'OBJECT' and obj.data == original and helpers.snapshot(original) == before
        assert len(bpy.data.meshes) == mesh_count
    remove(obj)
    print('PASS current six-face Edit Mode eligibility, signed world distance, one topology and restore:', transform, flush=True)


obj = create()
top = max(ex.candidates(obj), key=lambda item: item[1].z)[0]
completed(obj, top, .5)
faces, reasons = ex.candidate_report(obj)
assert len(faces) == 10 and not reasons, reasons
cap = [item for item in faces if item[1].z > .99 and item[2].z > 1.49]
sides = [item for item in faces if abs(item[1].z) < .01 and min(v.z for v in item[3]) > .99
         and max(v.z for v in item[3]) > 1.49]
assert len(cap) == 1 and len(sides) == 4
for index, normal, _, _ in cap + sides:
    before, original = helpers.snapshot(obj.data), obj.data
    tx = edit.EditTransaction(obj, context())
    candidates, omitted = ex.candidate_report(obj)
    assert index in {item[0] for item in candidates} and not omitted
    preview = edit.SignedEditPreview(tx, obj, index)
    preview.update(.2)
    preview.validate_result()
    for vertex, base in zip(preview.cap_vertices, preview.base):
        assert (obj.matrix_world @ vertex.co - obj.matrix_world @ base - normal * .2).length < 1e-6
    tx.restore(obj)
    assert obj.data == original and helpers.snapshot(original) == before
print('PASS repeated extrusion exposes current cap and all four new supporting side faces in Edit Mode', flush=True)


# Extruding one new side creates a stepped solid: its old coplanar lower side
# becomes recessed. Keep the actual supporting-plane rejection, explain exactly
# which faces it excludes, and verify every remaining candidate still extrudes.
completed(obj, sides[0][0], .2)
faces, reasons = ex.candidate_report(obj)
assert reasons and any('recessed' in reason for reason in reasons.values())
assert {item[0] for item in faces} | set(reasons) == set(range(len(obj.data.polygons)))
assert not ({item[0] for item in faces} & set(reasons))
for index, normal, _, _ in faces:
    tx = edit.EditTransaction(obj, context())
    preview = edit.SignedEditPreview(tx, obj, index)
    preview.update(.1)
    preview.validate_result()
    tx.restore(obj)
remove(obj)
print('PASS current stepped-mesh enumeration preserves specific recessed-face reasons and valid outward paths', flush=True)


obj = create()
tx = edit.EditTransaction(obj, context())
bm = tx.bmesh(obj)
hidden = bm.faces[0]
hidden.hide_set(True)
tx.sync(obj)
faces, reasons = ex.candidate_report(obj)
assert len(faces) == 5 and set(reasons) == {0} and 'hidden' in reasons[0]
hidden.hide_set(False)
# Alter the live Edit BMesh without relying on Object Mode polygons. A missing
# face must invalidate all current candidates through existing manifold checks.
import bmesh
bmesh.ops.delete(bm, geom=[bm.faces[-1]], context='FACES_ONLY')
faces, reasons = ex.candidate_report(obj)
assert not faces and len(reasons) == 5 and all('manifold' in reason for reason in reasons.values())
tx.restore(obj)
remove(obj)
print('PASS explicit hidden-face reason and live Edit BMesh manifold rejection without stale polygon indices', flush=True)
