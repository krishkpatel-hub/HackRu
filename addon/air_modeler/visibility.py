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


def visible_faces(obj,context,view,ray_trees=None):
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
            if mesh.polygons:
                tree=BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in mesh.polygons])
                trees.append(tree)
                if ray_trees is not None:ray_trees.append((other==obj,tree))
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


def observability(normal,mapping):
    horizontal=Vector(mapping.horizontal);vertical=Vector(mapping.vertical)
    if mapping.axis!='NONE':
        component='XYZ'.index(mapping.axis)
        horizontal=Vector(tuple(v if i==component else 0. for i,v in enumerate(horizontal)))
        vertical=Vector(tuple(v if i==component else 0. for i,v in enumerate(vertical)))
    return math.hypot(normal.dot(horizontal),normal.dot(vertical))


def cursor_face(faces,view,uv,trees):
    """Ray under the displayed corrected Right cursor; reject occlusion/edge ties.

    Cache the evaluated scene BVHs alongside visible faces. The controller's
    scene/view invalidation refreshes targeting and cancels locked operations.
    """
    origin,direction=viewport.ray(view,uv)
    hits=[]
    for target,tree in trees:
        point,normal,index,distance=tree.ray_cast(origin,direction)
        if point is not None and distance>=0:hits.append((distance,target,index))
    if not hits:return None
    hits.sort();distance,target,index=hits[0]
    if not target:return None
    if any(not target and abs(depth-distance)<=max(1e-5,distance*1e-6) for depth,target,_ in hits):return None
    face=next((f for f in faces if f[0]==index),None)
    if face is None:return None
    # A ray exactly on a shared edge has no unique face. Require the displayed
    # cursor to be at least three pixels inside the polygon, not on its border.
    pixel=Vector(viewport.pixels(view[0],uv))
    outline=[projected(view,point) for point in face[3]]
    if any(point is None for point in outline):return None
    for a,b in zip(outline,outline[1:]+outline[:1]):
        edge=b-a
        if edge.length_squared<1e-9:return None
        closest=a+edge*max(0.,min(1.,(pixel-a).dot(edge)/edge.length_squared))
        if (pixel-closest).length<3:return None
    return index
