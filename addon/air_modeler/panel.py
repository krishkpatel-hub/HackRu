import bpy
import textwrap

from .primitives import SHAPES
from . import bridge


class AIRMODELER_PT_primitives(bpy.types.Panel):
    bl_label = "Air Modeler"
    bl_idname = "AIRMODELER_PT_primitives"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Air Modeler"

    def draw(self, context):
        layout = self.layout
        if context.mode != "OBJECT":
            layout.label(text="Switch to Object Mode to create meshes", icon="INFO")
        column = layout.column(align=True)
        for shape, label, _ in SHAPES:
            column.operator("air_modeler.create_primitive", text=f"Create {label}").shape = shape
        box = layout.box()
        state, message, error, running = bridge.ui_state()
        box.label(text=f"Bridge: {state}")
        row = box.row(align=True)
        row.operator("air_modeler.connect")
        row.operator("air_modeler.disconnect")
        for line in textwrap.wrap(error or message, width=40)[:6]:
            box.label(text=line)
