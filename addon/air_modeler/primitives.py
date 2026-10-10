"""Mesh construction without nested Blender operators or undo pushes."""

import math
import threading

import bmesh
import bpy

SHAPES = (
    ("cube", "Cube", "Create a cube with side length 2"),
    ("sphere", "Sphere", "Create a UV sphere with radius 1"),
    ("cylinder", "Cylinder", "Create a cylinder with radius 1 and depth 2"),
    ("prism", "Triangular Prism", "Create a three-sided cylinder with flat caps"),
)
_NAMES = {identifier: label for identifier, label, _ in SHAPES}


def validate_context(context):
    """Raise RuntimeError before mutation if creation cannot be supported."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Air Modeler must run on Blender's main thread")
    scene = getattr(context, "scene", None)
    # Blender may derive view_layer from scene, so do not access it without one.
    if scene is None:
        raise RuntimeError("Air Modeler requires a scene and active view layer")
    view_layer = getattr(context, "view_layer", None)
    if view_layer is None:
        raise RuntimeError("Air Modeler requires a scene and active view layer")
    if view_layer not in list(scene.view_layers):
        raise RuntimeError("The active view layer must belong to the current scene")
    if getattr(context, "mode", None) != "OBJECT":
        raise RuntimeError("Air Modeler requires Object Mode; leave the current mode first")
    if not scene.is_editable:
        raise RuntimeError("Air Modeler requires an editable scene")
    layer = view_layer.active_layer_collection
    if layer is None:
        raise RuntimeError("Choose a visible collection in the active view layer")
    collection = layer.collection
    if not collection.is_editable or collection.hide_select or collection.hide_viewport:
        raise RuntimeError("Choose an editable, visible, selectable collection")
    # Check explicit restrictions: is_visible may be false for an empty root.
    def restricted_ancestor(node, restricted=False):
        restricted = (restricted or node.exclude or node.hide_viewport
                      or node.collection.hide_select or node.collection.hide_viewport)
        if node == layer:
            return restricted
        return any(restricted_ancestor(child, restricted) for child in node.children)

    if restricted_ancestor(view_layer.layer_collection):
        raise RuntimeError("The active collection has a hidden or unselectable parent")
    if not all(math.isfinite(value) for value in scene.cursor.location):
        raise RuntimeError("The 3D cursor location must contain finite coordinates")


def create_primitive(context: bpy.types.Context, shape: str) -> bpy.types.Object:
    """Create/select a mesh; ValueError for shape, RuntimeError for context.

    Main thread and Object Mode only. This helper does not create an undo step:
    interactive callers must use air_modeler.create_primitive. On construction
    failure, remove new datablocks and restore the previous selection/active object.
    """
    if not isinstance(shape, str) or shape not in _NAMES:
        raise ValueError("Unknown shape; expected cube, sphere, cylinder, or prism")
    validate_context(context)
    view_layer = context.view_layer
    selected = [obj for obj in view_layer.objects if obj.select_get(view_layer=view_layer)]
    active = view_layer.objects.active
    mesh = obj = None
    bm = bmesh.new()
    try:
        if shape == "cube":
            bmesh.ops.create_cube(bm, size=2.0)
        elif shape == "sphere":
            bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
        else:
            bmesh.ops.create_cone(
                bm, cap_ends=True, cap_tris=False,
                segments=3 if shape == "prism" else 32,
                radius1=1.0, radius2=1.0, depth=2.0,
            )
        mesh = bpy.data.meshes.new(f"Air {_NAMES[shape]} Mesh")
        bm.to_mesh(mesh)
        mesh.update()
        obj = bpy.data.objects.new(f"Air {_NAMES[shape]}", mesh)
        obj.location = context.scene.cursor.location.copy()
        view_layer.active_layer_collection.collection.objects.link(obj)
        view_layer.update()
        for previous in selected:
            previous.select_set(False, view_layer=view_layer)
        obj.select_set(True, view_layer=view_layer)
        view_layer.objects.active = obj
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        for previous in selected:
            previous.select_set(True, view_layer=view_layer)
        view_layer.objects.active = active
        raise
    finally:
        bm.free()
