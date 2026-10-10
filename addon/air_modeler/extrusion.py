"""Single-face geometry ownership. No controller, timer, socket or Undo pushes."""
from dataclasses import dataclass
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


@dataclass(frozen=True)
class ExtrusionConfig:
    sensitivity: float = 4.0  # world units per normalized viewport height
    maximum_distance: float = 4.0
    negligible_distance: float = 1e-5  # world units
    geometry_tolerance: float = 1e-6  # mesh-local units


CONFIG = ExtrusionConfig()


def distance(start_v, current_v, config):
    return max(0.0, min(config.maximum_distance, config.sensitivity * (start_v - current_v)))


def validate_object(obj):
    if obj.type != 'MESH' or not obj.is_editable or not obj.data.is_editable:
        raise ValueError('EXTRUDE requires an editable mesh')
    if obj.parent or obj.constraints or obj.animation_data or any(m.show_viewport for m in obj.modifiers):
        raise ValueError('EXTRUDE rejects parents, constraints, animation and enabled modifiers')
    mesh = obj.data
    if mesh.users != 1 or mesh.library or mesh.override_library or mesh.use_fake_user:
        raise ValueError('EXTRUDE requires single-user local mesh data (no linked/shared data)')
    if not all(math.isfinite(x) for vertex in mesh.vertices for x in vertex.co):
        raise ValueError("EXTRUDE requires finite mesh coordinates")
    if mesh.shape_keys or mesh.animation_data or mesh.has_custom_normals:
        raise ValueError('EXTRUDE does not support shape keys, animated meshes or custom normals')
    if abs(obj.matrix_world.to_3x3().determinant()) <= 1e-10:
        raise ValueError('EXTRUDE rejects singular transforms')
    if not all(math.isfinite(x) for row in obj.matrix_world for x in row):
        raise ValueError('EXTRUDE requires a finite transform')
    from .transforms import validate_rigid_scale
    validate_rigid_scale(obj)
    supported = {'FLOAT', 'INT', 'FLOAT_VECTOR', 'FLOAT_COLOR', 'BYTE_COLOR', 'BOOLEAN', 'FLOAT2'}
    if any(not a.is_internal and a.data_type not in supported for a in mesh.attributes):
        raise ValueError('EXTRUDE found an unsupported mesh attribute type')


def validate_face(bm, index, config=CONFIG):
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    if not 0 <= index < len(bm.faces):
        raise ValueError('Original mesh face index is invalid')
    if not bm.edges or not all(e.is_manifold and e.is_contiguous for e in bm.edges):
        raise ValueError('EXTRUDE requires closed consistently wound manifold geometry')
    if any(not v.link_faces for v in bm.verts) or bm.calc_volume(signed=True) <= config.geometry_tolerance:
        raise ValueError('EXTRUDE requires outward closed geometry without loose vertices')
    if any(f.calc_area() <= 1e-12 for f in bm.faces) or any(e.calc_length() <= 1e-12 for e in bm.edges):
        raise ValueError('EXTRUDE rejects degenerate source geometry')
    face = bm.faces[index]
    vertices = [v.co for v in face.verts]
    normal = face.normal.copy()
    if len(vertices) not in (3, 4) or face.calc_area() <= config.geometry_tolerance:
        raise ValueError('EXTRUDE supports nondegenerate triangular or quad faces')
    if any(abs((v - vertices[0]).dot(normal)) > config.geometry_tolerance for v in vertices):
        raise ValueError('EXTRUDE requires a flat face')
    if any((vertices[(i+1) % len(vertices)] - vertices[i]).cross(
            vertices[(i+2) % len(vertices)] - vertices[(i+1) % len(vertices)]).dot(normal)
            <= config.geometry_tolerance for i in range(len(vertices))):
        raise ValueError('EXTRUDE requires a strictly convex face')
    # A supporting face plane guarantees the outward prism cannot cross the
    # rest of this mesh. Concave recessed faces are deliberately unsupported.
    if any((v.co - vertices[0]).dot(normal) > config.geometry_tolerance for v in bm.verts):
        raise ValueError('EXTRUDE requires an outer supporting face, not a recessed face')
    return face


def face_info(obj, index, config=CONFIG):
    validate_object(obj)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        face = validate_face(bm, index, config)
        # from_mesh preserves polygon order; verify the original index mapping
        # against the actual vertex loop before allowing any edit.
        bm.verts.index_update()
        if tuple(v.index for v in face.verts) != tuple(obj.data.polygons[index].vertices):
            raise ValueError('Original face mapping could not be verified')
        return face.normal.copy(), tuple(v.co.copy() for v in face.verts)
    finally:
        bm.free()


def ray_hit(obj, origin, direction):
    """BVH built directly from original polygons; no evaluated index is used."""
    if not all(math.isfinite(x) for row in obj.matrix_world for x in row) or not all(math.isfinite(x) for v in obj.data.vertices for x in v.co):
        return None
    inverse = obj.matrix_world.inverted()
    tree = BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                               [tuple(p.vertices) for p in obj.data.polygons])
    point, _, index, _ = tree.ray_cast(inverse @ origin, (inverse.to_3x3() @ direction).normalized())
    return (obj.matrix_world @ point, index) if point is not None else None


class Preview:
    """Own one isolated mesh copy and one BMesh until restore/adopt."""
    def __init__(self, obj, face_index, config=CONFIG):
        normal, _ = face_info(obj, face_index, config)  # no mutation before validation
        self.original = obj.data
        self.original_name = obj.data.name
        self.face_index = face_index
        self.config = config
        self.bm = None
        self.mesh = None
        self.cap_vertices = []
        self.base = []
        self.cap = None
        self.world_matrix = obj.matrix_world.copy()
        linear = self.world_matrix.to_3x3()
        self.world_normal = (linear.inverted().transposed() @ normal).normalized()
        self.inverse_linear = linear.inverted()
        self.local_step = self.inverse_linear @ self.world_normal
        self.amount = 0.0
        self.world_vector = Vector((0, 0, 0))
        self.local_vector = Vector((0, 0, 0))
        self.outward_distance = 0.0
        try:
            self.mesh = self.original.copy()
            self.mesh.name = 'Air Extrusion Preview'
            self.bm = bmesh.new()
            self.bm.from_mesh(self.original)
            self.bm.faces.ensure_lookup_table()
            face = self.bm.faces[face_index]
            self.original_volume = self.bm.calc_volume(signed=True)
            self.original_area = face.calc_area()
            self.local_normal = normal
            result = bmesh.ops.extrude_face_region(self.bm, geom=[face], use_keep_orig=False)
            self.cap_vertices = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
            cap_set = set(self.cap_vertices)
            caps = [f for f in result['geom'] if isinstance(f, bmesh.types.BMFace) and set(f.verts) == cap_set]
            if len(caps) != 1 or len(cap_set) != len(face.verts):
                raise RuntimeError('BMesh did not produce one identifiable outer cap')
            self.cap = caps[0]
            # Blender 5.2 retains/flips this single input face. Remove only
            # the interior face; its boundary is needed by the new side walls.
            bmesh.ops.delete(self.bm, geom=[face], context='FACES_ONLY')
            self.base = [v.co.copy() for v in self.cap_vertices]
            self.update(0)
            obj.data = self.mesh
        except Exception:
            self.restore(obj)
            raise

    def update(self, amount):
        if not math.isfinite(amount) or amount < 0 or amount > self.config.maximum_distance:
            raise ValueError('Extrusion distance is outside configured bounds')
        # Legacy scalar previews may pass through a negligible positive value.
        # validate_result/commit still prevent a negligible modeling edit.
        self._apply_vector(self.world_normal * amount)

    def update_vector(self, world_vector):
        """Translate the existing cap from its baseline; never grow topology.

        A negative world component is valid when it points outside this face.
        Tangent/inward displacements are rejected before changing any vertices.
        A zero vector restores the coincident preview cap and cannot be adopted.
        """
        vector = checked_vector(world_vector, self.config)
        outward = vector.dot(self.world_normal)
        if vector.length > 0 and outward <= self.config.negligible_distance:
            raise ValueError('Extrusion must point outward from the selected face; tangent/inward motion is unsupported')
        self._apply_vector(vector)

    def _apply_vector(self, vector):
        local = self.inverse_linear @ vector
        for vert, base in zip(self.cap_vertices, self.base):
            vert.co = base + local
        self.world_vector = vector
        self.local_vector = local
        self.amount = vector.length
        self.outward_distance = vector.dot(self.world_normal)
        self.bm.normal_update()
        self.bm.to_mesh(self.mesh)
        self.mesh.update()

    def validate_result(self):
        if self.outward_distance <= self.config.negligible_distance:
            raise ValueError('Extrusion is negligible')
        if not all(e.is_manifold and e.is_contiguous for e in self.bm.edges):
            raise ValueError('Extrusion would not be consistently wound and manifold')
        if any(f.calc_area() <= 1e-12 for f in self.bm.faces):
            raise ValueError('Extrusion is too small for this mesh precision')
        if self.cap.normal.dot(self.local_normal) < .999:
            raise ValueError('Extrusion cap orientation is inconsistent')
        expected = self.original_volume + self.original_area * self.local_vector.dot(self.local_normal)
        if not math.isclose(self.bm.calc_volume(signed=True), expected, rel_tol=1e-5, abs_tol=1e-6):
            raise ValueError('Extrusion volume does not match the outward prism')

    def outline(self):
        return tuple(self.world_matrix @ v.co for v in self.cap.verts)

    def _free_bmesh(self):
        if self.bm is not None:
            self.bm.free()
        self.bm = self.cap = None
        self.cap_vertices = []
        self.base = []

    def restore(self, obj):
        restore_mode = None
        if obj is not None and self.mesh is not None and obj.data == self.mesh:
            # Flush/free Blender's edit-mode BMesh before swapping datablocks;
            # otherwise exiting Edit Mode later writes the preview into baseline.
            if obj.mode != 'OBJECT':
                restore_mode = obj.mode
                with bpy.context.temp_override(object=obj, active_object=obj):
                    bpy.ops.object.mode_set(mode='OBJECT')
            obj.data = self.original
            if restore_mode is not None:
                with bpy.context.temp_override(object=obj, active_object=obj):
                    bpy.ops.object.mode_set(mode=restore_mode)
        self._free_bmesh()
        if self.mesh is not None and self.mesh.users == 0:
            bpy.data.meshes.remove(self.mesh)
        self.mesh = None
        self.original = None

    def adopt(self, obj):
        """Transfer the completed copy to the object; remove unused baseline."""
        if obj.data != self.mesh:
            raise RuntimeError('Extrusion preview ownership changed')
        self._free_bmesh()
        if self.original.users == 0:
            bpy.data.meshes.remove(self.original)
            self.mesh.name = self.original_name
        self.mesh = self.original = None


def commit(obj, face_index, amount, config=CONFIG):
    if amount <= config.negligible_distance:
        return False
    preview = Preview(obj, face_index, config)
    try:
        preview.update(amount)
        preview.validate_result()
        preview.adopt(obj)
    except Exception:
        preview.restore(obj)
        raise
    return True


def checked_vector(value, config=CONFIG):
    """Validate before allocating a preview or touching its current cap."""
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError('Extrusion requires a finite three-component world vector') from exc
    if len(values) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                               or not math.isfinite(v) for v in values):
        raise ValueError('Extrusion requires a finite three-component world vector')
    vector = Vector(values)
    # mathutils stores float32 values; tolerate its rounding at the exact bound.
    if vector.length > config.maximum_distance + 1e-6:
        raise ValueError('Extrusion vector is outside configured bounds')
    return vector


def commit_vector(obj, face_index, world_vector, config=CONFIG):
    """Transactional geometry commit for mapped signed world displacement."""
    vector = checked_vector(world_vector, config)
    if vector.length == 0:
        return False
    preview = Preview(obj, face_index, config)
    try:
        preview.update_vector(vector)
        preview.validate_result()
        preview.adopt(obj)
    except Exception:
        preview.restore(obj)
        raise
    return True


def candidates(obj):
    """Eligible baseline faces including hidden ones, without a raycast/mutation."""
    validate_object(obj)
    linear=obj.matrix_world.to_3x3()
    normal_matrix=linear.inverted().transposed()
    result=[]
    for polygon in obj.data.polygons:
        try:
            normal,vertices=face_info(obj,polygon.index)
        except ValueError:
            continue
        outline=tuple(obj.matrix_world@v for v in vertices)
        normal=(normal_matrix@normal).normalized()
        center=sum(outline,Vector())/len(outline)
        result.append((polygon.index,normal,center,outline))
    if not result: raise ValueError('No eligible outer supporting triangular/quad face')
    return result


def choose_face(faces, direction, margin=.12):
    """Best positive normal; distinct directions need margin, parallel outermost wins."""
    direction=Vector(direction).normalized()
    ranked=sorted(((normal.dot(direction),index,normal,center,outline)
                   for index,normal,center,outline in faces),key=lambda x:(-x[0],x[1]))
    best=ranked[0]
    if best[0]<.55: return None
    distinct=[item for item in ranked[1:] if item[2].dot(best[2])<.999]
    if distinct and best[0]-distinct[0][0]<margin: return None
    parallel=[item for item in ranked if item[2].dot(best[2])>=.999]
    # Rounded support distance avoids floating-point noise changing a tie.
    chosen=max(parallel,key=lambda item:(round(item[3].dot(direction),6),-item[1]))
    return chosen[1],chosen[2],chosen[4],[(i,round(score,3)) for score,i,_,_,_ in ranked]
