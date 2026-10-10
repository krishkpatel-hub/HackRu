"""Air Modeler's first milestone: undoable mesh primitive creation."""

bl_info = {
    "name": "Air Modeler",
    "author": "HackRU Team",
    "version": (0, 1, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Air Modeler",
    "description": "Create four mesh primitives at the 3D cursor",
    "category": "Add Mesh",
}

import bpy

from .operators import AIRMODELER_OT_create_primitive
from .panel import AIRMODELER_PT_primitives

_CLASSES = (AIRMODELER_OT_create_primitive, AIRMODELER_PT_primitives)


def register():
    registered = []
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
