"""Disposable foreground real-runner/TCP tests for selectors and precise edits."""
import importlib.util
import math
import os
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4
import bpy
from mathutils import Matrix


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

helpers=load('move_helpers','move_check.py')
geometry=load('geometry_helpers','extrusion_geometry_check.py')


def same(a,b):
    return max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4)) < 4e-5


class Check(helpers.Check):
    def until(self, predicate, label, timeout=2):
        deadline=time.monotonic()+timeout
        while not predicate():
            assert time.monotonic()<deadline, label
            yield .04

    def selector(self,pose):
        self.send({'type':'selector_frame','payload':dict(pose=pose,manipulator='Right',selector='Left')})

    def confirm(self,pose):
        for _ in range(5):
            self.selector(pose); self.frame(self.uv()); yield .1

    def aim(self,index):
        obj=self.obj(); polygon=obj.data.polygons[index]
        center=obj.matrix_world@polygon.center
        normal=(obj.matrix_world.to_3x3().inverted().transposed()@polygon.normal).normalized()
        rv=self.area.spaces.active.region_3d
        rv.view_location=center; rv.view_rotation=normal.to_track_quat('Z','Y')
        rv.view_distance=14; rv.view_perspective='ORTHO'; self.area.tag_redraw()
        return center,normal

    def sequence(self):
        assert self.module.bl_info['version']==(0,8,0)
        self.line('create cube'); yield .3
        self.name=self.window.view_layer.objects.active.name
        self.obj().rotation_euler=(.3,-.2,.4); self.obj().scale=(1.2,.7,1.5)
        yield .1
        with self.override(): bpy.ops.ed.undo_push(message='Precision test baseline')
        baseline=self.obj().matrix_world.copy()
        # No hand observations have been sent. Idle cancellation/reconnect must
        # leave typed-only precision usable rather than manufacturing a gate.
        self.line('rotate x')
        yield from self.until(lambda:self.runtime().override, 'arm before idle cancel')
        self.line('cancel')
        yield from self.until(lambda:not self.runtime().override, 'idle cancel clears override')
        for stage in ('idle cancel', 'idle reconnect'):
            if stage == 'idle reconnect':
                old = self.runtime()
                self.module.bridge.disconnect()
                assert old.timer is None and old.draw_handler is None and old.sock.fileno() == -1
                assert not self.module.bridge._needs_release
                yield .12
                self.ready = None
                self.connect()
                yield from self.until(lambda:self.ready is not None, 'typed-only reconnect READY')
            assert self.runtime().phase == 'IDLE'
            expected = baseline.copy(); expected.translation.x += .75
            self.line('move x 0.75 units')
            yield from self.until(lambda:same(self.obj().matrix_world,expected), 'typed precision after '+stage)
            self.line('undo')
            yield from self.until(lambda:same(self.obj().matrix_world,baseline), 'single Undo after '+stage)
        print('PASS typed-only idle cancel/reconnect precision without hand observations',flush=True)
        for phrase,mode,axis,value in [('rotate x 45 degrees','ROTATE','X',45),
                ('rotate y -30 degrees','ROTATE','Y',-30),('rotate z 45 degrees','ROTATE','Z',45),
                ('move x -2 units','MOVE','X',-2),('move y 2 units','MOVE','Y',2),
                ('scale by 1.5','SCALE','Z',1.5),('scale by 0.5','SCALE','Z',.5)]:
            expected=baseline.copy()
            if mode=='MOVE': expected.translation['XYZ'.index(axis)]+=value
            else:
                delta=Matrix.Rotation(math.radians(value),4,axis) if mode=='ROTATE' else Matrix.Diagonal((value,value,value,1))
                expected=Matrix.Translation(baseline.translation)@delta@Matrix.Translation(-baseline.translation)@baseline
            self.line(phrase)
            yield from self.until(lambda:same(self.obj().matrix_world,expected),phrase)
            self.line('undo')
            yield from self.until(lambda:same(self.obj().matrix_world,baseline),'one Undo '+phrase)
        print('PASS numeric world-axis/origin, signed displacement, scale up/down and individual Undo',flush=True)
        # Fresh IDs intentionally repeat; duplicate UUID executes once.
        event=dict(type='command',payload=dict(id=str(uuid4()),action='precision',mode='MOVE',axis='Z',value=1))
        self.send(event); self.send(event); yield .25
        wanted=baseline.copy(); wanted.translation.z+=1
        assert same(self.obj().matrix_world,wanted)
        self.line('move z 1 units'); yield .2
        wanted.translation.z+=1; assert same(self.obj().matrix_world,wanted)
        self.line('undo'); yield .2; self.line('undo')
        yield from self.until(lambda:same(self.obj().matrix_world,baseline),'two precise undos')
        # No selection / Edit Mode reject without edits.
        self.obj().select_set(False); self.line('move x 2 units'); yield .15
        assert same(self.obj().matrix_world,baseline)
        self.obj().select_set(True)
        with self.override(): bpy.ops.object.mode_set(mode='EDIT')
        self.line('scale by 1.5'); yield .15
        with self.override(): bpy.ops.object.mode_set(mode='OBJECT')
        assert same(self.obj().matrix_world,baseline)
        # Sidebar values do not mutate; Apply uses same inner Undo operator.
        with self.override():
            v=bpy.context.window_manager.air_modeler_precision
            v.mode='MOVE'; v.axis='X'; v.distance=2
            assert same(self.obj().matrix_world,baseline)
            assert bpy.ops.air_modeler.precision_reset()=={'FINISHED'}
            assert same(self.obj().matrix_world,baseline)
            v.mode='MOVE'; v.axis='X'; v.distance=2
            assert bpy.ops.air_modeler.precision_apply('EXEC_DEFAULT', True)=={'FINISHED'}
        self.line('undo')
        yield from self.until(lambda:same(self.obj().matrix_world,baseline),'sidebar single Undo')
        print('PASS UUID dedup/repeats, context rejection, sidebar staging/cancel/shared commit',flush=True)
        self.aim(next(p.index for p in self.obj().data.polygons if p.normal.z>.9)); yield .15
        for pose,mode in [('TWO','ROTATE'),('THREE','SCALE'),('OPEN','EXTRUDE'),('FIST','MOVE')]:
            yield from self.confirm(pose)
            assert self.runtime().mode==mode, (pose,self.runtime().mode_label())
        # Confirm SCALE, then voice overrides one operation with world X rotation.
        yield from self.confirm('THREE')
        self.line('rotate x'); self.frame((.5,.5)); yield .15
        assert self.runtime().override and self.runtime().axis=='X'
        gid=str(uuid4()); self.gesture('start',gid,(.5,.5)); yield .12
        assert self.runtime().drag.mode=='ROTATE'
        self.selector('OPEN'); self.frame((.55,.45),True); yield .12
        assert self.runtime().drag.mode=='ROTATE' and self.runtime().drag.axis=='X'
        self.line('move x 2 units'); yield .1
        assert self.runtime().drag is not None
        with self.override(): assert not bpy.ops.air_modeler.precision_apply.poll()
        self.gesture('end',gid,(.55,.45)); yield .15
        assert not self.runtime().override
        self.line('undo')
        yield from self.until(lambda:same(self.obj().matrix_world,baseline),'override Undo')
        yield from self.confirm('THREE'); assert self.runtime().mode=='SCALE'
        # Sustained loss cancels once and requires released manipulation hand.
        gid=str(uuid4()); self.gesture('start',gid,(.5,.5)); yield .12
        self.frame((.5,.4),True); yield .1
        self.frame(pinch=True,present=False); yield .2
        assert self.runtime().drag is not None
        self.selector('OPEN'); yield .4
        assert self.runtime().drag is None and self.runtime().phase=='NEEDS_RELEASE'
        assert same(self.obj().matrix_world,baseline)
        self.line('cancel'); yield .12
        assert self.runtime().phase=='NEEDS_RELEASE', 'idle cancel must preserve an existing loss gate'
        self.frame((.5,.5),True); yield .1; assert self.runtime().phase=='NEEDS_RELEASE'
        self.frame((.5,.5)); yield .1; assert self.runtime().phase=='IDLE'
        print('PASS selector debounce, voice precedence, drag locking, loss and release gate',flush=True)
        # Numeric extrusion must not choose a hover until pinch; lock amount.
        index=next(p.index for p in self.obj().data.polygons if p.normal.z>.9)
        center,normal=self.aim(index); yield .15
        mesh_before=geometry.snapshot(self.obj().data)
        for cancel in (True,False):
            self.line('extend 0.5 units'); yield .15
            assert geometry.snapshot(self.obj().data)==mesh_before
            assert self.runtime().fixed_distance==.5
            self.frame((.5,.5)); gid=str(uuid4()); self.gesture('start',gid,(.5,.5)); yield .15
            assert self.runtime().drag.amount==.5
            self.selector('FIST'); self.frame((.55,.65),True); yield .12
            assert self.runtime().drag.amount==.5
            if cancel:
                self.line('cancel'); yield .15
                assert geometry.snapshot(self.obj().data)==mesh_before
                assert self.runtime().fixed_distance is None
                self.frame((.5,.5)); yield .12
            else:
                self.gesture('end',gid,(.55,.65)); yield .2
                geometry.inspect(self.obj().data)
                cap=max(self.obj().data.polygons,key=lambda p:(self.obj().matrix_world@p.center).dot(normal))
                helpers.near(self.obj().matrix_world@cap.center,center+normal*.5)
                self.line('undo')
                yield from self.until(lambda:geometry.snapshot(self.obj().data)==mesh_before,'fixed extrusion Undo')
        print('PASS fixed distance, no hover edit, exact cancel and single geometry Undo',flush=True)
        self.line('quit'); yield .3
        assert self.runtime() is None
        print('PASS precision/selector real TCP integration',flush=True)

check=Check(); check.deadline=time.monotonic()+90

def advance():
    try: return check.step()
    except Exception:
        traceback.print_exc()
        if check.process: check.process.terminate()
        sys.stdout.flush(); sys.stderr.flush(); os._exit(1)

bpy.app.timers.register(advance,first_interval=.2)
