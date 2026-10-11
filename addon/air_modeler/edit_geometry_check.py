"""Installed ZIP: native editable BMesh ownership, topology caching and Undo."""
import bpy,bmesh,sys,traceback,os,addon_utils
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
assert os.environ.get('BLENDER_USER_RESOURCES'), 'Use isolated factory startup'
sys.path.insert(0,str(ROOT))
bpy.ops.preferences.addon_install(filepath=str(ROOT/'dist/air_modeler.zip'))
m=addon_utils.enable('air_modeler',default_set=False)
from air_modeler import edit_extrusion as edit,visibility
import importlib.util
spec=importlib.util.spec_from_file_location("edit_geometry_helpers",Path(__file__).with_name("extrusion_geometry_check.py"))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)

def geometry(mesh):
 if mesh.is_editmode:
  # Mesh RNA custom-data collections are unavailable while editing. Snapshot
  # a detached copy of the actual wrapped BMesh instead of stale Object RNA.
  owned=bmesh.from_edit_mesh(mesh).copy(); copy=bpy.data.meshes.new('check snapshot')
  try:
   owned.to_mesh(copy)
   return helpers.snapshot(copy)
  finally:
   owned.free();bpy.data.meshes.remove(copy)
 return helpers.snapshot(mesh)
def run():
 try:
  win=bpy.context.window;area=next(a for a in win.screen.areas if a.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
  context=dict(window=win,area=area,region=region,scene=win.scene,view_layer=win.view_layer)
  with bpy.context.temp_override(**context):
   bpy.ops.ed.undo_push(message='probe baseline')
   bpy.ops.air_modeler.create_primitive('EXEC_DEFAULT',True,shape='cube')
   obj=bpy.context.object;name=obj.name;original=obj.data
   attr=original.attributes.new('sentinel','FLOAT','POINT')
   for i,item in enumerate(attr.data):item.value=i+.25
   original.uv_layers.new(name='Edit test UV')
   for i,item in enumerate(original.uv_layers.active.data):item.uv=(i/30,.75)
   # Attribute setup belongs to the spawn baseline for the following Undo check.
   bpy.ops.ed.undo_push(message='attribute baseline')
   before=geometry(original)
   for commit in (False,True):
    tx=edit.EditTransaction(obj,context)
    assert obj.mode=='EDIT' and tuple(win.scene.tool_settings.mesh_select_mode)==(False,False,True)
    assert geometry(obj.data)==before, [(i,a,b) for i,(a,b) in enumerate(zip(geometry(obj.data),before)) if a!=b]
    assert not any(f.select for f in tx.bmesh(obj).faces)
    tx.select(obj,5)
    pr=edit.SignedEditPreview(tx,obj,5)
    for amount in (.2,.4,.2,0,-.2,-.4,0,.3):
     pr.update(amount)
     if amount:pr.validate_result()
     else:assert geometry(obj.data)==before
     assert geometry(original)==before
    assert pr.topology_builds==1
    after=geometry(obj.data)
    token=tx.finish(obj,keep=commit)
    assert obj.mode=='OBJECT' and obj.data==original and geometry(original)==before
    if commit:
     assert bpy.ops.air_modeler.commit_extrusion('EXEC_DEFAULT',True,target_name=name,prepared_id=token)=={'FINISHED'}
     assert geometry(obj.data)==after
     bpy.ops.ed.undo();obj=bpy.data.objects[name]
     assert obj.mode=='OBJECT' and geometry(obj.data)==before
   bpy.ops.ed.undo()
   assert name in bpy.data.objects and 'sentinel' not in bpy.data.objects[name].data.attributes,'temporary modes or cancellation inserted Undo'
   bpy.ops.ed.undo();assert name not in bpy.data.objects
   print('PASS editable BMesh signed topology reused once, original immutable, Object Mode restoration, one native Undo and no temporary Undo',flush=True)
  bpy.ops.wm.quit_blender()
 except Exception:
  traceback.print_exc();sys.stdout.flush();sys.stderr.flush();os._exit(1)
bpy.app.timers.register(run,first_interval=.2)
