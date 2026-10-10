"""Installed-package fixed-distance topology and ownership checks; background safe."""
from pathlib import Path
import os
import math

import bpy
import bmesh
import addon_utils
from mathutils import Vector

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


def rejected(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Invalid extrusion accepted')


def vector_checks(ex):
    from air_modeler import planes

    # Synthetic mapped palm displacement: every compatible signed cardinal
    # direction on every plane, with a face whose outward normal agrees.
    for plane in ('XY', 'XZ', 'YZ'):
        for axis in plane:
            for sign in (-1, 1):
                bpy.ops.air_modeler.create_primitive(shape='cube')
                obj = bpy.context.object
                mesh = obj.data
                attr = mesh.attributes.new('sentinel', 'FLOAT', 'POINT')
                for i, value in enumerate(attr.data): value.value = i + .25
                mesh.uv_layers.new(name='Vector UV test')
                for i, value in enumerate(mesh.uv_layers.active.data): value.uv = (i / 30, .75)
                before, matrix, count = snapshot(mesh), obj.matrix_world.copy(), len(bpy.data.meshes)
                normal = Vector(planes.AXES[axis]) * sign
                index = max(range(6), key=lambda i: ex.face_info(obj, i)[0].dot(normal))
                control = planes.mapping(normal, plane=plane, axis=axis)
                component = 'XYZ'.index(axis)
                vector = Vector(control.displacement(.125 * sign * control.horizontal[component],
                                                     -.125 * sign * control.vertical[component]))
                assert (vector - normal * .5).length < 1e-6
                preview = ex.Preview(obj, index)
                for amount in (1., 1.5, .6, 1.):
                    preview.update_vector(vector * amount)
                    preview.validate_result()
                    assert (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)) == (12, 20, 10)
                    assert obj.matrix_world == matrix
                assert abs(inspect(obj.data) - 10) < 1e-5
                valid = snapshot(obj.data)
                tangent = Vector(planes.AXES[next(a for a in 'XYZ' if a != axis)]) * .5
                for bad in (-vector, tangent, normal * 4.1, (math.nan, 0, 0)):
                    rejected(lambda bad=bad: preview.update_vector(bad))
                    assert snapshot(obj.data) == valid and preview.world_vector == vector
                    assert snapshot(mesh) == before and obj.matrix_world == matrix
                preview.update_vector((0, 0, 0))
                rejected(preview.validate_result)
                preview.restore(obj)
                assert obj.data == mesh and snapshot(mesh) == before and len(bpy.data.meshes) == count
                assert ex.commit_vector(obj, index, vector)
                assert abs(inspect(obj.data) - 10) < 1e-5 and obj.matrix_world == matrix
                assert len(bpy.data.meshes) == count
                final_mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(final_mesh)
                print('PASS signed mapped plane', plane, 'axis', axis, sign, 'manifold/restore/attributes/bounds')

    # Every signed world direction remains world-space under rotated,
    # positive nonuniform scaling. Pick the supporting face with greatest
    # positive world-normal dot, so these are valid oblique outward prisms.
    for axis in 'XYZ':
        for sign in (-1, 1):
            bpy.ops.air_modeler.create_primitive(shape='cube')
            obj = bpy.context.object
            obj.rotation_euler = (.4, -.35, .8)
            obj.scale = (1.2, .7, 1.6)
            bpy.context.view_layer.update()
            mesh, matrix = obj.data, obj.matrix_world.copy()
            before, count = snapshot(mesh), len(bpy.data.meshes)
            inverse = matrix.to_3x3().inverted()
            vector = Vector(planes.AXES[axis]) * (.5 * sign)
            index = max(range(6), key=lambda i: (inverse.transposed() @ ex.face_info(obj, i)[0]).normalized().dot(vector))
            preview = ex.Preview(obj, index)
            bases = [v.copy() for v in preview.base]
            preview.update_vector(vector)
            preview.validate_result()
            for base, vertex in zip(bases, preview.cap_vertices):
                assert ((matrix @ vertex.co) - (matrix @ base) - vector).length < 1e-6
            inspect(obj.data)
            assert obj.matrix_world == matrix
            preview.restore(obj)
            assert obj.data == mesh and snapshot(mesh) == before and len(bpy.data.meshes) == count
            assert ex.commit_vector(obj, index, vector)
            inspect(obj.data)
            assert obj.matrix_world == matrix and len(bpy.data.meshes) == count
            final_mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(final_mesh)
            print('PASS rotated nonuniform object signed world axis', axis, sign)

    bpy.ops.air_modeler.create_primitive(shape='cube')
    obj = bpy.context.object
    mesh, before, count = obj.data, snapshot(obj.data), len(bpy.data.meshes)
    normal = ex.face_info(obj, 0)[0]
    assert not ex.commit_vector(obj, 0, (0, 0, 0))
    for invalid in (-normal * .5, (math.nan, 0, 0), (10, 0, 0)):
        rejected(lambda invalid=invalid: ex.commit_vector(obj, 0, invalid))
        assert obj.data == mesh and snapshot(mesh) == before and len(bpy.data.meshes) == count
    obj.scale.x = 0
    bpy.context.view_layer.update()
    rejected(lambda: ex.commit_vector(obj, 0, normal * .5))
    assert obj.data == mesh and snapshot(mesh) == before and len(bpy.data.meshes) == count
    obj.scale.x = 1
    bpy.context.view_layer.update()
    original_update = ex.Preview.update_vector
    captured = []
    def fail_vector_update(preview, vector):
        captured.append(preview)
        if Vector(vector).length:
            raise RuntimeError('Injected vector preview update failure')
        original_update(preview, vector)
    ex.Preview.update_vector = fail_vector_update
    try:
        try:
            ex.commit_vector(obj, 0, normal * .5)
            raise AssertionError('Injected vector failure did not occur')
        except RuntimeError:
            pass
    finally:
        ex.Preview.update_vector = original_update
    assert obj.data == mesh and snapshot(mesh) == before and len(bpy.data.meshes) == count
    assert all(p.bm is None and p.mesh is None for p in captured)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    print('PASS zero/inward/nonfinite/oversize/singular/injected vector commit failure cleanup')


def main():
    assert os.environ.get('BLENDER_USER_RESOURCES')
    bpy.ops.preferences.addon_install(filepath=os.environ.get('AIR_MODELER_TEST_ZIP', str(ROOT / 'dist/air_modeler.zip')))
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
        preview.update(ex.CONFIG.negligible_distance / 2)
        assert 0 < preview.outward_distance < ex.CONFIG.negligible_distance
        rejected(preview.validate_result)
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
    vector_checks(ex)
    addon_utils.disable('air_modeler', default_set=False)
    print('PASS deleted-target ownership cleanup and fixed-distance geometry checks')


if __name__ == '__main__':
    main()
