"""Native removal/Undo and active-clutch rejection; isolated generated input only."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4
import bpy

spec=importlib.util.spec_from_file_location('remove_clutch_helpers',Path(__file__).with_name('clutch_check.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


class Check(helpers.Check):
    def command(self,action,shape,identifier=None):
        event=dict(type='command',payload=dict(id=identifier or str(uuid4()),action=action,shape=shape))
        self.send(event)
        return event

    def select(self,*names):
        for obj in self.window.view_layer.objects:obj.select_set(obj.name in names)
        self.window.view_layer.objects.active=self.window.view_layer.objects.get(names[0]) if names else None

    def sequence(self):
        assert self.module.bl_info['version']==(0,15,0)
        self.window.scene.cursor.location=(0,0,0)
        # All shape tags, changed names, UUID dedup and independent native Undo.
        for shape in ('cube','sphere','cylinder','prism'):
            self.line('create '+shape)
            yield from self.until(lambda:len(self.objects())==1,'create '+shape)
            obj=self.window.view_layer.objects.active
            assert obj['air_modeler_shape']==shape
            obj.name='Renamed object '+shape;name=obj.name
            baseline=helpers.geometry.snapshot(obj.data)
            with self.override():bpy.ops.ed.undo_push(message='Renamed target baseline')
            event=self.command('remove',shape)
            yield from self.until(lambda:name not in self.window.scene.objects,'remove '+shape)
            assert self.runtime().status()['payload']['message'].startswith('Removed '+shape)
            self.line('undo')
            yield from self.until_stable(lambda:name in self.window.scene.objects,'native removal Undo')
            assert helpers.geometry.snapshot(self.window.scene.objects[name].data)==baseline
            self.send(event);yield .2
            assert name in self.window.scene.objects,'duplicate removal executed after Undo'
            self.command('remove',shape)
            yield from self.until(lambda:not self.objects(),'intentional new removal')
        print('PASS all four tagged shapes remove once, names irrelevant, native Undo restores geometry, UUID duplicate versus repeat',flush=True)

        self.line('create cube');yield from self.until(lambda:len(self.objects())==1,'base cube')
        self.name=self.window.view_layer.objects.active.name
        self.line('create sphere');yield from self.until(lambda:len(self.objects())==2,'Undo sentinel sphere')
        sphere=self.window.view_layer.objects.active.name
        self.command('remove','cube');yield .2
        assert len(self.objects())==2 and 'Select the cube' in self.module.bridge.ui_state()[2]
        self.select();self.command('remove','sphere');yield .2
        assert len(self.objects())==2 and 'Select the sphere' in self.module.bridge.ui_state()[2]
        self.select(self.name,sphere);self.command('remove','cube');yield .2
        assert len(self.objects())==2
        self.line('undo');yield from self.until_stable(lambda:sphere not in self.window.scene.objects,'rejections add no Undo')
        assert self.name in self.window.scene.objects
        print('PASS wrong/missing/multiple selection deletes nothing and adds no Undo',flush=True)

        # A linked mesh can be shared; only the target object should disappear.
        obj=self.obj();mesh=obj.data;baseline=helpers.geometry.snapshot(mesh)
        sibling=obj.copy();sibling.name='Shared mesh sibling';sibling.location.x=4
        self.window.scene.collection.objects.link(sibling);sibling_name=sibling.name
        fake=bpy.data.objects.new('Air Cube Impostor',mesh)
        self.window.scene.collection.objects.link(fake);fake_name=fake.name
        self.select(fake_name);self.command('remove','cube');yield .2
        assert fake_name in self.window.scene.objects and 'Select the cube' in self.module.bridge.ui_state()[2]
        bpy.data.objects.remove(fake,do_unlink=True)
        self.select(self.name)
        with self.override():bpy.ops.ed.undo_push(message='Shared mesh removal baseline')
        self.command('remove','cube');yield from self.until(lambda:self.name not in self.window.scene.objects,'remove shared target only')
        assert sibling_name in self.window.scene.objects
        assert helpers.geometry.snapshot(self.window.scene.objects[sibling_name].data)==baseline
        self.line('undo');yield from self.until_stable(lambda:self.name in self.window.scene.objects,'restore shared target')
        assert self.obj().data==self.window.scene.objects[sibling_name].data
        assert helpers.geometry.snapshot(self.obj().data)==baseline
        print('PASS untagged name rejected; shared mesh sibling/data unchanged; one Undo restores target and sharing',flush=True)

        # Real coherent frames + same bridge: SELECTED_READY, dwell, transform preview.
        # Extrusion intentionally forbids shared data; give its fixture a private
        # copy only after proving removal/Undo preserved the original sharing.
        self.obj().data=self.obj().data.copy()
        obj=self.obj();index=max(range(len(obj.data.polygons)),key=lambda i:obj.data.polygons[i].center.z)
        self.aim(index);yield .15;yield from self.idle()
        initial=len(self.objects())
        for phase in ('ready','dwell','move'):
            if phase=='dwell':self.line('extrude plane xz axis z');yield .15
            yield from self.start(uv=(.5,.5))
            if phase=='dwell':
                self.right_pinch(event='START');yield from self.lock('EXTRUDE');yield .3
                assert self.runtime().drag.face_index is None and self.runtime().drag.geometry is None
            if phase=='move':
                self.capture(right=helpers.palm(.56,.5));yield from self.lock('MOVE')
                self.capture(right=helpers.palm(.62,.5));yield .15
            drag=self.runtime().drag
            self.command('spawn','sphere');self.command('remove','cube');yield .15
            # Consumer guard is authoritative even before status reaches producer.
            for action in ('spawn','remove'):
                self.runtime().handle(dict(type='command',payload=dict(id=str(uuid4()),action=action,shape='cube')))
                assert 'Release or cancel' in self.module.bridge.ui_state()[2]
            assert self.runtime().drag is drag and len(self.objects())==initial
            self.line('cancel');yield from self.until(lambda:self.runtime().drag is None,'cancel '+phase)
            yield from self.idle();yield .25
            assert len(self.objects())==initial and helpers.geometry.snapshot(self.obj().data)==baseline
        print('PASS CREATE/REMOVE rejected during selection, real dwell and MOVE preview; no queued execution after cancel',flush=True)
        self.select(self.name)
        bpy.context.preferences.edit.use_global_undo=False
        try:
            self.command('remove','cube');yield .2
            assert len(self.objects())==initial and 'Enable Global Undo' in self.module.bridge.ui_state()[2]
        finally:
            bpy.context.preferences.edit.use_global_undo=True
        print('PASS disabled Global Undo rejects removal without scene mutation',flush=True)
        self.auto_frames=False
        self.line('quit');yield from self.until(lambda:self.runtime() is None,'clean bridge shutdown')
        yield from self.until(lambda:self.process.poll() is not None,'companion shutdown')
        print('PASS removal real TCP/Blender status and shutdown',flush=True)


check=Check()
check.deadline=time.monotonic()+180

def advance():
    try:return check.step()
    except Exception:
        traceback.print_exc();check.close();sys.stdout.flush();sys.stderr.flush();os._exit(1)

bpy.app.timers.register(advance,first_interval=.1)
