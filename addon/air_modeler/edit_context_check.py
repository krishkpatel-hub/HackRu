"""Isolated native Edit Mode context invalidation and custom-data guards."""
import importlib.util
import os
from pathlib import Path
import sys
import traceback
import addon_utils
import bpy
import bmesh

ROOT=Path(__file__).resolve().parents[2]
assert os.environ.get('BLENDER_USER_RESOURCES'), 'Use isolated factory startup'
bpy.ops.preferences.addon_install(filepath=str(ROOT/'dist/air_modeler.zip'))
module=addon_utils.enable('air_modeler',default_set=False)
from air_modeler import edit_extrusion as edit, visibility
spec=importlib.util.spec_from_file_location('edit_context_geometry',Path(__file__).with_name('extrusion_geometry_check.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)

def run():
 try:
  window=bpy.context.window;scene=window.scene
  area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
  region=next(r for r in area.regions if r.type=='WINDOW')
  context=dict(window=window,area=area,region=region,scene=scene,view_layer=window.view_layer)
  with bpy.context.temp_override(**context):
   for reason in ('attributes','viewport','mode','scene','active','deletion'):
    bpy.ops.air_modeler.create_primitive('EXEC_DEFAULT',False,shape='cube')
    obj=bpy.context.object;original=obj.data
    attr=original.attributes.new('sentinel','FLOAT','POINT')
    for i,item in enumerate(attr.data):item.value=i+.25
    original.uv_layers.new(name='Context UV')
    baseline=helpers.snapshot(original)
    original_id=original.session_uid
    tx=edit.EditTransaction(obj,context)
    initial_stamp=visibility.mesh_stamp(obj.data)
    tx.select(obj,5)
    assert initial_stamp==visibility.mesh_stamp(obj.data),'face selection changed geometry guard'
    preview=edit.SignedEditPreview(tx,obj,5);preview.update(.3)
    if reason=='attributes':
     before=visibility.mesh_stamp(obj.data)
     assert before==visibility.mesh_stamp(obj.data),'validation retained temporary RNA references'
     bm=tx.bmesh(obj);layer=bm.verts.layers.float['sentinel'];bm.verts[0][layer]+=1
     assert visibility.mesh_stamp(obj.data)!=before,'editable custom data absent from guard'
    elif reason=='viewport':area.type='CONSOLE'
    elif reason=='mode':bpy.ops.object.mode_set('EXEC_DEFAULT',False,mode='OBJECT')
    elif reason=='scene':window.scene=bpy.data.scenes.new('Other context')
    elif reason=='active':
     other=bpy.data.objects.new('Other active',None);scene.collection.objects.link(other)
     window.view_layer.objects.active=other
    elif reason=='deletion':bpy.data.objects.remove(obj,do_unlink=True);obj=None
    tx.restore(obj)
    assert tx.closed and tx._bm is None and preview.cache_id is None and not edit._pending
    retained=edit.mesh_by_id(original_id)
    if retained is not None:assert helpers.snapshot(retained)==baseline
    if reason in ('attributes','viewport','mode'):
     assert obj.mode=='OBJECT' and obj.data==original and obj.select_get()
    if reason=='viewport':
     area.type='VIEW_3D';region=next(r for r in area.regions if r.type=='WINDOW');context['region']=region
    if reason=='scene':window.scene=scene
    if obj is not None:
     window.view_layer.objects.active=obj
     if obj.mode=='EDIT':
      # Context was no longer ours: baseline restored in live BMesh, no mode
      # switch forced on the newly active object/scene. Verify after safe exit.
      with bpy.context.temp_override(window=window,scene=scene,view_layer=window.view_layer):
       bpy.ops.object.mode_set('EXEC_DEFAULT',False,mode='OBJECT')
     assert helpers.snapshot(obj.data)==baseline
    assert not any(m.name.startswith(('Air Extrusion Topology Cache','Air edit validation','Air Edit Extrusion Preview')) for m in bpy.data.meshes)
    print('PASS Edit Mode cleanup '+reason+' restores baseline safely, no stale wrapper or cache',flush=True)
  bpy.ops.wm.quit_blender()
 except Exception:
  traceback.print_exc();sys.stdout.flush();sys.stderr.flush();os._exit(1)
bpy.app.timers.register(run,first_interval=.2)
