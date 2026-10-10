"""Synthetic coherent captures through the installed ZIP and real companion TCP.

Foreground Blender 5.2.2, --factory-startup and isolated user resources required.
These generated observations verify controller/Undo behavior, not live hands.
"""
import importlib.util
import math
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from uuid import uuid4

import addon_utils
import bpy
from mathutils import Matrix, Quaternion, Vector


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load('clutch_move_helpers', 'move_check.py')
geometry = load('clutch_geometry_helpers', 'extrusion_geometry_check.py')


def same(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(4) for j in range(4)) < 5e-5


def observed(uv=(.5, .5), **changes):
    result = dict(valid=True, confidence=.99, u=uv[0], v=uv[1], palm_u=.5, palm_v=.5,
                  pinching=False, open=True, gesture_id=None, event='NONE',
                  grip=False, angle=None, aperture=None, open_palm=False)
    result.update(changes)
    return result


def absent():
    return observed((None, None), valid=False, confidence=0, palm_u=None, palm_v=None, open=False)


def grip(angle=0., aperture=1.):
    return observed(grip=True, angle=angle, aperture=aperture)


def palm(u=.5, v=.5):
    return observed(open_palm=True, palm_u=u, palm_v=v)


class Check(helpers.Check):
    def __init__(self):
        self.capture_id = 0
        self.capture_origin = time.monotonic()
        self.last_capture = 0.
        self.auto_frames = True
        self.hands = dict(Left=observed(), Right=observed())
        self.disconnections = 0
        super().__init__()
        get_log = self.logs.get_nowait
        def take_log():
            line = get_log()
            if line.startswith('Disconnected:'):
                self.disconnections += 1
            return line
        self.logs.get_nowait = take_log

    def capture(self, left=None, right=None):
        if left is not None:
            self.hands['Left'] = dict(left)
        if right is not None:
            self.hands['Right'] = dict(right)
        self.capture_id += 1
        self.last_capture = time.monotonic()
        self.send(dict(type='hands_frame', payload=dict(frame_id=self.capture_id,
                  t=self.last_capture-self.capture_origin,
                  hands={name: dict(value) for name, value in self.hands.items()})))
        # Boundaries occur once; the heartbeat keeps only the observed held state.
        for hand in self.hands.values():
            hand['event'] = 'NONE'
            if not hand['pinching']:
                hand['gesture_id'] = None

    def step(self):
        if (self.stage == 'run' and self.auto_frames and self.ready
                and time.monotonic()-self.last_capture >= .04):
            self.capture()
        return super().step()

    def until(self, predicate, label, timeout=3):
        deadline = time.monotonic()+timeout
        while not predicate():
            assert time.monotonic() < deadline, (label, self.module.bridge.ui_state(),
                  self.runtime().phase if self.runtime() else None)
            yield .04

    def until_stable(self, predicate, label, settle=.12, timeout=3):
        """Let Blender evaluate/redraw naturally across several timer cycles."""
        deadline = time.monotonic()+timeout
        observed_since = None
        while True:
            now = time.monotonic()
            assert now < deadline, (label, self.module.bridge.ui_state())
            if predicate():
                if observed_since is None:
                    observed_since = now
                elif now-observed_since >= settle:
                    return
            else:
                observed_since = None
            yield .04

    def move_matrix(self, uv):
        drag = self.runtime().drag
        expected = drag.baseline.copy()
        expected.translation += self.module.bridge.viewport.plane_point(
            drag.view, uv, drag.point, drag.normal)-drag.grab
        return expected

    def wait_move(self, uv, label):
        expected = self.move_matrix(uv)
        assert not same(expected, self.runtime().drag.baseline), 'test MOVE must have nonzero displacement'
        yield from self.until_stable(lambda: same(self.obj().matrix_world, expected), label)
        return expected

    def idle(self):
        self.capture(observed(self.uv()), observed())
        yield from self.until(lambda: self.runtime().phase == 'IDLE', 'observed open rearm')

    def start(self, owner='Left', right=None, simultaneous=False, uv=None):
        self.owner = owner
        self.gid = str(uuid4())
        self.start_uv = uv or self.uv()
        selected = observed(self.start_uv, pinching=True, open=False,
                            event='START', gesture_id=self.gid)
        other = right if right is not None else observed()
        if simultaneous:
            other = observed(self.start_uv, pinching=True, open=False,
                             event='START', gesture_id=str(uuid4()))
        self.capture(selected, other) if owner == 'Left' else self.capture(other, selected)
        yield from self.until(lambda: self.runtime().phase == 'SELECTED_READY', 'selection without deformation')
        assert self.runtime().drag.owner == owner

    def owner_at(self, uv, event='NONE', identifier=None):
        owner = observed(uv, event=event, gesture_id=identifier or self.gid)
        if event == 'END':
            owner.update(pinching=False, open=True)
        else:
            owner.update(pinching=True, open=False)
        self.capture(left=owner) if self.owner == 'Left' else self.capture(right=owner)

    def release(self, uv=None):
        self.owner_at(uv or self.start_uv, 'END')
        yield from self.until(lambda: self.runtime().drag is None, 'owner release')
        yield from self.idle()

    def lock(self, mode):
        yield from self.until(lambda: self.runtime().phase == 'DRAGGING', mode+' intent lock')
        assert self.runtime().drag.mode == mode, self.runtime().mode_label()

    def undo_matrix(self, expected):
        self.line('undo')
        yield from self.until_stable(lambda: same(self.obj().matrix_world, expected),
                                     'individual transform Undo', settle=.2)

    def undo_mesh(self, expected, matrix, label):
        self.line('undo')
        yield from self.until_stable(lambda: geometry.snapshot(self.obj().data) == expected
                                     and same(self.obj().matrix_world, matrix), label, settle=.2)

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

    def arm_extrusion(self, phrase, index):
        center, normal = self.aim(index)
        yield .12
        yield from self.idle()
        before = geometry.snapshot(self.obj().data)
        self.line(phrase)
        yield from self.until(lambda: self.runtime().override and self.runtime().mode == 'EXTRUDE', phrase)
        assert geometry.snapshot(self.obj().data) == before, 'arming must not extrude a hover target'
        yield from self.start(right=palm(), uv=(.5, .5))
        assert self.runtime().drag.face_index == index and self.runtime().face_outline
        self.capture(right=palm(.56, .5))
        yield from self.lock('EXTRUDE')
        return center, normal

    def mapped_vector(self, vector):
        control = self.runtime().drag.plane
        reference = self.runtime().drag.palm_reference
        du = Vector(vector).dot(Vector(control.horizontal))/control.sensitivity
        dv = -Vector(vector).dot(Vector(control.vertical))/control.sensitivity
        self.capture(right=palm(reference[0]+du, reference[1]+dv))

    def sequence(self):
        assert self.module.bl_info['version'] == (0, 7, 0)
        self.window.scene.cursor.location = (0, 0, 0)
        self.line('create cube')
        yield from self.until(lambda: len(self.objects()) == 1, 'spawn test cube')
        self.name = self.window.view_layer.objects.active.name
        self.obj().rotation_euler = (.2, -.25, .3)
        self.obj().scale = (1.2, .8, 1.5)
        rv = self.area.spaces.active.region_3d
        rv.view_location = (0, 0, 0)
        rv.view_rotation = Quaternion((1, 0, 0, 0))
        rv.view_distance = 12
        rv.view_perspective = 'ORTHO'
        yield .12
        with self.override():
            bpy.ops.ed.undo_push(message='Clutch synthetic test baseline')
        baseline = self.obj().matrix_world.copy()

        # An unchanged selection and rejected conflicting commands consume no Undo.
        self.window.scene.cursor.location = (4, 0, 0)
        self.line('create sphere')
        yield from self.until(lambda: len(self.objects()) == 2, 'sentinel spawn')
        sentinel = self.window.view_layer.objects.active.name
        sentinel_matrix = self.window.scene.objects[sentinel].matrix_world.copy()
        with self.override():
            values = bpy.context.window_manager.air_modeler_precision
            for mode, field, value in (('MOVE','distance',0), ('ROTATE','angle',0), ('SCALE','factor',1)):
                values.mode = mode
                setattr(values, field, value)
                assert bpy.ops.air_modeler.precision_apply('EXEC_DEFAULT', True) == {'CANCELLED'}
            assert bpy.ops.air_modeler.precision_reset() == {'FINISHED'}
            values.mode = 'EXTRUDE'; values.extrusion = .5
            assert bpy.ops.air_modeler.precision_apply('EXEC_DEFAULT', True) == {'CANCELLED'}
            assert self.runtime().fixed_distance == .5
        assert same(self.window.scene.objects[sentinel].matrix_world, sentinel_matrix)
        assert same(self.obj().matrix_world, baseline)
        yield from self.start()
        yield .3
        assert same(self.obj().matrix_world, baseline)
        self.line('scale by 1.5')
        self.line('rotate x')
        self.line('create prism')
        yield .16
        assert len(self.objects()) == 2 and self.runtime().phase == 'SELECTED_READY'
        assert same(self.obj().matrix_world, baseline)
        with self.override():
            assert not bpy.ops.air_modeler.precision_apply.poll()
        yield from self.release()
        self.line('undo')
        yield from self.until_stable(lambda: sentinel not in self.window.scene.objects
                                     and same(self.obj().matrix_world, baseline),
                                     'stationary selection adds no Undo', settle=.2)
        assert same(self.obj().matrix_world, baseline)
        print('PASS synthetic stationary selection/release, conflicting edits, no-op precision UI and fixed-distance UI arm add no Undo', flush=True)

        # Two completed edits must undo independently. Left wins simultaneous START.
        completed = []
        for owner in ('Left', 'Right'):
            before = self.obj().matrix_world.copy()
            yield from self.start(owner, simultaneous=owner == 'Left')
            start = self.start_uv
            self.owner_at((start[0]+.04, start[1]))
            yield from self.lock('MOVE')
            assert same(self.obj().matrix_world, before), 'recognition must not jump'
            move_uv = start[0]+.075, start[1]-.015
            self.owner_at(move_uv)
            moved = yield from self.wait_move(move_uv, owner+' exact MOVE preview')
            self.capture(right=absent()) if owner == 'Left' else self.capture(left=absent())
            yield .22
            assert self.runtime().drag and same(self.obj().matrix_world, moved), (
                'unrelated loss interrupted MOVE', owner, self.runtime().phase,
                tuple(tuple(row) for row in self.obj().matrix_world), tuple(tuple(row) for row in moved))
            # Wrong final ID freezes; it cannot commit or change ownership.
            self.owner_at((start[0]+.12, start[1]), 'END', str(uuid4()))
            yield .1
            assert self.runtime().drag and same(self.obj().matrix_world, moved)
            self.owner_at((start[0]+.075, start[1]-.015))
            yield .08
            assert same(self.obj().matrix_world, moved)
            self.owner_at((start[0]+.075, start[1]-.015), 'START')
            yield .08
            assert self.runtime().drag.owner == owner
            final_uv = start[0]+.10, start[1]-.015
            expected = self.move_matrix(final_uv)
            yield from self.release(final_uv)
            assert same(self.obj().matrix_world, expected), 'final corrected owner cursor ignored'
            completed.append(expected.copy())
            self.owner_at(final_uv, 'END')
            self.owner_at(final_uv, 'START')
            yield .1
            assert self.runtime().drag is None, 'duplicate gesture replay'
            yield from self.idle()
        yield from self.undo_matrix(completed[0])
        yield from self.undo_matrix(baseline)
        print('PASS synthetic either-hand MOVE, Left tie ownership, unrelated loss, final IDs/dedup, consecutive Undo', flush=True)

        # END itself is observed release. The owner may immediately leave view;
        # the other hand can select next without an extra old-owner open frame.
        yield from self.start('Left', right=absent())
        start = self.start_uv
        self.owner_at((start[0]+.04, start[1]))
        yield from self.lock('MOVE')
        move_uv = start[0]+.07, start[1]
        self.owner_at(move_uv)
        moved = yield from self.wait_move(move_uv, 'exact left MOVE before independent handoff')
        self.owner_at((start[0]+.07, start[1]), 'END')
        # No yield and no additional Left-open frame between these captures.
        yield from self.start('Right', right=absent())
        assert self.runtime().drag.owner == 'Right' and same(self.obj().matrix_world, moved)
        yield from self.release()
        yield from self.undo_matrix(baseline)
        print('PASS synthetic Left END immediately followed by Left absent/Right START needs no extra owner-open frame', flush=True)

        # Missed pinch cannot later acquire a target while held.
        self.owner = 'Left'; self.gid = str(uuid4()); self.start_uv = (.98, .98)
        self.owner_at(self.start_uv, 'START')
        yield from self.until(lambda: self.runtime().phase == 'NEEDS_RELEASE', 'miss release gate')
        self.owner_at(self.uv())
        yield .2
        assert self.runtime().drag is None and same(self.obj().matrix_world, baseline)
        yield from self.idle()

        # Twist controls rotation only; owner movement and aperture cannot switch it.
        yield from self.start(right=grip())
        self.capture(right=grip(.3, 1.))
        yield from self.lock('ROTATE')
        assert same(self.obj().matrix_world, baseline)
        self.capture(right=grip(.6, 1.))
        rotated = Matrix.Rotation(.3, 4, 'Z') @ baseline
        rotated.translation = baseline.translation
        yield from self.until_stable(lambda: abs(self.runtime().drag.amount-.3) < 1e-5
                                     and same(self.obj().matrix_world, rotated), 'twist preview')
        self.owner_at((self.start_uv[0]+.15, self.start_uv[1]+.10))
        self.capture(right=grip(.6, 1.8))
        yield .12
        assert same(self.obj().matrix_world, rotated) and self.runtime().drag.mode == 'ROTATE'
        # A short required-pose loss freezes; reacquisition must not jump.
        self.capture(right=absent())
        yield .12
        assert same(self.obj().matrix_world, rotated)
        self.capture(right=grip(1.3, 1.8))
        yield .08
        assert same(self.obj().matrix_world, rotated), 'right reacquisition jumped'
        self.capture(right=grip(1.5, 1.8))
        yield from self.until(lambda: abs(self.runtime().drag.amount-.5) < 1e-5, 'rotation resumed after loss')
        expected = Matrix.Rotation(.5, 4, 'Z') @ baseline
        expected.translation = baseline.translation
        yield from self.release((.9, .9))
        assert same(self.obj().matrix_world, expected), 'left release motion changed right operation'
        yield from self.undo_matrix(baseline)

        yield from self.start(right=grip())
        self.capture(right=grip(0., 1.3))
        yield from self.lock('SCALE')
        assert same(self.obj().matrix_world, baseline)
        self.capture(right=grip(.9, 1.95))
        expected = Matrix.Scale(1.5, 4) @ baseline
        expected.translation = baseline.translation
        yield from self.until_stable(lambda: abs(self.runtime().drag.amount-1.5) < 1e-5
                                     and same(self.obj().matrix_world, expected), 'aperture preview')
        self.owner_at((self.start_uv[0]-.15, self.start_uv[1]+.1))
        yield .12
        assert self.runtime().drag.mode == 'SCALE' and same(self.obj().matrix_world, expected)
        yield from self.release()
        assert same(self.obj().matrix_world, expected)
        yield from self.undo_matrix(baseline)
        print('PASS synthetic twist/aperture intent, recognition without jump, owner motion ignored, pose recovery, individual Undo', flush=True)

        yield from self.start(right=grip())
        self.capture(right=grip(math.radians(16), 1.24))
        yield .3
        assert self.runtime().phase == 'SELECTED_READY' and same(self.obj().matrix_world, baseline)
        assert 'Twist to rotate or spread fingers to scale' in self.module.bridge.ui_state()[1]
        self.capture(right=grip(.6, 1.24))
        yield from self.lock('ROTATE')
        assert same(self.obj().matrix_world, baseline)
        self.capture(right=grip(.9, 1.24))
        expected = Matrix.Rotation(.3, 4, 'Z') @ baseline
        expected.translation = baseline.translation
        yield from self.until_stable(lambda: same(self.obj().matrix_world, expected), 'exact dominant twist preview')
        self.capture(right=absent())
        yield from self.until(lambda: self.runtime().drag is None, 'sustained required loss cancels', timeout=2)
        assert same(self.obj().matrix_world, baseline) and self.runtime().phase == 'NEEDS_RELEASE'
        self.capture(left=observed(), right=absent())
        yield .12
        assert self.runtime().phase == 'NEEDS_RELEASE', 'missing right must not fabricate open rearm'
        yield from self.idle()
        print('PASS synthetic ambiguity, dominant lock, sustained required loss cancellation and both-hand release gate', flush=True)

        # MOVE reacquisition at a displaced cursor preserves the frozen preview.
        self.area.spaces.active.show_region_ui = True
        yield .12
        yield from self.start('Right')
        start = self.start_uv
        self.owner_at((start[0]+.04, start[1])); yield from self.lock('MOVE')
        move_uv = start[0]+.07, start[1]
        self.owner_at(move_uv)
        frozen = yield from self.wait_move(move_uv, 'exact MOVE before short loss')
        self.capture(right=absent()); yield .12
        self.owner_at((start[0]+.2, start[1])); yield .1
        assert same(self.obj().matrix_world, frozen), 'MOVE reacquisition jumped'
        sidebar = next(region for region in self.area.regions if region.type == 'UI' and region.width > 0)
        modal = self.module.bridge.AIRMODELER_OT_connect.modal
        operator = SimpleNamespace(runtime=self.runtime())
        mouse = dict(value='PRESS', ctrl=False, oskey=False,
                     mouse_x=sidebar.x+sidebar.width//2, mouse_y=sidebar.y+sidebar.height//2)
        with self.override():
            for key in ('G', 'R', 'S', 'TAB', 'DEL'):
                assert modal(operator, bpy.context, SimpleNamespace(type=key, **mouse)) == {'RUNNING_MODAL'}
                assert self.runtime().drag and same(self.obj().matrix_world, frozen)
            assert modal(operator, bpy.context, SimpleNamespace(type='LEFTMOUSE', **mouse)) == {'PASS_THROUGH'}
        assert self.runtime().drag is None, 'sidebar click must restore before passing to native UI'
        assert same(self.obj().matrix_world, baseline)
        yield .1
        assert self.runtime().phase == 'NEEDS_RELEASE'
        yield from self.idle()
        print('PASS synthetic modal editing shortcuts blocked over sidebar; sidebar click restores before native UI receives it', flush=True)

        # Signed world displacement through each mapping plane and both signs.
        self.obj().rotation_euler = (0, 0, 0)
        yield .1
        baseline = self.obj().matrix_world.copy()
        with self.override(): bpy.ops.ed.undo_push(message='Clutch extrusion baseline')
        mesh_before = geometry.snapshot(self.obj().data)
        for axis, sign, plane in [('X',1,'XY'), ('X',-1,'XZ'), ('Y',1,'XY'),
                                  ('Y',-1,'YZ'), ('Z',1,'XZ'), ('Z',-1,'YZ')]:
            vector = Vector(tuple(sign*.4 if name == axis else 0 for name in 'XYZ'))
            index = max(range(len(self.obj().data.polygons)),
                        key=lambda i: self.obj().data.polygons[i].normal.dot(vector))
            center, normal = yield from self.arm_extrusion('extrude plane '+plane.lower()+' axis '+axis.lower(), index)
            assert self.runtime().drag.plane.plane == plane and self.runtime().drag.plane.axis == axis
            self.mapped_vector(vector)
            yield from self.until(lambda: self.runtime().drag.geometry.outward_distance > .39, 'signed extrusion preview')
            self.owner_at((.8, .8))
            yield .08
            assert same(self.obj().matrix_world, baseline)
            geometry.inspect(self.obj().data)
            yield from self.release()
            cap = max(self.obj().data.polygons, key=lambda p: (self.obj().matrix_world @ p.center).dot(normal))
            helpers.near(self.obj().matrix_world @ cap.center, center+vector)
            # Mesh RNA can restore before Blender evaluates matrix_world. Wait
            # for both native Undo results rather than sampling a cached matrix.
            yield from self.undo_mesh(mesh_before, baseline, 'signed geometry and transform Undo')
        print('PASS synthetic TCP XY/XZ/YZ mapping, all six signed world directions, left clutch ignored, geometry Undo', flush=True)

        # Numeric distance arms explicit face operation, stays fixed, and can repeat on its cap.
        snapshots = [mesh_before]
        for distance in (.5, .25):
            index = max(range(len(self.obj().data.polygons)), key=lambda i: self.obj().data.polygons[i].center.z)
            center, normal = yield from self.arm_extrusion(f'extend {distance} units', index)
            assert abs(self.runtime().drag.geometry.outward_distance-distance) < 1e-6
            self.capture(right=palm(.8, .3)); yield .12
            assert abs(self.runtime().drag.geometry.outward_distance-distance) < 1e-6
            yield from self.release()
            geometry.inspect(self.obj().data)
            cap = max(self.obj().data.polygons, key=lambda p: p.center.z)
            helpers.near(self.obj().matrix_world @ cap.center, center+normal*distance)
            snapshots.append(geometry.snapshot(self.obj().data))
        yield from self.undo_mesh(snapshots[1], baseline, 'repeated cap first Undo')
        yield from self.undo_mesh(snapshots[0], baseline, 'repeated cap second Undo')

        # Invalid inward release restores exact data instead of committing the last valid cap.
        index = max(range(len(self.obj().data.polygons)), key=lambda i: self.obj().data.polygons[i].center.z)
        yield from self.arm_extrusion('extrude plane xz axis z', index)
        self.mapped_vector((0, 0, .4))
        yield from self.until(lambda: self.runtime().drag.geometry.outward_distance > .39, 'valid cap before rejection')
        valid = geometry.snapshot(self.obj().data)
        self.mapped_vector((0, 0, -.4))
        yield from self.until(lambda: not self.runtime().drag.valid_preview, 'inward displacement rejection')
        assert geometry.snapshot(self.obj().data) == valid
        yield from self.release()
        assert geometry.snapshot(self.obj().data) == mesh_before
        print('PASS synthetic fixed extrusion, repeated cap and consecutive Undo, invalid inward release exact restoration', flush=True)

        # Held geometry cancels through real disconnect and add-on disable cleanup.
        for reason in ('disconnect', 'disable'):
            yield from self.arm_extrusion('extrude plane xz axis z', index)
            self.mapped_vector((0, 0, .4))
            yield from self.until(lambda: self.runtime().drag.geometry.outward_distance > .39, reason+' preview')
            old = self.runtime()
            detached = self.disconnections
            if reason == 'disconnect': self.module.bridge.disconnect()
            else: addon_utils.disable('air_modeler', default_set=False)
            assert old.timer is None and old.draw_handler is None and old.sock.fileno() == -1
            assert geometry.snapshot(self.obj().data) == mesh_before and same(self.obj().matrix_world, baseline)
            if reason == 'disable': self.module = addon_utils.enable('air_modeler', default_set=False)
            self.ready = None
            yield from self.until(lambda: self.disconnections > detached, 'companion observes old peer EOF')
            self.connect()
            yield from self.until(lambda: self.ready and self.module.bridge.ui_state()[0] == 'Connected', 'explicit reconnect')
            yield from self.idle()
        # A format switch may arrive after a legacy preview has begun; it must
        # restore rather than treating the legacy transaction as hand-owned.
        self.auto_frames = False
        detached = self.disconnections
        self.module.bridge.disconnect()
        self.ready = None
        yield from self.until(lambda: self.disconnections > detached, 'companion observes peer EOF before legacy reconnect')
        self.connect()
        yield from self.until(lambda: self.ready and self.module.bridge.ui_state()[0] == 'Connected', 'legacy-format reconnect')
        uv = self.uv()
        self.frame(uv)
        yield from self.until(lambda: self.runtime().phase == 'IDLE', 'legacy observed release')
        self.gesture('start', str(uuid4()), uv)
        yield from self.until(lambda: self.runtime().phase == 'DRAGGING', 'legacy preview before format switch')
        move_uv = uv[0]+.05, uv[1]
        self.frame(move_uv, pinch=True)
        yield from self.wait_move(move_uv, 'exact legacy MOVE before stream switch')
        self.capture(absent(), absent())
        self.auto_frames = True
        yield from self.until(lambda: self.runtime().drag is None, 'coherent stream switch restores legacy preview')
        assert same(self.obj().matrix_world, baseline) and self.runtime().phase == 'NEEDS_RELEASE'
        yield from self.idle()
        print('PASS synthetic legacy-to-coherent stream switch restores active preview and gates release', flush=True)
        self.auto_frames = False
        self.line('quit')
        yield from self.until(lambda: self.runtime() is None, 'clean companion shutdown')
        yield from self.until(lambda: self.process.poll() is not None, 'companion process exit')
        print('PASS synthetic clutch real TCP, native Undo, disconnect/disable/reconnect and shutdown cleanup', flush=True)


check = Check()
check.deadline = time.monotonic()+180


def advance():
    try:
        return check.step()
    except Exception:
        traceback.print_exc()
        if check.process:
            check.process.terminate()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(advance, first_interval=.2)
