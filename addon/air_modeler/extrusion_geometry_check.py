"""Installed-package fixed-distance topology and ownership checks; background safe."""
from pathlib import Path
import os

import bpy
import bmesh
import addon_utils

ROOT = Path(__file__).resolve().parents[2]


def snapshot(mesh):
    return (tuple(tuple(v.co) for v in mesh.vertices),
            tuple(tuple(e.vertices) for e in mesh.edges),
            tuple((tuple(p.vertices), p.material_index) for p in mesh.polygons),
            tuple(v.value for v in mesh.attributes['sentinel'].data) if 'sentinel' in mesh.attributes else (),
            tuple(tuple(v.uv) for v in mesh.uv_layers.active.data) if mesh.uv_layers.active else ())


def inspect(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        assert all(e.is_manifold and e.is_contiguous for e in bm.edges)
        assert all(v.link_faces and v.link_edges for v in bm.verts)
        assert all(f.calc_area() > 1e-8 for f in bm.faces)
        assert bm.calc_volume(signed=True) > 0
        coords = [tuple(round(x, 6) for x in v.co) for v in bm.verts]
        assert len(set(coords)) == len(coords), 'duplicate vertices'
        faces = [frozenset(tuple(round(x, 6) for x in v.co) for v in f.verts) for f in bm.faces]
        assert len(set(faces)) == len(faces), 'duplicate faces'
        return bm.calc_volume(signed=True)
    finally:
        bm.free()


def main():
    assert os.environ.get('BLENDER_USER_RESOURCES')
    bpy.ops.preferences.addon_install(filepath=str(ROOT / 'dist/air_modeler.zip'))
    module = addon_utils.enable('air_modeler', default_set=False)
    ex = module.bridge.extrusion
    for face_index in range(6):
        bpy.ops.air_modeler.create_primitive(shape='cube')
        obj = bpy.context.object
        mesh = obj.data
        attr = mesh.attributes.new('sentinel', 'FLOAT', 'POINT')
        for i, value in enumerate(attr.data): value.value = i + .25
        face_attr = mesh.attributes.new('face_marker', 'INT', 'FACE')
        for i, value in enumerate(face_attr.data): value.value = 100 + i
        mesh.uv_layers.new(name='UV test')
        for i, value in enumerate(mesh.uv_layers.active.data): value.uv = (i / 30, .25)
        mesh.materials.append(bpy.data.materials.new('Extrude test material'))
        original = snapshot(mesh)
        counts = len(bpy.data.meshes)
        normal, face_vertices = ex.face_info(obj, face_index)
        center = sum(face_vertices, face_vertices[0]*0) / len(face_vertices)
        preview = ex.Preview(obj, face_index)
        assert snapshot(mesh) == original
        for amount in (.2, .5, .3, .5):
            preview.update(amount)
            assert (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)) == (12, 20, 10)
        assert abs(inspect(obj.data) - 10) < 1e-5
        assert preview.cap.normal.dot(normal) > .999
        assert preview.cap[preview.bm.faces.layers.int['face_marker']] == 100 + face_index
        assert preview.cap.material_index == mesh.polygons[face_index].material_index
        assert not any((p.center-center).length < 1e-6 for p in obj.data.polygons)
        assert tuple(v.value for v in obj.data.attributes['sentinel'].data[:8]) == original[3]
        assert obj.data.materials[0] == mesh.materials[0]
        preview.restore(obj)
        assert obj.data == mesh and snapshot(mesh) == original
        assert len(bpy.data.meshes) == counts and preview.bm is None
        assert ex.commit(obj, face_index, .5)
        assert len(bpy.data.meshes) == counts
        assert abs(inspect(obj.data) - 10) < 1e-5
        print('PASS fixed cube face',face_index,'normals/volume/interior-cap removal/attributes/ownership')
    obj = bpy.context.object
    mesh = obj.data
    original = snapshot(mesh)
    count = len(bpy.data.meshes)
    for variant in ('shared', 'modifier', 'reflection', 'singular', 'shape_key', 'face_index'):
        other = modifier = None
        matrix = obj.matrix_world.copy()
        if variant == 'shared':
            other = bpy.data.objects.new('Shared test', mesh)
        elif variant == 'modifier':
            modifier = obj.modifiers.new('Unsupported', 'SUBSURF')
        elif variant == 'reflection':
            obj.scale.x = -1
        elif variant == 'singular':
            obj.scale.x = 0
        elif variant == 'shape_key':
            obj.shape_key_add(name='Basis')
        bpy.context.view_layer.update()
        try:
            ex.Preview(obj, 9999 if variant == 'face_index' else 0)
            raise AssertionError('Unsupported target accepted: '+variant)
        except ValueError:
            pass
        assert obj.data == mesh and snapshot(mesh) == original and len(bpy.data.meshes) == count
        if other: bpy.data.objects.remove(other)
        if modifier: obj.modifiers.remove(modifier)
        if variant == 'shape_key': obj.shape_key_clear()
        obj.matrix_world = matrix
        bpy.context.view_layer.update()
    # Reject malformed source topology/coordinates before allocating preview data.
    for variant in ('open', 'nonplanar', 'nonfinite'):
        fixture = mesh.copy()
        obj.data = fixture
        bm = bmesh.new()
        bm.from_mesh(fixture)
        bm.faces.ensure_lookup_table()
        if variant == 'open':
            bmesh.ops.delete(bm, geom=[bm.faces[-1]], context='FACES_ONLY')
        elif variant == 'nonplanar':
            face = next(f for f in bm.faces if len(f.verts) == 4)
            face.verts[0].co += face.normal * .2
            face_index = face.index
        bm.to_mesh(fixture)
        bm.free()
        if variant == 'nonfinite':
            fixture.vertices[0].co.x = float('nan')
        try:
            ex.Preview(obj, face_index if variant == 'nonplanar' else 0)
            raise AssertionError('Malformed mesh accepted: '+variant)
        except ValueError:
            pass
        assert obj.data == fixture and len(bpy.data.meshes) == count + 1
        obj.data = mesh
        bpy.data.meshes.remove(fixture)
    # Inject a failure after the isolated copy is attached during commit.
    original_update = ex.Preview.update
    captured = []
    def fail_update(preview, amount):
        captured.append(preview)
        if amount > 0:
            raise RuntimeError('Injected preview update failure')
        original_update(preview, amount)
    ex.Preview.update = fail_update
    try:
        try:
            ex.commit(obj, 0, .5)
            raise AssertionError('Injected failure did not occur')
        except RuntimeError:
            pass
    finally:
        ex.Preview.update = original_update
    assert obj.data == mesh and snapshot(mesh) == original and len(bpy.data.meshes) == count
    assert all(p.bm is None and p.mesh is None for p in captured)
    assert ex.distance(.5, 1, ex.CONFIG) == 0
    assert ex.distance(1, 0, ex.CONFIG) == ex.CONFIG.maximum_distance
    print('PASS unsupported targets and injected commit failure restore without leaks')
    # Deleted target cleanup does not access invalid RNA or retain preview data.
    preview = ex.Preview(obj, 0)
    bpy.data.objects.remove(obj, do_unlink=True)
    preview.restore(None)
    assert len(bpy.data.meshes) == count and preview.bm is None
    addon_utils.disable('air_modeler', default_set=False)
    print('PASS deleted-target ownership cleanup and fixed-distance geometry checks')


if __name__ == '__main__':
    main()
