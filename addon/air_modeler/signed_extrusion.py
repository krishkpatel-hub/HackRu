"""Baseline convex face-plane shortening plus the existing outward cap path.

Inward vertices follow intersections with their incident baseline side planes.
No inward cap extrusion, boolean, inset, cavity, or topology event is performed.
"""
import math
import bmesh
import bpy
from mathutils import Matrix, Vector
from . import extrusion as ex


def validate_convex(bm):
    bm.normal_update();bm.verts.index_update();bm.verts.ensure_lookup_table()
    bm.faces.index_update();bm.faces.ensure_lookup_table()
    if len(bm.verts)>256 or len(bm.faces)>256:
        raise ValueError('Inward movement supports small convex cube/prism-like solids (≤256 faces/vertices)')
    if len(bm.verts)-len(bm.edges)+len(bm.faces)!=2:
        raise ValueError('Inward movement needs one convex closed solid')
    visited=set();pending=[bm.verts[0]] if bm.verts else []
    while pending:
        v=pending.pop()
        if v in visited:continue
        visited.add(v);pending.extend(e.other_vert(v) for e in v.link_edges)
    if len(visited)!=len(bm.verts):raise ValueError('Disconnected geometry is unsupported')
    # Each face must be a strictly convex planar supporting polygon. Combined
    # with a connected closed outward oriented sphere this bounds one convex
    # solid, excluding inverted, internal, duplicated and crossing surfaces.
    for f in bm.faces:ex.validate_face(bm,f.index)
    signatures=set()
    for f in bm.faces:
        key=tuple(sorted(tuple(round(x,7) for x in v.co) for v in f.verts))
        if key in signatures:raise ValueError('Duplicate face geometry')
        signatures.add(key)
    return bm.calc_volume(signed=True)


class InwardPlan:
    def __init__(self,obj,index):
        ex.validate_object(obj)
        bm=bmesh.new()
        try:
            bm.from_mesh(obj.data);bm.verts.ensure_lookup_table();bm.faces.ensure_lookup_table()
            self.volume=validate_convex(bm)
            face=bm.faces[index];self.indices=[v.index for v in face.verts]
            matrix=obj.matrix_world;normal_matrix=matrix.to_3x3().inverted().transposed()
            normals=[(normal_matrix@f.normal).normalized() for f in bm.faces]
            positions=[matrix@v.co for v in bm.verts]
            self.normal=normals[index];anchor=positions[self.indices[0]]
            selected=set(self.indices);limits=[];self.steps={}
            # Earliest contact of the moving face plane with ANY fixed vertex.
            # This includes previous cap rings and prism/taper corners.
            for v in bm.verts:
                if v.index not in selected:
                    gap=(anchor-positions[v.index]).dot(self.normal)
                    if gap<=1e-5:raise ValueError('Inward face shares its plane with fixed geometry')
                    limits.append((gap,'face reaches a fixed vertex/edge'))
            for vertex in face.verts:
                other=[normals[f.index] for f in vertex.link_faces if f!=face]
                step=None
                for i,a in enumerate(other):
                    for b in other[i+1:]:
                        system=Matrix((self.normal,a,b))
                        if abs(system.determinant())>1e-5:
                            step=system.inverted()@Vector((1,0,0));break
                    if step is not None:break
                if step is None or any(abs(n.dot(step))>1e-4 for n in other):
                    raise ValueError('Inward movement cannot preserve these incident side planes')
                self.steps[vertex.index]=matrix.to_3x3().inverted()@step
                point=positions[vertex.index]
                for f,n in zip(bm.faces,normals):
                    if f.index==index:continue
                    rate=-n.dot(step)
                    if rate>1e-6:
                        gap=(positions[f.verts[0].index]-point).dot(n)
                        if gap<=1e-5:raise ValueError('Inward path immediately crosses a side plane')
                        limits.append((gap/rate,'moving vertex reaches another face plane'))
            if not limits:raise ValueError('No finite verified inward travel bound')
            event,self.reason=min(limits,key=lambda item:item[0])
            # Stay strictly before topology changes. World-unit margin plus 1%.
            self.limit=max(0.,event-max(event*.01,1e-4))
            if self.limit<1e-4:raise ValueError('Solid too thin for safe inward movement')
            self.base={v.index:v.co.copy() for v in bm.verts}
            self.limit=min(self.limit,ex.CONFIG.maximum_distance)
            # Verify the most contracted allowed shape before any preview exists.
            self.apply(bm,-self.limit);validate_convex(bm)
        finally:bm.free()

    def apply(self,bm,amount):
        bm.verts.ensure_lookup_table()
        for index,base in self.base.items():
            bm.verts[index].co=base+self.steps.get(index,Vector())*amount
        bm.normal_update()


class SignedPreview:
    """One geometry owner inside the existing transaction, rebuilt only at sign changes."""
    def __init__(self,obj,index,config=ex.CONFIG):
        normal,vertices=ex.face_info(obj,index,config)
        self.obj=obj;self.original=obj.data;self.original_name=obj.data.name
        self.face_index=index;self.config=config;self.world_matrix=obj.matrix_world.copy()
        self.world_normal=(self.world_matrix.to_3x3().inverted().transposed()@normal).normalized()
        self.base_outline=tuple(self.world_matrix@v for v in vertices)
        self.outward=None;self.inward_mesh=None;self.inward_bm=None
        self.amount=self.outward_distance=0.;self.world_vector=Vector()
        self.limit_reason='';self.inward_error=None
        try:self.plan=InwardPlan(obj,index)
        except ValueError as exc:self.plan=None;self.inward_error=str(exc)

    @property
    def mesh(self):return self.outward.mesh if self.outward else self.inward_mesh or self.original
    @property
    def bm(self):return self.outward.bm if self.outward else self.inward_bm

    def clear_preview(self):
        if self.outward:
            self.outward.restore(self.obj);self.outward=None
        if self.inward_mesh:
            if self.obj and self.obj.data==self.inward_mesh:self.obj.data=self.original
            if self.inward_bm:self.inward_bm.free()
            self.inward_bm=None
            if self.inward_mesh.users==0:bpy.data.meshes.remove(self.inward_mesh)
            self.inward_mesh=None

    def update(self,amount):
        if not math.isfinite(amount):raise ValueError('Nonfinite signed extrusion distance')
        self.limit_reason=''
        requested=amount;amount=min(self.config.maximum_distance,amount)
        if amount < 0:
            if self.plan is None:
                amount=0.;self.limit_reason='Inward unsupported: '+self.inward_error
            else:
                amount=max(-self.plan.limit,amount)
                if amount!=requested:self.limit_reason=f'Inward limit {self.plan.limit:.3f}: {self.plan.reason}; safety margin retained'
        elif amount!=requested:self.limit_reason='Maximum outward distance reached'
        if abs(amount)<=self.config.negligible_distance:
            self.clear_preview();amount=0.
        elif amount>0:
            if not self.outward:
                self.clear_preview();self.outward=ex.Preview(self.obj,self.face_index,self.config)
            self.outward.update(amount)
        else:
            if self.inward_mesh is None:
                self.clear_preview();self.inward_mesh=self.original.copy()
                self.inward_mesh.name='Air Inward Preview'
                self.inward_bm=bmesh.new();self.inward_bm.from_mesh(self.original)
            self.plan.apply(self.inward_bm,amount)
            validate_convex(self.inward_bm)
            self.inward_bm.to_mesh(self.inward_mesh);self.inward_mesh.update()
            self.obj.data=self.inward_mesh
        self.amount=self.outward_distance=amount
        self.world_vector=self.world_normal*amount

    def validate_result(self):
        if abs(self.amount)<=self.config.negligible_distance:raise ValueError('Extrusion is negligible')
        if self.outward:self.outward.validate_result()
        else:
            volume=validate_convex(self.inward_bm)
            if not 0<volume<self.plan.volume:raise ValueError('Inward result must shorten the original convex solid')

    def outline(self):
        if self.outward:return self.outward.outline()
        if self.inward_bm:
            self.inward_bm.faces.ensure_lookup_table()
            return tuple(self.world_matrix@v.co for v in self.inward_bm.faces[self.face_index].verts)
        return self.base_outline

    def restore(self,obj):
        # Match the existing edit-mode cleanup path before swapping mesh owners.
        mode=None
        if obj and obj.mode!='OBJECT':
            mode=obj.mode
            with bpy.context.temp_override(object=obj,active_object=obj):bpy.ops.object.mode_set(mode='OBJECT')
        self.obj=obj;self.clear_preview()
        if mode:
            with bpy.context.temp_override(object=obj,active_object=obj):bpy.ops.object.mode_set(mode=mode)
        self.original=None;self.obj=None

    def adopt(self,obj):
        if self.outward:
            self.outward.adopt(obj);self.outward=None
        else:
            if obj.data!=self.inward_mesh:raise RuntimeError('Inward preview ownership changed')
            self.inward_bm.free();self.inward_bm=None
            if self.original.users==0:bpy.data.meshes.remove(self.original)
            self.inward_mesh.name=self.original_name;self.inward_mesh=None
        self.original=None;self.obj=None


def commit(obj,index,amount,config=ex.CONFIG):
    if abs(amount)<=config.negligible_distance:return False
    preview=SignedPreview(obj,index,config)
    try:
        preview.update(amount)
        if abs(preview.amount-amount)>1e-5:raise ValueError('Committed distance differs from verified preview limit')
        preview.validate_result();preview.adopt(obj)
    except Exception:
        preview.restore(obj);raise
    return True
