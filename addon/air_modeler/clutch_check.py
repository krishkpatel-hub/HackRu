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


def observed(uv=(.5,.5), **changes):
    value=dict(valid=True,confidence=.99,u=uv[0],v=uv[1],palm_u=.5,palm_v=.5,
        pinching=False,open=True,gesture_id=None,event='NONE',shape_valid=True,shape_error=None,
        angle=0.,openness=1.,open_palm=True,extrude_pose=True,pinch_pending=False)
    value.update(changes)
    angle=value['angle']
    value['orientation']=changes.get('orientation',[math.cos(angle/2),0.,0.,math.sin(angle/2)] if angle is not None else None)
    value['fingers']=changes.get('fingers',[value['openness']]*4 if value['shape_valid'] else None)
    return value


def absent():
    return observed((None,None),valid=False,confidence=0,palm_u=None,palm_v=None,open=False,
        shape_valid=False,shape_error='Hand absent or uncertain',angle=None,openness=None,
        open_palm=False,extrude_pose=False)


def palm(u=.5,v=.5,angle=0.,openness=1.):
    return observed(palm_u=u,palm_v=v,angle=angle,openness=openness,
        open_palm=openness>=.72,extrude_pose=openness>=.72)


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
        self.send(dict(type='hands_frame', payload=dict(profile='left_clutch_v3',aspect=4/3,frame_id=self.capture_id,
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

    def right_pinch(self, uv=(.5,.5), event='NONE', gid=None):
        if event=='START': self.right_gid=gid or str(uuid4())
        self.capture(right=observed(uv,open=event=='END',pinching=event!='END',
            gesture_id=gid or self.right_gid,event=event,openness=.8,fingers=[.2,1.,1.,1.],open_palm=False,
            extrude_pose=True,pinch_pending=event!='END'))

    def arm_extrusion(self, phrase, index):
        center,normal=self.aim(index)
        # Aim Left at the OPPOSITE side; intended drag must still select the
        # hidden requested face rather than either hand's raycast.
        opposite=min(range(len(self.obj().data.polygons)),key=lambda i:
            (self.obj().matrix_world.to_3x3().inverted().transposed()@self.obj().data.polygons[i].normal).normalized().dot(normal))
        self.aim(opposite)
        yield .12
        yield from self.idle()
        before=geometry.snapshot(self.obj().data)
        if phrase:
            if phrase.startswith('extend '):
                self.line('extrude plane xz axis z')
                yield from self.until(lambda:self.runtime().plane=='XZ','fixed distance plane selection')
            self.line(phrase)
            yield from self.until(lambda:self.runtime().override and self.runtime().mode=='EXTRUDE',phrase)
        assert geometry.snapshot(self.obj().data)==before
        yield from self.start(right=palm(),uv=(.5,.5))
        assert self.runtime().drag.face_index is None and not self.runtime().face_outline
        self.right_pinch(event='START')
        yield from self.lock('EXTRUDE')
        assert self.runtime().drag.geometry is None
        self.mapped_vector(normal*.35)
        yield from self.until(lambda:self.runtime().drag.face_index is not None,'automatic face lock')
        assert self.runtime().drag.face_index==index and self.runtime().face_outline
        assert geometry.snapshot(self.obj().data)==before,'direction lock mutated topology'
        yield .15
        return center,normal

    def mapped_vector(self, vector, event='NONE'):
        drag=self.runtime().drag
        du=Vector(vector).dot(Vector(drag.plane.horizontal))/drag.plane.sensitivity/drag.aspect
        dv=-Vector(vector).dot(Vector(drag.plane.vertical))/drag.plane.sensitivity
        uv=drag.pinch_reference[0]+du,drag.pinch_reference[1]+dv
        self.right_pinch(uv,event)
        return uv

    def sequence(self):
        assert self.module.bl_info['version']==(0,9,0)
        self.window.scene.cursor.location=(0,0,0)
        self.line('create cube')
        yield from self.until(lambda:len(self.objects())==1,'spawn cube')
        self.name=self.window.view_layer.objects.active.name
        self.obj().rotation_euler=(.2,-.25,.3)
        self.obj().scale=(1.2,.8,1.5)
        rv=self.area.spaces.active.region_3d
        rv.view_location=(0,0,0);rv.view_rotation=Quaternion((1,0,0,0));rv.view_distance=12;rv.view_perspective='ORTHO'
        yield .15
        with self.override(): bpy.ops.ed.undo_push(message='Whole-hand baseline')
        baseline=self.obj().matrix_world.copy()

        # Right-only pinch and large open-palm motion cannot select or edit.
        self.capture(left=absent(),right=observed(self.uv(),event='START',gesture_id=str(uuid4()),pinching=True,open=False,pinch_pending=True))
        yield .2
        self.capture(right=palm(.8,.3,angle=.8,openness=.8));yield .25
        assert self.runtime().drag is None and same(self.obj().matrix_world,baseline)
        assert self.runtime().phase=='IDLE'
        yield from self.idle()
        # Sentinel proves unchanged selection adds no Undo. Left moves a LOT.
        self.window.scene.cursor.location=(4,0,0);self.line('create sphere')
        yield from self.until(lambda:len(self.objects())==2,'sentinel')
        sentinel=self.window.view_layer.objects.active.name
        yield from self.start()
        for uv in ((.1,.1),(.9,.9),(.9,.1),(.1,.9)):
            self.owner_at(uv);yield .18
            assert self.runtime().phase=='SELECTED_READY' and same(self.obj().matrix_world,baseline)
        self.line('move x 2 units');self.line('scale');self.line('create prism');yield .12
        assert len(self.objects())==2 and self.runtime().phase=='SELECTED_READY'
        with self.override(): assert not bpy.ops.air_modeler.precision_apply.poll()
        yield from self.release((.1,.9))
        self.line('undo')
        yield from self.until_stable(lambda:sentinel not in self.window.scene.objects and same(self.obj().matrix_world,baseline),'stationary no Undo',settle=.2)
        print('PASS revised Right-only input rejected; large Left motion inert; stationary selection/conflicts/no Undo',flush=True)

        # Two right-palm moves commit with Left END and undo separately.
        completed=[]
        for offset in (.08,.10):
            before=self.obj().matrix_world.copy()
            yield from self.start()
            self.capture(right=palm(.55,.5));yield from self.lock('MOVE')
            assert same(self.obj().matrix_world,before),'MOVE activation jumped'
            self.capture(right=palm(.5+offset,.46))
            moved=yield from self.wait_move((.5+offset,.46),'Right palm MOVE')
            self.owner_at((.9,.9));yield .15
            assert same(self.obj().matrix_world,moved),'Left drove active MOVE'
            self.line('rotate');yield .1
            assert self.runtime().drag.mode=='MOVE'
            self.owner_at((.1,.1),'END',str(uuid4()));yield .1
            assert self.runtime().drag and same(self.obj().matrix_world,moved)
            self.owner_at((.9,.9));yield .1
            yield from self.release((.1,.1))
            assert same(self.obj().matrix_world,moved)
            completed.append(moved.copy())
        yield from self.undo_matrix(completed[0]);yield from self.undo_matrix(baseline)
        print('PASS Right open-palm MOVE, recognition without jump, Left release ignores cursor, IDs/lock and consecutive Undo',flush=True)

        # Image-plane whole-hand twist, each explicit world axis, left ignored.
        for axis in ('Z','X','Y'):
            if True:
                self.line('rotate '+axis.lower())
                yield from self.until(lambda:self.runtime().override and self.runtime().axis==axis,'rotation override')
            yield from self.start()
            def rotated(a):
                return observed(orientation=list(Quaternion(Vector(tuple(1. if x==axis else 0. for x in 'XYZ')),a)))
            self.capture(right=rotated(.3));yield from self.lock('ROTATE')
            assert same(self.obj().matrix_world,baseline)
            self.capture(right=rotated(.6))
            expected=Matrix.Rotation((.3-math.radians(2))*math.pi/(math.pi-math.radians(2)),4,axis)@baseline;expected.translation=baseline.translation
            yield from self.until_stable(lambda:same(self.obj().matrix_world,expected),'whole twist')
            self.owner_at((.1,.9));yield .12
            assert same(self.obj().matrix_world,expected)
            yield from self.release((.9,.1));assert same(self.obj().matrix_world,expected)
            yield from self.undo_matrix(baseline)
        print('PASS whole-hand twist ROTATE world XYZ, no scale/translation, no recognition jump and individual Undo',flush=True)

        # Whole-hand SCALE stays valid through fist/contact and reopening.
        yield from self.start()
        self.capture(right=palm(openness=.65));yield from self.lock('SCALE')
        assert same(self.obj().matrix_world,baseline)
        fist_id=str(uuid4())
        self.capture(right=observed(openness=0,open_palm=False,extrude_pose=False,
            pinching=True,open=False,gesture_id=fist_id,event='START',angle=.9,palm_u=.8,palm_v=.2))
        factor=4**(-.65)
        expected=Matrix.Scale(factor,4)@baseline;expected.translation=baseline.translation
        yield from self.until_stable(lambda:same(self.obj().matrix_world,expected),'visible fist scale')
        assert self.runtime().drag.mode=='SCALE' and self.runtime().tracking
        self.owner_at((.05,.95));yield .12
        assert same(self.obj().matrix_world,expected)
        self.capture(right=observed(openness=1.,event='END',gesture_id=fist_id,angle=1.2))
        factor=4**(.35)
        expected=Matrix.Scale(factor,4)@baseline;expected.translation=baseline.translation
        yield from self.until_stable(lambda:same(self.obj().matrix_world,expected),'whole hand reopening')
        assert self.runtime().drag.mode=='SCALE','fist contact/release became extrusion or completion'
        yield from self.release();assert same(self.obj().matrix_world,expected)
        yield from self.undo_matrix(baseline)
        # Near-closed selection and opening use a finite difference, no divisor.
        yield from self.start(right=palm(openness=0))
        self.capture(right=palm(openness=.3));yield from self.lock('SCALE')
        self.capture(right=palm(openness=.8))
        expected=Matrix.Scale(2.,4)@baseline;expected.translation=baseline.translation
        yield from self.until_stable(lambda:same(self.obj().matrix_world,expected),'near closed finite scale')
        yield from self.release();yield from self.undo_matrix(baseline)
        print('PASS whole-finger SCALE through fist/contact/reopening, near-closed starts, translation/twist ignored and Undo',flush=True)

        # Default FREE rotation exercises actual controller, native commit and
        # short required-hand recovery for each independent camera-frame axis.
        for axis in 'XYZ':
            qaxis=Vector(tuple(1. if x==axis else 0. for x in 'XYZ'))
            def free(a):return observed(orientation=list(Quaternion(qaxis,a)))
            yield from self.start()
            self.capture(right=free(.3));yield from self.lock('ROTATE')
            assert self.runtime().drag.axis=='FREE' and same(self.obj().matrix_world,baseline)
            self.capture(right=free(.6))
            expected=Matrix.Rotation((.3-math.radians(2))*math.pi/(math.pi-math.radians(2)),4,axis)@baseline
            expected.translation=baseline.translation
            yield from self.until_stable(lambda:same(self.obj().matrix_world,expected),'free '+axis)
            self.capture(right=absent());yield .1
            assert same(self.obj().matrix_world,expected)
            self.capture(right=free(1.0));yield .1
            assert same(self.obj().matrix_world,expected),'orientation recovery jumped'
            yield from self.release();yield from self.undo_matrix(baseline)
        print('PASS default FREE XYZ through real controller, original origin/nonuniform scale, freeze/recovery and native Undo',flush=True)

        yield from self.start()
        self.capture(right=palm(.57,.5,angle=math.radians(16)))
        yield .35
        assert self.runtime().phase=='SELECTED_READY' and same(self.obj().matrix_world,baseline)
        assert 'clearer motion' in self.module.bridge.ui_state()[1]
        self.capture(right=palm(.57,.5,angle=.6));yield from self.lock('ROTATE')
        assert same(self.obj().matrix_world,baseline)
        self.line('cancel');yield from self.until(lambda:self.runtime().drag is None,'cancel ambiguous winner')
        assert same(self.obj().matrix_world,baseline)
        yield from self.idle()
        print('PASS normalized ambiguous intent remains READY; dominant operation locks without jump; exact cancel',flush=True)

        # Required loss: both hands now required even for MOVE. No release races.
        for lost_hand in ('Left','Right'):
            yield from self.start()
            self.capture(right=palm(.55,.5));yield from self.lock('MOVE')
            self.capture(right=palm(.6,.5));moved=yield from self.wait_move((.6,.5),'preview before required loss')
            held_left=dict(self.hands['Left'])
            self.capture(left=absent()) if lost_hand=='Left' else self.capture(right=absent())
            yield .12
            assert same(self.obj().matrix_world,moved)
            if lost_hand=='Left': self.capture(left=held_left,right=palm(.8,.5))
            else: self.capture(right=palm(.8,.5))
            yield .12
            assert same(self.obj().matrix_world,moved),'recovery jumped'
            self.capture(left=absent()) if lost_hand=='Left' else self.capture(right=absent())
            yield from self.until(lambda:self.runtime().drag is None,'sustained required loss')
            assert same(self.obj().matrix_world,baseline) and self.runtime().phase=='NEEDS_RELEASE'
            self.capture(left=absent(),right=observed()) if lost_hand=='Left' else self.capture(left=observed(),right=absent())
            yield .1
            assert self.runtime().phase=='NEEDS_RELEASE' and lost_hand in self.runtime().release_hands
            yield from self.idle()
        yield from self.start();self.capture(right=palm(.55,.5));yield from self.lock('MOVE')
        self.capture(right=palm(.6,.5));yield from self.wait_move((.6,.5),'release race preview')
        self.capture(right=absent());yield .1
        self.capture(left=observed(self.start_uv,event='END',gesture_id=self.gid),right=palm(.6,.5))
        yield from self.until(lambda:self.runtime().drag is None,'loss release race cancelled')
        assert same(self.obj().matrix_world,baseline)
        yield from self.idle()
        print('PASS both required identities freeze/rebase, timeout/crossing-style uncertainty gates, release race restores',flush=True)

        # Sidebars cannot mutate an active transaction through native UI fields.
        self.area.spaces.active.show_region_ui=True;yield .12
        yield from self.start();self.capture(right=palm(.55,.5));yield from self.lock('MOVE')
        self.capture(right=palm(.6,.5));yield from self.wait_move((.6,.5),'sidebar preview')
        sidebar=next(r for r in self.area.regions if r.type=='UI' and r.width>0)
        modal=self.module.bridge.AIRMODELER_OT_connect.modal;operator=SimpleNamespace(runtime=self.runtime())
        mouse=dict(value='PRESS',ctrl=False,oskey=False,mouse_x=sidebar.x+sidebar.width//2,mouse_y=sidebar.y+sidebar.height//2)
        with self.override():
            for key in ('G','R','S','TAB','DEL'):
                assert modal(operator,bpy.context,SimpleNamespace(type=key,**mouse))=={'RUNNING_MODAL'}
            assert modal(operator,bpy.context,SimpleNamespace(type='LEFTMOUSE',**mouse))=={'PASS_THROUGH'}
        assert self.runtime().drag is None and same(self.obj().matrix_world,baseline)
        yield from self.idle()

        # Signed geometry uses the captured face and Right corrected pinch cursor.
        self.obj().rotation_euler=(0,0,0);yield .12
        baseline=self.obj().matrix_world.copy()
        with self.override(): bpy.ops.ed.undo_push(message='Whole-hand geometry baseline')
        mesh_before=geometry.snapshot(self.obj().data)
        for n,(axis,sign,plane) in enumerate([('X',1,'XY'),('X',-1,'XZ'),('Y',1,'XY'),('Y',-1,'YZ'),('Z',1,'XZ'),('Z',-1,'YZ')]):
            vector=Vector(tuple(sign*.4 if name==axis else 0 for name in 'XYZ'))
            index=max(range(len(self.obj().data.polygons)),key=lambda i:self.obj().data.polygons[i].normal.dot(vector))
            center,normal=yield from self.arm_extrusion('extrude plane '+plane.lower()+' axis '+axis.lower(),index)
            assert self.runtime().drag.plane.plane==plane and self.runtime().drag.plane.axis==axis
            assert self.runtime().drag.geometry is None,'direction lock deformed immediately'
            self.mapped_vector(vector*.5)
            yield from self.until(lambda:self.runtime().drag.geometry and self.runtime().drag.geometry.outward_distance>.19,'pinch cap preview')
            preview_counts=(len(self.obj().data.vertices),len(self.obj().data.polygons))
            cap_before_left_motion=geometry.snapshot(self.obj().data)
            self.owner_at((.1,.9));yield .1
            assert same(self.obj().matrix_world,baseline)
            assert geometry.snapshot(self.obj().data)==cap_before_left_motion,'Left motion changed cap geometry'
            assert self.runtime().drag.face_index==index
            if n%2==0:
                # Right END supplies a NEW frozen final coordinate and commits
                # while Left stays held. Its later END must not create an edit.
                self.mapped_vector(vector,event='END')
                yield from self.until(lambda:self.runtime().drag is None,'Right completion first')
                assert self.runtime().phase=='NEEDS_RELEASE' and self.runtime().release_hands=={'Left'}
                self.right_pinch(event='START');yield .18
                assert self.runtime().drag is None,'held Left selected a second transaction'
                self.owner_at((.9,.1),'END');self.capture(right=observed())
                yield from self.idle()
            else:
                self.mapped_vector(vector)
                yield from self.until(lambda:self.runtime().drag.geometry and self.runtime().drag.geometry.outward_distance>.39,'last right coordinate')
                self.owner_at((.9,.1),'END')
                yield from self.until(lambda:self.runtime().drag is None,'Left completion first')
                assert self.runtime().phase=='NEEDS_RELEASE' and self.runtime().release_hands=={'Right'}
                self.right_pinch((.1,.1),event='END');yield from self.idle()
            cap=max(self.obj().data.polygons,key=lambda p:(self.obj().matrix_world@p.center).dot(normal))
            helpers.near(self.obj().matrix_world@cap.center,center+vector)
            assert (len(self.obj().data.vertices),len(self.obj().data.polygons))==preview_counts
            geometry.inspect(self.obj().data)
            yield from self.undo_mesh(mesh_before,baseline,'one Undo for either completion order')
        print('PASS Right pinch signed XY/XZ/YZ/all six directions, final coordinate, Left inert, both completion orders once, gate and native Undo',flush=True)

        index=max(range(len(self.obj().data.polygons)),key=lambda i:self.obj().data.polygons[i].center.z)
        self.aim(index);yield .12;yield from self.idle()
        self.line('create sphere')
        yield from self.until(lambda:len(self.objects())==2,'zero-extrusion Undo sentinel')
        zero_sentinel=self.window.view_layer.objects.active.name
        # A pinch already held at selection cannot activate; reopening rearms
        # without a SCALE jump. Pinch approach displacement cannot become MOVE.
        self.right_gid=str(uuid4())
        held=observed(pinching=True,open=False,event='NONE',gesture_id=self.right_gid,
            openness=.8,open_palm=False,extrude_pose=True,pinch_pending=True)
        yield from self.start(right=held,uv=(.5,.5));yield .3
        assert self.runtime().phase=='SELECTED_READY'
        self.capture(right=palm());yield .25
        assert self.runtime().phase=='SELECTED_READY' and geometry.snapshot(self.obj().data)==mesh_before
        self.capture(right=observed(palm_u=.8,palm_v=.3,open=False,pinch_pending=True));yield .3
        assert self.runtime().phase=='SELECTED_READY' and same(self.obj().matrix_world,baseline)
        self.right_pinch(event='START');yield from self.lock('EXTRUDE')
        assert self.runtime().drag.geometry is None
        self.right_pinch(event='END');yield from self.until(lambda:self.runtime().drag is None,'zero distance completion')
        self.owner_at(self.start_uv,'END');yield from self.idle()
        assert geometry.snapshot(self.obj().data)==mesh_before
        self.line('undo')
        yield from self.until_stable(lambda:zero_sentinel not in self.window.scene.objects
            and geometry.snapshot(self.obj().data)==mesh_before and same(self.obj().matrix_world,baseline),
            'zero extrusion adds no Undo; sentinel creation is undone',settle=.2)
        print('PASS held Right pinch requires rearm, approach cannot steal MOVE, zero-distance restoration with no Undo entry',flush=True)

        snapshots=[mesh_before]
        for distance in (.5,.25):
            index=max(range(len(self.obj().data.polygons)),key=lambda i:self.obj().data.polygons[i].center.z)
            center,normal=yield from self.arm_extrusion(f'extend {distance} units',index)
            yield from self.until(lambda:self.runtime().drag.geometry is not None,'fixed distance after highlight')
            assert abs(self.runtime().drag.geometry.outward_distance-distance)<1e-6
            self.right_pinch((.8,.3));yield .12
            assert abs(self.runtime().drag.geometry.outward_distance-distance)<1e-6
            yield from self.release()
            cap=max(self.obj().data.polygons,key=lambda p:p.center.z)
            helpers.near(self.obj().matrix_world@cap.center,center+normal*distance)
            snapshots.append(geometry.snapshot(self.obj().data))
        yield from self.undo_mesh(snapshots[1],baseline,'repeated cap first Undo')
        yield from self.undo_mesh(snapshots[0],baseline,'repeated cap second Undo')
        index=max(range(len(self.obj().data.polygons)),key=lambda i:self.obj().data.polygons[i].center.z)
        yield from self.arm_extrusion('extrude plane xz axis z',index)
        self.mapped_vector((0,0,.4));yield from self.until(lambda:self.runtime().drag.geometry and self.runtime().drag.geometry.outward_distance>.39,'valid cap')
        valid_mesh=geometry.snapshot(self.obj().data)
        self.mapped_vector((0,0,-.4));yield from self.until(lambda:self.runtime().drag.geometry.outward_distance==0,'reverse to zero')
        assert self.runtime().drag.valid_preview
        yield from self.release()
        assert geometry.snapshot(self.obj().data)==mesh_before
        print('PASS fixed distance after explicit Right pinch, repeated cap/consecutive Undo, reverse-to-zero release exact restoration',flush=True)

        # Active-preview Undo cancels before undoing previous completed edit.
        self.line('move x 1 units');yield .2
        moved=self.obj().matrix_world.copy();assert not same(moved,baseline)
        yield from self.start();self.capture(right=palm(.55,.5));yield from self.lock('MOVE')
        self.capture(right=palm(.6,.5));yield from self.wait_move((.6,.5),'preview before Undo')
        self.line('undo');yield from self.until_stable(lambda:self.runtime().drag is None and same(self.obj().matrix_world,baseline),'Undo during preview',settle=.2)
        yield from self.idle()
        for reason in ('disconnect','disable'):
            yield from self.arm_extrusion('extrude plane xz axis z',index)
            self.mapped_vector((0,0,.4));yield from self.until(lambda:self.runtime().drag.geometry and self.runtime().drag.geometry.outward_distance>.39,reason+' cap')
            old=self.runtime();detached=self.disconnections
            if reason=='disconnect': self.module.bridge.disconnect()
            else: addon_utils.disable('air_modeler',default_set=False)
            assert old.timer is None and old.draw_handler is None and old.sock.fileno()==-1
            assert geometry.snapshot(self.obj().data)==mesh_before
            if reason=='disable': self.module=addon_utils.enable('air_modeler',default_set=False)
            self.ready=None
            yield from self.until(lambda:self.disconnections>detached,'old peer EOF')
            self.connect();yield from self.until(lambda:self.ready and self.module.bridge.ui_state()[0]=='Connected','reconnect')
            yield from self.idle()
        self.auto_frames=False;self.line('quit')
        yield from self.until(lambda:self.runtime() is None,'clean shutdown')
        yield from self.until(lambda:self.process.poll() is not None,'companion exit')
        print('PASS preview Undo cancels first, disconnect/disable/reconnect/shutdown restore exact geometry and free resources',flush=True)


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
