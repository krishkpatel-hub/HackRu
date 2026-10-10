"""Air Modeler: typed spawning and viewport pinch-and-drag MOVE."""

bl_info = {
    "name": "Air Modeler",
    "author": "HackRU Team",
    "version": (0, 5, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Air Modeler",
    "description": "Hand cursor, picking, undoable transforms, single-face extrusion and primitive creation",
    "category": "Add Mesh",
}

import bpy

from .operators import AIRMODELER_OT_create_primitive, AIRMODELER_OT_commit_transform, AIRMODELER_OT_commit_extrusion
from .panel import AIRMODELER_PT_primitives
from . import bridge

_CLASSES = (AIRMODELER_OT_create_primitive, AIRMODELER_OT_commit_transform, AIRMODELER_OT_commit_extrusion, bridge.AIRMODELER_OT_connect,
            bridge.AIRMODELER_OT_disconnect, AIRMODELER_PT_primitives)


def register():
    registered = []
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.app.handlers.load_pre.append(bridge.on_load_pre)
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    bridge.disconnect("Add-on disabled")
    if bridge.on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(bridge.on_load_pre)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
