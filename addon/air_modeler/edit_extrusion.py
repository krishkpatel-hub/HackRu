"""Controller-owned Edit Mode transaction; Blender owns the wrapped live BMesh.

The original Mesh is never edited. A temporary Mesh hosts Edit Mode, with all
geometry changes made through from_edit_mesh/update_edit_mesh. A completed copy
is adopted by one native Undo operator after restoring the original in Object Mode.
"""
from uuid import uuid4
import math
import bmesh
import bpy
from mathutils import Vector
from . import extrusion as ex, signed_extrusion as signed

_pending = {}


def mesh_by_id(identifier):
    return next((m for m in bpy.data.meshes if m.session_uid == identifier), None)


def discard(identifier):
    record = _pending.pop(identifier, None)
    if record:
        mesh = mesh_by_id(record[2])
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def adopt(obj, identifier):
    record = _pending.get(identifier)
    if not record or record[:2] != (obj.session_uid, obj.data.session_uid):
        raise RuntimeError('Completed extrusion no longer owns its original object/mesh')
    result = mesh_by_id(record[2])
    if obj.mode != 'OBJECT' or result is None or result.users:
        raise RuntimeError('Completed extrusion mesh is unavailable')
    original, name = obj.data, obj.data.name
    obj.data = result
    _pending.pop(identifier)
    if original.users == 0:
        bpy.data.meshes.remove(original)
        result.name = name


class EditTransaction:
    def __init__(self, obj, context):
        ex.validate_object(obj)
        if obj.mode != 'OBJECT' or not bpy.context.preferences.edit.use_global_undo:
            raise ValueError('Extrusion requires Object Mode and Global Undo enabled')
        self.object_id = obj.session_uid
        self.original_id = obj.data.session_uid
        self.scene_id = context['scene'].session_uid
        self.layer_name = context['view_layer'].name
        self.select_mode = tuple(context['scene'].tool_settings.mesh_select_mode)
        self.preview = None
        self._bm = None
        self.closed = False
        self.working_id = obj.data.copy().session_uid
        self.mesh.name = 'Air Edit Extrusion Preview'
        try:
            obj.data = self.mesh
            with bpy.context.temp_override(**context):
                for other in context['view_layer'].objects:
                    other.select_set(other == obj)
                context['view_layer'].objects.active = obj
                # False explicitly suppresses operator Undo for temporary mode changes.
                bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='EDIT')
                context['scene'].tool_settings.mesh_select_mode = (False, False, True)
            self.select(obj, None)
        except Exception:
            self.restore(obj)
            raise

    @property
    def original(self): return mesh_by_id(self.original_id)

    @property
    def mesh(self): return mesh_by_id(self.working_id)

    def bmesh(self, obj):
        if (self.closed or obj is None or obj.session_uid != self.object_id
                or obj.mode != 'EDIT' or obj.data != self.mesh or not obj.data.is_editmode):
            raise RuntimeError('Controller-owned Edit Mode changed; extrusion cancelled')
        # Keep the Python wrapper alive for the entire Edit Mode ownership.
        # BMVert/BMFace wrappers must not outlive their parent BMesh wrapper.
        if self._bm is None:
            self._bm = bmesh.from_edit_mesh(obj.data)
        bm = self._bm
        bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        bm.verts.index_update(); bm.faces.index_update()
        return bm

    def sync(self, obj, *, destructive=False):
        self.bmesh(obj).normal_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=destructive)
        obj.update_from_editmode()  # RNA/attribute validation sees the actual editable geometry.

    def select(self, obj, index):
        bm = self.bmesh(obj)
        bm.select_mode = {'FACE'}
        for element in (*bm.faces, *bm.edges, *bm.verts):
            element.select_set(False)
        bm.select_history.clear()
        bm.faces.active = None
        if index is not None:
            face = bm.faces[index]
            if face.hide:
                raise ValueError('Hidden edit faces cannot be selected for extrusion')
            face.select_set(True)
            bm.faces.active = face
        bm.select_flush_mode()
        self.sync(obj)

    def validate(self, obj, context):
        bm = self.bmesh(obj)
        if (context['view_layer'].objects.active != obj
                or tuple(context['scene'].tool_settings.mesh_select_mode) != (False, False, True)
                or any(other != obj and other.mode == 'EDIT' for other in context['view_layer'].objects)):
            raise RuntimeError('Edit object or Face Select context changed; extrusion cancelled')
        self.sync(obj)
        return bm

    def mode_context(self, obj):
        # Re-resolve IDs: a viewport may have disappeared, or file/Undo may have
        # invalidated RNA. Never switch the mode of a different active object.
        for window in bpy.context.window_manager.windows:
            if (window.scene.session_uid == self.scene_id and window.view_layer.name == self.layer_name
                    and window.view_layer.objects.active == obj):
                return dict(window=window, scene=window.scene, view_layer=window.view_layer,
                            object=obj, active_object=obj)
        return None

    def finish(self, obj, keep=False):
        if self.closed:
            return None
        original, working = self.original, self.mesh
        owns = obj is not None and obj.data == working
        if owns and obj.mode != 'OBJECT':
            # Restore via the live BMesh before leaving on cancel. No Object Mode
            # mesh writes can be overwritten later by Blender's edit-mode flush.
            if obj.mode == 'EDIT' and not keep and original is not None:
                bm = self.bmesh(obj); bm.clear(); bm.from_mesh(original)
                self.sync(obj, destructive=True)
            context = self.mode_context(obj)
            if context is not None:
                with bpy.context.temp_override(**context):
                    bpy.ops.object.mode_set('EXEC_DEFAULT', False, mode='OBJECT')
            elif keep:
                raise RuntimeError('Original edit context disappeared; cannot commit')
        if owns and obj.mode == 'OBJECT' and original is not None:
            obj.data = original
            obj.select_set(True)
        elif keep:
            raise RuntimeError('Cannot return the extrusion target to Object Mode')
        elif owns and original is not None:
            # The original context is gone. The editable working mesh already
            # contains the exact baseline; let it become the object's data,
            # without changing another scene/active object's mode. Retire the
            # unused baseline rather than leave an orphaned temporary pair.
            if original.users == 0 and not original.use_fake_user:
                name = original.name
                bpy.data.meshes.remove(original)
                working.name = name
        scene = next((s for s in bpy.data.scenes if s.session_uid == self.scene_id), None)
        if scene is not None:
            scene.tool_settings.mesh_select_mode = self.select_mode
        if self.preview is not None:
            self.preview.dispose()
        self._bm = None  # Blender freed it on mode exit; never call free() here.
        self.closed = True
        if keep:
            identifier = str(uuid4())
            _pending[identifier] = (obj.session_uid, original.session_uid, working.session_uid)
            return identifier
        if working is not None and working.users == 0:
            bpy.data.meshes.remove(working)
        return None

    def restore(self, obj):
        return self.finish(obj, keep=False)


class SignedEditPreview:
    """Update the wrapped BMesh, building the outward extrusion only once.

    Zero/inward use baseline topology. A cached outward topology preserves custom
    data when crossing zero repeatedly, without extruding an already extruded cap.
    Blender owns the live BMesh: it is never freed or used after leaving Edit Mode.
    """
    def __init__(self, edit, obj, index, config=ex.CONFIG):
        self.edit, self.obj, self.face_index, self.config = edit, obj, index, config
        edit.sync(obj)
        normal, vertices = ex.face_info(obj, index, config)
        self.world_matrix = obj.matrix_world.copy()
        linear = self.world_matrix.to_3x3()
        self.local_normal = normal
        self.world_normal = (linear.inverted().transposed() @ normal).normalized()
        self.inverse_linear = linear.inverted()
        self.base_outline = tuple(self.world_matrix @ v for v in vertices)
        self.amount = self.outward_distance = 0.
        self.world_vector = self.local_vector = Vector()
        self.limit_reason = ''; self.inward_error = None
        self.cache_id = None; self.representation = 'baseline'; self.topology_builds = 0
        bm = self.bm
        self.original_volume = bm.calc_volume(signed=True)
        self.original_area = bm.faces[index].calc_area()
        try: self.plan = signed.InwardPlan(obj, index)
        except ValueError as exc: self.plan = None; self.inward_error = str(exc)
        edit.preview = self

    @property
    def mesh(self): return self.edit.mesh

    @property
    def bm(self): return self.edit.bmesh(self.obj)

    def load(self, mesh, representation):
        bm = self.bm
        bm.clear(); bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        bm.verts.index_update(); bm.faces.index_update()
        self.representation = representation

    def outward(self):
        bm = self.bm
        if self.cache_id is None:
            face = bm.faces[self.face_index]
            result = bmesh.ops.extrude_face_region(bm, geom=[face], use_keep_orig=False)
            cap_vertices = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
            caps = [f for f in result['geom'] if isinstance(f, bmesh.types.BMFace) and set(f.verts) == set(cap_vertices)]
            if len(caps) != 1 or len(cap_vertices) != len(face.verts):
                raise RuntimeError('Cannot identify one editable extrusion cap')
            cap = caps[0]
            bmesh.ops.delete(bm, geom=[face], context='FACES_ONLY')
            bm.verts.index_update(); bm.faces.index_update()
            self.cap_indices = [v.index for v in cap_vertices]
            self.cap_index = cap.index
            self.base = [v.co.copy() for v in cap_vertices]
            cache = self.edit.original.copy(); cache.name = 'Air Extrusion Topology Cache'
            self.cache_id = cache.session_uid
            owned = bm.copy()
            try: owned.to_mesh(cache)
            finally: owned.free()
            self.topology_builds += 1
            self.representation = 'outward'
        elif self.representation != 'outward':
            self.load(mesh_by_id(self.cache_id), 'outward')
        bm = self.bm
        self.cap = bm.faces[self.cap_index]
        self.cap_vertices = [bm.verts[i] for i in self.cap_indices]

    def update(self, amount):
        if not math.isfinite(amount): raise ValueError('Nonfinite signed extrusion distance')
        requested = amount; self.limit_reason = ''
        amount = min(amount, self.config.maximum_distance)
        if amount < 0:
            if self.plan is None:
                amount = 0.; self.limit_reason = 'Inward unsupported: ' + self.inward_error
            else:
                amount = max(amount, -self.plan.limit)
                if amount != requested:
                    self.limit_reason = f'Inward limit {self.plan.limit:.3f}: {self.plan.reason}; safety margin retained'
        elif amount != requested: self.limit_reason = 'Maximum outward distance reached'
        if abs(amount) <= self.config.negligible_distance: amount = 0.
        before = self.representation
        if amount > 0:
            if self.representation == 'inward': self.load(self.edit.original, 'baseline')
            self.outward()
            local = self.inverse_linear @ (self.world_normal * amount)
            for vertex, base in zip(self.cap_vertices, self.base): vertex.co = base + local
            selected = self.cap_index
        else:
            if self.representation == 'outward' or amount == 0 and self.representation == 'inward':
                self.load(self.edit.original, 'baseline')
            if amount < 0:
                self.plan.apply(self.bm, amount); signed.validate_convex(self.bm)
                self.representation = 'inward'
            selected = self.face_index
        self.amount = self.outward_distance = amount
        self.world_vector = self.world_normal * amount
        self.local_vector = self.inverse_linear @ self.world_vector
        self.edit.sync(self.obj, destructive=before != self.representation)
        self.edit.select(self.obj, selected)

    def validate_result(self):
        if abs(self.amount) <= self.config.negligible_distance: raise ValueError('Extrusion is negligible')
        if self.amount > 0: ex.Preview.validate_result(self)
        elif not 0 < signed.validate_convex(self.bm) < self.plan.volume:
            raise ValueError('Inward result must shorten the original convex solid')

    def outline(self):
        bm = self.bm
        index = self.cap_index if self.representation == 'outward' else self.face_index
        return tuple(self.world_matrix @ v.co for v in bm.faces[index].verts)

    def dispose(self):
        cache = mesh_by_id(self.cache_id) if self.cache_id is not None else None
        if cache is not None and cache.users == 0: bpy.data.meshes.remove(cache)
        self.cache_id = None
        self.obj = None
