"""Actual factory file load while the installed controller owns an Edit preview."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import traceback
import bpy
spec=importlib.util.spec_from_file_location('load_clutch',Path(__file__).with_name('clutch_check.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)

class Check(helpers.Check):
 def sequence(self):
  self.window.scene.cursor.location=(0,0,0)
  self.line('create cube');yield from self.until(lambda:len(self.objects())==1,'cube')
  self.name=self.window.view_layer.objects.active.name
  index=max(range(6),key=lambda i:self.obj().data.polygons[i].center.z)
  yield from self.arm_extrusion('extrude plane xz axis z',index)
  self.mapped_vector((0,0,.4));yield from self.until(lambda:self.runtime().drag.geometry is not None,'editable preview')
  runtime=self.runtime();transaction=runtime.drag.edit
  assert self.obj().mode=='EDIT'
  self.auto_frames=False
  # Only this factory-startup process is cleared; no user's file is opened/saved.
  bpy.ops.wm.read_factory_settings(use_empty=True)
  assert transaction.closed and transaction._bm is None
  assert runtime.drag is None and runtime.timer is None and runtime.sock.fileno()==-1
  assert runtime.draw_handler is None and runtime.face_draw_handler is None
  assert self.module.bridge._runtime is None and not self.module.edit_extrusion._pending
  self.line('quit');self.process.wait(timeout=5)
  assert self.process.returncode==0
  print('PASS actual file-load pre-handler cancels owned Edit Mode, frees controller resources and invalidates old object references safely',flush=True)
  bpy.ops.wm.quit_blender()
  yield 100

check=Check();check.deadline=time.monotonic()+30

def advance():
 try:return check.step()
 except Exception:
  traceback.print_exc()
  if check.process:check.process.terminate()
  sys.stdout.flush();sys.stderr.flush();os._exit(1)
bpy.app.timers.register(advance,first_interval=.2)
