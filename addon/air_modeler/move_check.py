"""Disposable foreground check: actual companion CLI, TCP, modal timer and Undo."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback
from uuid import uuid4

import addon_utils
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bridge_check_helpers', Path(__file__).with_name('bridge_check.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def near(a, b):
    assert (Vector(a) - Vector(b)).length < 2e-4, (tuple(a), tuple(b))


class Check(helpers.Check):
    def start_server(self):
        self.process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-u', '-m', 'companion.main', '--synthetic'],
                                        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
        def reader():
            for line in self.process.stdout:
                self.logs.put(line.rstrip())
        threading.Thread(target=reader, daemon=True).start()

    def line(self, text):
        self.process.stdin.write(text + '\n')
        self.process.stdin.flush()

    def frame(self, uv=(.5, .5), pinch=False, present=True):
        self.send({'type': 'hand_frame', 'payload': dict(u=uv[0] if present else None, v=uv[1] if present else None, present=present, pinching=pinch)})

    def gesture(self, kind, identifier, uv):
        payload = dict(gesture_id=identifier)
        payload.update(reason='synthetic cancel') if kind == 'cancel' else payload.update(u=uv[0], v=uv[1])
        self.send({'type': 'gesture_' + kind, 'payload': payload})

    def obj(self):
        return self.window.scene.objects[self.name]

    def position(self):
        return self.obj().matrix_world.translation.copy()

    def uv(self):
        point = location_3d_to_region_2d(self.region, self.area.spaces.active.region_3d, self.position())
        assert point is not None
        return point.x / self.region.width, 1 - point.y / self.region.height

    def runtime(self):
        return self.module.bridge._runtime

    def sequence(self):
        self.window.scene.cursor.location = (0, 0, 0)
        self.line('create cube')
        yield .2
        self.name = self.window.view_layer.objects.active.name
        self.obj().rotation_euler = (.3, .2, .4)
        self.obj().scale = (1.2, .7, 1.5)
        with self.override():
            bpy.ops.ed.undo_push(message='Disposable rotated scaled baseline')
        for perspective in ('PERSP', 'ORTHO'):
            rv = self.area.spaces.active.region_3d
            rv.view_location = (0, 0, 0)
            rv.view_rotation = Quaternion((1, 0, 0, 0))
            rv.view_distance = 12
            rv.view_perspective = perspective
            self.area.tag_redraw()
            yield .15
            baseline = self.position()
            basis = self.obj().matrix_world.to_3x3().copy()
            start = self.uv()
            end = (start[0] + .06, start[1] - .03)
            self.frame(start)
            yield .12
            assert self.runtime().hovered == self.name
            near(self.position(), baseline)
            assert self.module.bridge.viewport.pixels(self.region, (0, 0)) == (0, self.region.height)
            assert self.module.bridge.viewport.pixels(self.region, (1, 1)) == (self.region.width, 0)
            # A pinching frame never starts an edit.
            self.frame(end, True)
            yield .1
            assert self.runtime().drag is None
            near(self.position(), baseline)
            self.frame(start)
            identifier = str(uuid4())
            self.gesture('start', identifier, start)
            yield .12
            assert self.runtime().phase == 'DRAGGING'
            near(self.position(), baseline)
            with self.override():
                assert not bpy.ops.air_modeler.create_primitive.poll()
            before_count = len(self.objects())
            self.line('create sphere')
            self.line('rotate x')
            self.frame(end, True)
            yield .12
            moved = self.position()
            assert (moved - baseline).length > .1
            assert len(self.objects()) == before_count
            assert max(abs(self.obj().matrix_world[i][j] - basis[i][j]) for i in range(3) for j in range(3)) < 1e-5
            self.frame(end, True)
            yield .12
            near(self.position(), moved)  # no drift
            self.gesture('end', str(uuid4()), start)
            self.gesture('start', identifier, end)
            self.frame(end, True)
            yield .1
            assert self.runtime().phase == 'DRAGGING'
            near(self.position(), moved)
            self.frame(pinch=True, present=False)
            yield .12
            assert not self.runtime().tracking
            near(self.position(), moved)
            self.frame(end, True)
            yield .1
            assert self.runtime().phase == 'DRAGGING'
            final_uv = (end[0] + .025, end[1])
            expected = self.runtime().drag.baseline.translation + (self.module.bridge.viewport.plane_point(self.runtime().drag.view, final_uv, self.runtime().drag.point, self.runtime().drag.normal) - self.runtime().drag.grab)
            self.gesture('end', identifier, final_uv)
            yield .12
            near(self.position(), expected)
            assert self.runtime().phase == 'IDLE'
            self.gesture('end', identifier, start)
            self.gesture('start', identifier, start)
            yield .1
            assert self.runtime().drag is None
            near(self.position(), expected)
            first = self.position()
            start2 = self.uv()
            identifier2 = str(uuid4())
            self.frame(start2)
            self.gesture('start', identifier2, start2)
            yield .1
            self.gesture('end', identifier2, (start2[0] + .04, start2[1]))
            yield .12
            assert (self.position() - first).length > .1
            self.line('undo')
            yield .15
            near(self.position(), first)
            self.line('undo')
            yield .15
            near(self.position(), baseline)
            assert max(abs(self.obj().matrix_world[i][j] - basis[i][j]) for i in range(3) for j in range(3)) < 1e-5
            print('PASS', perspective, 'rotated/scaled hover, no jump/drift, final coordinates, ID isolation, brief loss, two separate Undo steps', flush=True)
            # Missed pinch does not acquire the selected target later.
            self.frame((.98, .98))
            self.gesture('start', str(uuid4()), (.98, .98))
            yield .1
            self.frame(self.uv(), True)
            yield .1
            assert self.runtime().phase == 'NEEDS_RELEASE' and self.runtime().drag is None
            near(self.position(), baseline)
            # All interruption paths restore the preview and gate restart.
            for reason in ('cancel', 'command', 'loss', 'stale', 'disconnect'):
                self.frame(self.uv())
                yield .1
                gid = str(uuid4())
                start = self.uv()
                self.gesture('start', gid, start)
                yield .1
                self.frame((start[0] + .05, start[1]), True)
                yield .1
                assert (self.position() - baseline).length > .1
                if reason == 'cancel':
                    self.gesture('cancel', gid, start)
                elif reason == 'command':
                    self.line('cancel')
                elif reason == 'loss':
                    for _ in range(6):
                        self.frame(pinch=True, present=False)
                        yield .1
                elif reason == 'stale':
                    yield .6
                elif reason == 'disconnect':
                    old = self.runtime()
                    self.module.bridge.disconnect()
                    assert old.timer is None and old.draw_handler is None and old.sock.fileno() == -1
                    yield .1
                    self.ready = None
                    self.connect()
                    yield .2
                yield .1
                near(self.position(), baseline)
                assert self.runtime().phase == 'NEEDS_RELEASE'
                self.frame(start, True)
                self.gesture('start', str(uuid4()), start)
                self.gesture('end', gid, (start[0] + .2, start[1]))
                yield .1
                assert self.runtime().drag is None
                near(self.position(), baseline)
            print('PASS', perspective, 'miss, cancellation, loss, stale stream, disconnect, release gate', flush=True)
        # Crossing a second target never changes the locked target.
        self.frame(self.uv())
        self.window.scene.cursor.location = (3, 0, 0)
        self.line('create sphere')
        yield .15
        second = self.window.view_layer.objects.active.name
        second_position = self.window.scene.objects[second].location.copy()
        start = self.uv()
        gid = str(uuid4())
        self.gesture('start', gid, start)
        yield .1
        point = location_3d_to_region_2d(self.region, self.area.spaces.active.region_3d, second_position)
        self.frame((point.x / self.region.width, 1 - point.y / self.region.height), True)
        yield .1
        assert self.runtime().target().name == self.name
        near(self.window.scene.objects[second].location, second_position)
        # Undo while dragging restores preview before undoing previous spawn.
        self.line('undo')
        yield .15
        near(self.position(), baseline)
        assert second not in self.window.scene.objects
        # Unchanged and cancelled gestures must not consume modeling undo.
        self.frame(self.uv())
        self.line('create sphere')
        yield .15
        disposable = self.window.view_layer.objects.active.name
        self.window.view_layer.objects.active = self.obj()
        gid = str(uuid4())
        self.gesture('start', gid, self.uv())
        yield .1
        self.gesture('end', gid, self.uv())
        yield .1
        self.gesture('start', str(uuid4()), self.uv())
        yield .1
        self.frame((self.uv()[0] + .03, self.uv()[1]), True)
        yield .1
        self.line('cancel')
        yield .1
        self.line('undo')
        yield .15
        assert disposable not in self.window.scene.objects
        near(self.position(), baseline)
        # Active previews restore through file-load, viewport, and disable hooks.
        for reason in ('load', 'viewport', 'disable'):
            self.frame(self.uv())
            yield .1
            self.gesture('start', str(uuid4()), self.uv())
            yield .1
            self.frame((self.uv()[0] + .03, self.uv()[1]), True)
            yield .1
            assert (self.position() - baseline).length > .1
            old = self.runtime()
            if reason == 'load':
                self.module.bridge.on_load_pre(None)
            elif reason == 'viewport':
                self.area.type = 'CONSOLE'
            else:
                addon_utils.disable('air_modeler', default_set=False)
            yield .12
            assert self.runtime() is None
            assert old.draw_handler is None and old.timer is None and old.sock.fileno() == -1
            near(self.position(), baseline)
            if reason == 'viewport':
                self.area.type = 'VIEW_3D'
                self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
            if reason == 'disable':
                self.module = addon_utils.enable('air_modeler', default_set=False)
            self.connect()
            yield .2
        print('PASS unchanged/cancelled gestures add no undo; active file-load hook, lost viewport and disable restore', flush=True)
        # Leaving Object Mode and invalid viewport cancel via the controller.
        self.frame(self.uv())
        yield .1
        self.gesture('start', str(uuid4()), self.uv())
        yield .1
        self.frame((self.uv()[0] + .04, self.uv()[1]), True)
        yield .1
        old = self.runtime()
        with self.override():
            bpy.ops.object.mode_set(mode='EDIT')
        yield .15
        assert self.runtime() is None and old.draw_handler is None
        with self.override():
            bpy.ops.object.mode_set(mode='OBJECT')
        near(self.position(), baseline)
        self.connect()
        yield .2
        for _ in range(2):
            old = self.runtime()
            assert old is not None, self.module.bridge.ui_state()
            addon_utils.disable('air_modeler', default_set=False)
            assert old.timer is None and old.draw_handler is None and old.sock.fileno() == -1
            self.module = addon_utils.enable('air_modeler', default_set=False)
            assert bpy.app.handlers.load_pre.count(self.module.bridge.on_load_pre) == 1
            self.connect()
            yield .2
        print('PASS target lock, Undo during drag, Object Mode exit, disable/re-enable resource cleanup', flush=True)
        self.line('quit')
        yield .2
        assert self.runtime() is None
        print('PASS real TCP MOVE milestone', flush=True)

    def step(self):
        while not self.logs.empty():
            line = self.logs.get_nowait()
            print('PEER', line, flush=True)
            if line.startswith('Listening') and self.stage == 'startup':
                self.connect()
                self.stage = 'handshake'
            if line.startswith('READY session='):
                self.ready = line.split('=', 1)[1]
        assert time.monotonic() < self.deadline, 'MOVE check timeout'
        if self.stage == 'handshake' and self.ready:
            self.steps = self.sequence()
            self.next_step = 0
            self.stage = 'run'
        if self.stage == 'run' and time.monotonic() >= self.next_step:
            try:
                self.next_step = time.monotonic() + next(self.steps)
            except StopIteration:
                addon_utils.disable('air_modeler', default_set=False)
                self.process.wait(timeout=3)
                bpy.ops.wm.quit_blender()
                return None
        return .02


check = Check() if __name__ == "__main__" else None
if check is not None:
    check.deadline = time.monotonic() + 60

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

if check is not None:
    bpy.app.timers.register(advance, first_interval=.2)
