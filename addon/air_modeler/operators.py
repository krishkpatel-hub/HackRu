import bpy
from bpy.props import EnumProperty

from .primitives import SHAPES, create_primitive, validate_context


class AIRMODELER_OT_create_primitive(bpy.types.Operator):
    bl_idname = "air_modeler.create_primitive"
    bl_label = "Create Air Modeler Primitive"
    bl_description = "Create and select a mesh at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    shape: EnumProperty(name="Shape", items=SHAPES, default="cube")

    @classmethod
    def poll(cls, context):
        try:
            validate_context(context)
        except RuntimeError as exc:
            cls.poll_message_set(str(exc))
            return False
        return True

    def execute(self, context):
        try:
            create_primitive(context, self.shape)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}
