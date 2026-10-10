import bpy

from .primitives import SHAPES


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
