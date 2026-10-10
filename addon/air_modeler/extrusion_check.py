"""Actual companion/TCP extrusion and Undo check in a disposable Blender process."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4

import bpy
import addon_utils
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


helpers = load('move_helpers', 'move_check.py')
geometry = load('geometry_helpers', 'extrusion_geometry_check.py')


def matrix_near(a, b):
    assert max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4)) < 1e-5


class Check(helpers.Check):
    def wait_drag(self):
        deadline = time.monotonic() + 2
        while self.runtime().drag is None:
            assert time.monotonic() < deadline, self.module.bridge.ui_state()
            yield .02

    def aim(self, index):
        obj = self.obj()
        polygon = obj.data.polygons[index]
        center = obj.matrix_world @ polygon.center
        normal = (obj.matrix_world.to_3x3().inverted().transposed() @ polygon.normal).normalized()
        rv = self.area.spaces.active.region_3d
        rv.view_location = center
        rv.view_rotation = normal.to_track_quat('Z', 'Y')
        rv.view_distance = 14
        rv.view_perspective = 'ORTHO'
        self.area.tag_redraw()
        return center, normal

    def cap(self, world_normal):
        obj = self.obj()
        inverse_transpose = obj.matrix_world.to_3x3().inverted().transposed()
        candidates = [p for p in obj.data.polygons if (inverse_transpose @ p.normal).normalized().dot(world_normal) > .999]
        return max(candidates, key=lambda p: (obj.matrix_world @ p.center).dot(world_normal)).index

    def counts(self):
        mesh = self.obj().data
        return len(mesh.vertices), len(mesh.edges), len(mesh.polygons)

    def sequence(self):
        for shape, face_kind in (('cube', 'top'), ('prism', 'top'), ('prism', 'side')):
            self.window.scene.cursor.location = (0, 0, 0)
            self.line('create '+shape)
            yield .15
            self.name = self.window.view_layer.objects.active.name
            self.obj().rotation_euler = (.3, -.25, .2)
            self.obj().scale = (1.2, .7, 1.5)
            yield .1
            mesh = self.obj().data
            sentinel = mesh.attributes.new('sentinel', 'FLOAT', 'POINT')
            for i, value in enumerate(sentinel.data): value.value = i + .25
            mesh.uv_layers.new(name='UV test')
            for i, value in enumerate(mesh.uv_layers.active.data): value.uv = (i / 30, .2)
            mesh.materials.append(bpy.data.materials.new('Extrusion material'))
            with self.override():
                bpy.ops.ed.undo_push(message='Extrusion baseline attributes/transform')
            index = next(p.index for p in mesh.polygons if (p.normal.z > .9 if face_kind == 'top' else abs(p.normal.z) < .1))
            center, normal = self.aim(index)
            yield .15
            baseline = geometry.snapshot(self.obj().data)
            original_matrix = self.obj().matrix_world.copy()
            counts = self.counts()
            meshes = len(bpy.data.meshes)
            sides = len(self.obj().data.polygons[index].vertices)
            self.line('extrude')
            self.frame((.5, .5))
            yield .12
            assert self.runtime().hovered == self.name, self.module.bridge.ui_state()
            assert len(self.runtime().face_outline) == sides
            assert geometry.snapshot(self.obj().data) == baseline
            gid = str(uuid4())
            self.gesture('start', gid, (.5, .5))
            yield .12
            yield from self.wait_drag()
            assert self.runtime().phase == 'DRAGGING', self.module.bridge.ui_state()
            state = self.runtime().drag.geometry
            assert state.face_index == index
            assert self.counts() == (counts[0]+sides, counts[1]+2*sides, counts[2]+sides)
            cap_base = [point.copy() for point in state.base]
            for v in (.4, .3, .35, .35, .5, .4):
                self.frame((.5, v), True)
                yield .1
                assert self.runtime().drag.geometry is state
                assert self.counts() == (counts[0]+sides, counts[1]+2*sides, counts[2]+sides)
                amount = max(0, 4*(.5-v))
                for vert, base in zip(state.cap_vertices, cap_base):
                    helpers.near(original_matrix @ vert.co, original_matrix @ base + normal * amount)
                matrix_near(self.obj().matrix_world, original_matrix)
            self.line('create cube')
            self.line('scale')
            self.gesture('end', str(uuid4()), (.5, 0))
            self.gesture('start', gid, (.5, 0))
            self.frame(pinch=True, present=False)
            yield .12
            assert self.runtime().drag.geometry is state and state.amount > .39
            self.frame((.5, .4), True)
            yield .1
            self.gesture('end', gid, (.5, .25))  # final = 1 world unit
            yield .15
            assert self.runtime().mode == 'MOVE' and self.runtime().drag is None
            assert state.bm is None and state.mesh is None
            assert len(bpy.data.meshes) == meshes
            geometry.inspect(self.obj().data)
            cap_index = self.cap(normal)
            helpers.near(self.obj().matrix_world @ self.obj().data.polygons[cap_index].center, center + normal)
            matrix_near(self.obj().matrix_world, original_matrix)
            first = geometry.snapshot(self.obj().data)
            # Extrude the newly created cap, not an initial face-count/name rule.
            self.aim(cap_index)
            yield .12
            self.line('extrude')
            self.frame((.5, .5))
            yield .12
            gid2 = str(uuid4())
            self.gesture('start', gid2, (.5, .5))
            yield .12
            self.gesture('end', gid2, (.5, .375))
            yield .15
            geometry.inspect(self.obj().data)
            cap_index = self.cap(normal)
            helpers.near(self.obj().matrix_world @ self.obj().data.polygons[cap_index].center, center + normal*1.5)
            self.line('undo')
            yield .15
            assert geometry.snapshot(self.obj().data) == first
            self.line('undo')
            yield .15
            assert geometry.snapshot(self.obj().data) == baseline
            matrix_near(self.obj().matrix_world, original_matrix)
            print('PASS', shape, face_kind, 'world-distance, fixed preview counts, final coordinates, new cap, manifold/normals, attributes, two Undo steps', flush=True)
            # Clear this object from the test scene after completing its checks.
            if not (shape == 'prism' and face_kind == 'side'):
                obj = self.obj()
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(mesh)
        # Last prism remains for recovery cases.
        self.aim(index)
        yield .15
        baseline = geometry.snapshot(self.obj().data)
        meshes = len(bpy.data.meshes)
        for reason in ('cancel', 'loss', 'stale', 'disconnect', 'disable', 'load', 'context', 'edit'):
            self.frame((.5, .5))
            self.line('extrude')
            yield .12
            gid = str(uuid4())
            self.gesture('start', gid, (.5, .5))
            yield .12
            yield from self.wait_drag()
            state = self.runtime().drag.geometry
            self.frame((.5, .3), True)
            yield .12
            if reason == 'cancel':
                self.line('cancel')
            elif reason == 'loss':
                for _ in range(6):
                    self.frame(pinch=True, present=False)
                    yield .1
            elif reason == 'stale':
                yield .6
            elif reason == 'disconnect':
                self.module.bridge.disconnect()
            elif reason == 'disable':
                addon_utils.disable('air_modeler', default_set=False)
            elif reason == 'load':
                self.module.bridge.on_load_pre(None)
            elif reason == 'context':
                self.area.type = 'CONSOLE'
            elif reason == 'edit':
                with self.override(): bpy.ops.object.mode_set(mode='EDIT')
            yield .15
            if reason == 'edit':
                with self.override(): bpy.ops.object.mode_set(mode='OBJECT')
            assert geometry.snapshot(self.obj().data) == baseline, reason
            assert len(bpy.data.meshes) == meshes, reason
            assert state.bm is None and state.mesh is None
            matrix_near(self.obj().matrix_world, original_matrix)
            if reason == 'context':
                self.area.type = 'VIEW_3D'
                self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
            if reason == 'disable': self.module = addon_utils.enable('air_modeler', default_set=False)
            if self.runtime() is None:
                self.connect()
                yield .2
            assert self.runtime().phase == 'NEEDS_RELEASE'
            self.frame((.5, .5), True)
            self.gesture('start', str(uuid4()), (.5, .5))
            self.gesture('end', gid, (.5, 0))
            yield .12
            assert self.runtime().drag is None and geometry.snapshot(self.obj().data) == baseline
            print('PASS extrusion restore/resources/release gate',reason,flush=True)
        self.frame((.5, .5))
        self.line('extrude')
        yield .12
        self.gesture('start', str(uuid4()), (.98, .98))
        yield .1
        self.frame((.5, .5), True)
        yield .1
        assert self.runtime().drag is None and self.runtime().mode == 'EXTRUDE'
        self.frame((.5, .5))
        yield .1
        # Unsupported shared data is rejected through actual TCP before mutation.
        shared = bpy.data.objects.new('Shared source rejection', self.obj().data)
        self.line('extrude')
        self.frame((.5, .5))
        yield .12
        self.gesture('start', str(uuid4()), (.5, .5))
        yield .12
        assert self.runtime().drag is None
        assert 'single-user' in self.module.bridge.ui_state()[2]
        assert geometry.snapshot(self.obj().data) == baseline
        bpy.data.objects.remove(shared)
        self.frame((.5, .5))
        yield .12
        # Zero release and cancellation must not consume an Undo action.
        self.window.scene.cursor.location = (10, 0, 0)
        self.line('create sphere')
        yield .15
        sphere = self.window.view_layer.objects.active.name
        gid = str(uuid4())
        self.gesture('start', gid, (.5, .5))
        yield .12
        self.frame((.5, .3), True)
        yield .1
        self.gesture('end', gid, (.5, .6))  # clamped zero
        yield .12
        assert geometry.snapshot(self.obj().data) == baseline
        self.line('extrude')
        yield .12
        self.gesture('start', str(uuid4()), (.5, .5))
        yield .12
        self.frame((.5, .3), True)
        yield .1
        self.line('undo')  # cancel preview, then undo sphere creation
        yield .15
        assert sphere not in self.window.scene.objects
        assert geometry.snapshot(self.obj().data) == baseline
        print('PASS missed pinch, zero-distance no Undo, Undo during extrusion',flush=True)
        self.line('quit')
        yield .2
        assert self.runtime() is None
        print('PASS real TCP EXTRUDE milestone',flush=True)


check = Check()
check.deadline = time.monotonic()+90

def advance():
    try:
        return check.step()
    except Exception:
        traceback.print_exc()
        if check.process: check.process.terminate()
        sys.stdout.flush();sys.stderr.flush()
        os._exit(1)

bpy.app.timers.register(advance, first_interval=.2)
