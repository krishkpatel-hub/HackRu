"""Real-TCP transform checks in a disposable foreground Blender process."""
import importlib.util
import math
import os
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4
from dataclasses import replace

import addon_utils
import bpy
from mathutils import Matrix, Quaternion

spec = importlib.util.spec_from_file_location('move_helpers', Path(__file__).with_name('move_check.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def matrix_near(actual, expected):
    error = max(abs(actual[i][j] - expected[i][j]) for i in range(4) for j in range(4))
    assert error < 3e-5, (error, actual, expected)


def expected(initial, mode, axis, start, end, rotation=math.tau, scaling=math.log(10)):
    origin = initial.translation
    if mode == 'ROTATE':
        delta = Matrix.Rotation(rotation * (end[0] - start[0]), 4, axis)
    else:
        factor = max(.1, min(10, math.exp(scaling * (start[1] - end[1]))))
        delta = Matrix.Diagonal((factor, factor, factor, 1))
    return Matrix.Translation(origin) @ delta @ Matrix.Translation(-origin) @ initial


class Check(helpers.Check):
    # Synthetic camera heartbeat during ordinary waits. Explicit stale tests
    # disable it; absent-hand frames remain absent. Do not relax production loss.
    heartbeat = None
    heartbeat_enabled = True
    heartbeat_due = 0.0

    def frame(self, uv=(.5,.5), pinch=False, present=True):
        self.heartbeat = (uv,pinch,present)
        self.heartbeat_due = time.monotonic() + .04
        super().frame(uv,pinch,present)

    def gesture(self, kind, identifier, uv):
        super().gesture(kind,identifier,uv)
        if kind == 'start' and (self.runtime().drag is None or self.runtime().drag.identifier == identifier):
            self.heartbeat = (uv,True,True)
        elif kind == 'end' and self.runtime().drag and self.runtime().drag.identifier == identifier:
            self.heartbeat = (uv,False,True)

    def step(self):
        if self.stage == 'run' and self.heartbeat_enabled and self.heartbeat and time.monotonic() >= self.heartbeat_due:
            super().frame(*self.heartbeat)
            self.heartbeat_due = time.monotonic() + .04
        return super().step()

    def wait_for(self, predicate, label):
        deadline = time.monotonic() + 2
        while not predicate():
            assert time.monotonic() < deadline, label
            yield .02

    def wait_matrix(self, wanted):
        yield from self.wait_for(
            lambda: max(abs(self.obj().matrix_world[i][j]-wanted[i][j]) for i in range(4) for j in range(4)) < 3e-5,
            'Timed out waiting for expected transform after TCP delivery')

    def sequence(self):
        self.window.scene.cursor.location = (2, -1, .5)
        self.line('create cube')
        yield .2
        self.name = self.window.view_layer.objects.active.name
        self.obj().rotation_euler = (.31, -.24, .43)
        self.obj().scale = (1.2, .7, 1.5)
        rv = self.area.spaces.active.region_3d
        rv.view_location = self.position()
        rv.view_rotation = Quaternion((1, 0, 0, 0))
        rv.view_distance = 16
        self.area.tag_redraw()
        yield .15
        with self.override():
            bpy.ops.ed.undo_push(message='Transform baseline')
        original = self.obj().matrix_world.copy()
        for view in ('PERSP', 'ORTHO'):
            rv.view_perspective = view
            self.area.tag_redraw()
            yield .15
            for command, mode, axis in (('rotate x', 'ROTATE', 'X'), ('rotate y', 'ROTATE', 'Y'),
                                         ('rotate', 'ROTATE', 'Z'), ('scale', 'SCALE', 'Z')):
                baseline = self.obj().matrix_world.copy()
                self.line(command)
                self.frame(self.uv())
                yield .12
                armed_axis='FREE' if command=='rotate' else axis
                yield from self.wait_for(lambda: self.runtime().mode == mode and self.runtime().axis == armed_axis, 'mode/axis command delivery')
                assert self.runtime().axis == armed_axis
                start = self.uv()
                gid = str(uuid4())
                self.gesture('start', gid, start)
                yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid, 'gesture START delivery')
                yield from self.wait_matrix(baseline)
                end = (start[0] + .10, start[1] - .15)
                self.frame(end, True)
                yield .12
                wanted = expected(baseline, mode, axis, start, end)
                yield from self.wait_matrix(wanted)
                helpers.near(self.position(), baseline.translation)
                if mode == 'ROTATE':
                    for column in range(3):
                        assert abs(self.obj().matrix_world.col[column].xyz.length - baseline.col[column].xyz.length) < 1e-5
                self.line('move')
                self.line('create sphere')
                self.frame(end, True)
                yield .12
                assert self.runtime().mode == mode and len(self.objects()) == 1
                yield from self.wait_matrix(wanted)  # stationary: no drift
                self.gesture('end', str(uuid4()), start)
                self.gesture('start', gid, end)
                self.frame(pinch=True, present=False)
                yield .12
                yield from self.wait_matrix(wanted)
                self.frame(start, True)
                yield .12
                yield from self.wait_matrix(baseline)  # return to start
                final_uv = (start[0] - .075, start[1] + .13)
                self.gesture('end', gid, final_uv)
                yield from self.wait_for(lambda: self.runtime().drag is None, 'gesture END delivery')
                final = expected(baseline, mode, axis, start, final_uv)
                yield from self.wait_matrix(final)
                assert self.runtime().mode == 'MOVE' and self.runtime().phase == 'IDLE'
                # Next pinch performs MOVE, independently undoable from transform.
                next_start = self.uv()
                gid2 = str(uuid4())
                self.gesture('start', gid2, next_start)
                yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid2, 'MOVE START delivery')
                self.gesture('end', gid2, (next_start[0] + .025, next_start[1]))
                yield from self.wait_for(lambda: self.runtime().drag is None, 'MOVE END delivery')
                assert (self.position() - baseline.translation).length > .1
                self.line('undo')
                yield .12
                yield from self.wait_matrix(final)
                self.line('undo')
                yield .12
                yield from self.wait_matrix(baseline)
                print('PASS', view, command, 'world matrix, origin/scale, no drift, final coordinates, shared ID/freeze lifecycle, MOVE reset, two Undo steps', flush=True)
            # Reacquire RNA invalidated by Undo.
            rv = self.area.spaces.active.region_3d
        for command in ('rotate y', 'scale'):
            for reason in ('cancel', 'loss', 'stale', 'disconnect'):
                self.frame(self.uv())
                self.line(command)
                yield .12
                baseline = self.obj().matrix_world.copy()
                start = self.uv()
                gid = str(uuid4())
                self.gesture('start', gid, start)
                yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid, 'gesture START delivery')
                self.frame((start[0] + .08, start[1] - .15), True)
                yield .12
                assert self.runtime().drag is not None
                if reason == 'cancel':
                    self.gesture('cancel', gid, start)
                elif reason == 'loss':
                    for _ in range(6):
                        self.frame(pinch=True, present=False)
                        yield .1
                elif reason == 'stale':
                    self.heartbeat_enabled = False
                    yield .6
                    self.heartbeat_enabled = True
                elif reason == 'disconnect':
                    self.module.bridge.disconnect()
                    yield .12
                    self.connect()
                    yield .2
                yield .12
                yield from self.wait_matrix(baseline)
                assert self.runtime().mode == 'MOVE' and self.runtime().phase == 'NEEDS_RELEASE'
                self.frame(start, True)
                self.gesture('start', str(uuid4()), start)
                yield .1
                assert self.runtime().drag is None
            self.frame(self.uv())
            self.line(command)
            yield .12
            mode = self.runtime().mode
            self.gesture('start', str(uuid4()), (.98, .98))
            yield .12
            self.frame(self.uv(), True)
            yield .12
            assert self.runtime().drag is None and self.runtime().mode == mode
            self.frame(self.uv())
            yield .1
            # Unchanged and cancelled transforms add no history entries.
            self.window.scene.cursor.location = (8, 0, 0)
            self.line('create sphere')
            yield from self.wait_for(lambda: len(self.objects()) == 2, 'sentinel spawn delivery')
            sphere = self.window.view_layer.objects.active.name
            gid = str(uuid4())
            self.gesture('start', gid, self.uv())
            yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid, 'unchanged START delivery')
            self.gesture('end', gid, self.uv())
            yield from self.wait_for(lambda: self.runtime().drag is None, 'gesture END delivery')
            self.line(command)
            yield .1
            self.gesture('start', str(uuid4()), self.uv())
            yield .1
            self.frame((self.uv()[0] + .05, self.uv()[1] - .1), True)
            yield .1
            self.line('undo')  # cancel preview first, undo sphere creation
            yield .12
            yield from self.wait_for(lambda: sphere not in self.window.scene.objects, 'sentinel Undo delivery')
            yield from self.wait_matrix(original)
            print('PASS', command, 'cancel/loss/stale/disconnect, release gate, missed pinch retains mode, unchanged release and Undo during drag', flush=True)
        # High test sensitivity reaches both factor bounds using valid u/v.
        module = self.module.bridge.transforms
        config = module.CONFIG
        module.CONFIG = replace(config, scale_sensitivity=20)
        self.frame(self.uv())
        self.line('scale')
        yield .12
        start = self.uv()
        gid = str(uuid4())
        self.gesture('start', gid, start)
        yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid, 'gesture START delivery')
        assert self.runtime().drag.config.scale_sensitivity == 20
        module.CONFIG = config  # active drag must retain captured sensitivity
        for v, factor in ((0, 10), (1, .1), (start[1], 1)):
            self.frame((start[0], v), True)
            yield .12
            wanted = Matrix.Diagonal((factor, factor, factor, 1)) @ original
            wanted.translation = original.translation
            yield from self.wait_matrix(wanted)
            assert abs(self.runtime().drag.amount - factor) < 1e-5
        self.gesture('end', gid, start)
        yield from self.wait_for(lambda: self.runtime().drag is None, 'gesture END delivery')
        # Negative scale signs must survive Blender's matrix setter, too.
        self.obj().scale = (-1.2, .7, 1.5)
        yield .1
        reflected = self.obj().matrix_world.copy()
        for rotation_mode in ('XYZ', 'QUATERNION', 'AXIS_ANGLE'):
            self.obj().rotation_mode = rotation_mode
            for command, mode in (('rotate x', 'ROTATE'), ('scale', 'SCALE')):
                self.line(command)
                self.frame(self.uv())
                yield .12
                start = self.uv()
                gid = str(uuid4())
                self.gesture('start', gid, start)
                yield from self.wait_for(lambda: self.runtime().drag is not None and self.runtime().drag.identifier == gid, 'gesture START delivery')
                end = (start[0] + .075, start[1] - .1)
                self.frame(end, True)
                yield .12
                yield from self.wait_matrix(expected(reflected, mode, 'X', start, end))
                assert tuple(v < 0 for v in self.obj().scale) == (True, False, False)
                self.gesture('end', gid, end)
                yield from self.wait_for(lambda: self.runtime().drag is None, 'gesture END delivery')
                yield from self.wait_matrix(expected(reflected, mode, 'X', start, end))
                assert tuple(v < 0 for v in self.obj().scale) == (True, False, False)
                # Restore a known baseline outside history for the next case.
                self.module.bridge.transforms.apply_matrix(self.obj(), reflected, (-1, 1, 1))
                yield .1
        print('PASS negative scale signs and world matrices in Euler/quaternion/axis-angle modes', flush=True)
        self.line('extrude')
        yield from self.wait_for(lambda: self.runtime().mode == 'EXTRUDE', 'extrude mode delivery')
        assert self.runtime().mode == 'EXTRUDE'
        print('PASS scale bounds, captured config, unchanged release, extrusion mode arming', flush=True)
        self.heartbeat_enabled = False
        self.line('quit')
        yield from self.wait_for(lambda: self.runtime() is None, 'shutdown delivery')
        assert self.runtime() is None
        print('PASS real TCP ROTATE/SCALE milestone', flush=True)


check = Check()
check.deadline = time.monotonic() + 90

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
