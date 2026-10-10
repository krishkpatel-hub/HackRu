"""Cached viewport-visible extrusion faces. No render-camera dependency."""
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from . import viewport,extrusion


def mesh_stamp(mesh):
    # Includes supported attributes/material slots so an externally edited
    # baseline cannot be committed using a stale preview of its old attributes.
    attributes=[]
    for attribute in mesh.attributes:
        field={'FLOAT_VECTOR':'vector','FLOAT2':'vector','FLOAT_COLOR':'color','BYTE_COLOR':'color'}.get(attribute.data_type,'value')
        values=[]
        for item in attribute.data:
            value=getattr(item,field,None)
            values.append(tuple(value) if hasattr(value,'__iter__') else value)
        attributes.append((attribute.name,attribute.domain,attribute.data_type,tuple(values)))
    return (mesh.as_pointer(),tuple(tuple(v.co) for v in mesh.vertices),
            tuple(tuple(e.vertices) for e in mesh.edges),
            tuple((tuple(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons),
            tuple(attributes),tuple(m.as_pointer() if m else None for m in mesh.materials))


def view_unchanged(context,view):
    current=viewport.mapping(context)
    return (current[0].width==view[0].width and current[0].height==view[0].height
        and current[1].is_perspective==view[1].is_perspective
        and all(abs(a-b)<1e-6 for x,y in zip(current[1].perspective_matrix,view[1].perspective_matrix) for a,b in zip(x,y)))


def scene_stamp(context,exclude):
    # Evaluated geometry catches modifiers/animation/curve edits too. This is
    # checked at 4 Hz and completion, not on every camera frame.
    with bpy.context.temp_override(**context):graph=bpy.context.evaluated_depsgraph_get()
    if any(instance.is_instance for instance in graph.object_instances):
        raise ValueError('Instanced occluders unsupported; isolate the demo objects')
    records=[];total=0;polygons=0
    for obj in context['view_layer'].objects:
        if obj==exclude or obj.type not in ('MESH','CURVE','SURFACE','FONT','META'):continue
        if not obj.visible_get(view_layer=context['view_layer'],viewport=context['area'].spaces.active):continue
        if len(records)>=128:raise ValueError('Visibility scene budget exceeded')
        evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
        try:
            total+=len(mesh.vertices);polygons+=len(mesh.polygons)
            if total>100000 or polygons>100000:raise ValueError('Visibility geometry budget exceeded')
            records.append((obj.as_pointer(),tuple(x for row in evaluated.matrix_world for x in row),
                tuple(tuple(v.co) for v in mesh.vertices),tuple(tuple(p.vertices) for p in mesh.polygons)))
        finally:evaluated.to_mesh_clear()
    return tuple(records)


def projected(view,point):
    clip=view[1].perspective_matrix@point.to_4d()
    if clip.w<=1e-8 or not -clip.w<=clip.z<=clip.w:return None
    return Vector(((clip.x/clip.w+1)*view[0].width/2,(clip.y/clip.w+1)*view[0].height/2))


def samples(outline):
    # Triangle-fan interior grid includes center and near-edge/corner samples.
    # At most 30 probes/quad; a blocked center does not exclude visible edges.
    center=sum(outline,Vector())/len(outline)
    yield center
    for v in outline:yield center*.06+v*.94
    for i in range(1,len(outline)-1):
        a,b,c=outline[0],outline[i],outline[i+1]
        for x in range(1,5):
            for y in range(1,6-x):
                yield (a*x+b*y+c*(6-x-y))/6


def visible_faces(obj,context,view):
    space=context['area'].spaces.active
    if space.shading.type=='WIREFRAME' or space.shading.show_xray:
        raise ValueError('Extrusion visibility requires a solid viewport with X-Ray off')
    if len(obj.data.polygons)>256:raise ValueError('Too many extrusion faces; use a simple cube/prism mesh')
    faces=extrusion.candidates(obj)
    with bpy.context.temp_override(**context):
        graph=bpy.context.evaluated_depsgraph_get()
    trees=[];total=0;polygons=0
    for other in context['view_layer'].objects:
        if other.type not in ('MESH','CURVE','SURFACE','FONT','META') or not other.visible_get(view_layer=context['view_layer'],viewport=space):continue
        if len(trees)>=128:raise ValueError('Visibility scene budget exceeded; isolate the demo objects')
        evaluated=other.evaluated_get(graph);mesh=evaluated.to_mesh()
        try:
            total+=len(mesh.vertices);polygons+=len(mesh.polygons)
            if total>100000 or polygons>100000:raise ValueError('Visibility geometry budget exceeded; isolate the demo objects')
            vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
            if mesh.polygons:trees.append(BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in mesh.polygons]))
        finally:evaluated.to_mesh_clear()
    if any(instance.is_instance for instance in graph.object_instances):
        raise ValueError('Instanced occluders unsupported; make demo geometry real or isolate it')
    eye=view[1].view_matrix.inverted().translation
    toward=view[1].view_matrix.inverted().col[2].xyz.normalized()
    accepted=[];diagnostics=[]
    for index,normal,center,outline in faces:
        record=dict(face=index,visible=False,reason='',area=0,clear_samples=0)
        ray_to_eye=(eye-center).normalized() if view[1].is_perspective else toward
        if normal.dot(ray_to_eye)<.04:
            record['reason']='back-facing or edge-on';diagnostics.append(record);continue
        points=[projected(view,p) for p in outline]
        if any(p is None for p in points):
            record['reason']='behind view clipping plane';diagnostics.append(record);continue
        area=abs(sum(points[i].x*points[(i+1)%len(points)].y-points[(i+1)%len(points)].x*points[i].y for i in range(len(points))))/2
        record['area']=round(area,2)
        if area<16:
            record['reason']='projected area below 16 pixels²';diagnostics.append(record);continue
        for point in samples(outline):
            pixel=projected(view,point)
            if pixel is None or not (0<=pixel.x<=view[0].width and 0<=pixel.y<=view[0].height):continue
            uv=pixel.x/view[0].width,1-pixel.y/view[0].height
            origin,direction=viewport.ray(view,uv)
            distance=(point-origin).dot(direction)
            if distance<=0:continue
            epsilon=max(1e-5,distance*1e-6)
            if all(tree.ray_cast(origin,direction,max(0,distance-epsilon))[0] is None for tree in trees):
                record['clear_samples']+=1
        record['visible']=record['clear_samples']>0
        record['reason']='unoccluded sample' if record['visible'] else 'occluded or outside viewport'
        if record['visible']:accepted.append((index,normal,center,outline))
        diagnostics.append(record)
    return accepted,diagnostics


def choose(faces,vector,mapping,previous=None):
    """Magnitude chooses a visible face; sign is kept for outward/inward intent."""
    direction=Vector(vector)
    if direction.length<1e-8:return None,[], 'Drag along the selected mapping axis'
    direction.normalize();ranked=[]
    for index,normal,center,outline in faces:
        h=normal.dot(Vector(mapping.horizontal));v=normal.dot(Vector(mapping.vertical))
        if mapping.axis!='NONE':
            h*=abs(Vector(mapping.horizontal)['XYZ'.index(mapping.axis)])
            v*=abs(Vector(mapping.vertical)['XYZ'.index(mapping.axis)])
        observable=math.hypot(h,v)
        alignment=normal.dot(direction)
        ranked.append(dict(face=index,alignment=alignment,observable=observable))
    useful=[r for r in ranked if r['observable']>=.25]
    useful.sort(key=lambda r:(-abs(r['alignment']),r['face']))
    if not useful:return None,ranked,f'Visible normals cannot use {mapping.plane}/{mapping.axis}; choose another plane/axis or view'
    best=useful[0];lookup={f[0]:f for f in faces}
    competitors=[r for r in useful[1:] if lookup[r['face']][1].dot(lookup[best['face']][1])<.999]
    margin=.10 if best['face']==previous else .12
    if abs(best['alignment'])<.55 or competitors and abs(best['alignment'])-abs(competitors[0]['alignment'])<margin:
        return None,ranked,'Drag more clearly toward one visible face'
    equivalent=[r for r in useful if lookup[r['face']][1].dot(lookup[best['face']][1])>=.999]
    # Parallel normals alone do not make edits equivalent: adjacent coplanar
    # quads (e.g. a previous cap's side ring) would deform different patches.
    def patch(record):
        face=lookup[record['face']]
        return (tuple(round(v,6) for v in face[2]),
                tuple(sorted(tuple(round(v,6) for v in p) for p in face[3])))
    if any(patch(r)!=patch(best) for r in equivalent):
        return None,ranked,'Several visible faces share this direction; expose one distinct face or use a simpler mesh'
    chosen=min(equivalent,key=lambda r:r['face'])
    return lookup[chosen['face']],ranked,''
