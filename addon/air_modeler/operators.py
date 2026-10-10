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
            from .bridge import dragging
            if dragging():
                raise RuntimeError("Release or cancel the active drag first")
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


class AIRMODELER_OT_commit_transform(bpy.types.Operator):
    """Apply the final world matrix after the controller restores baseline."""
    bl_idname = "air_modeler.commit_transform"
    bl_label = "Air Modeler Transform"
    bl_options = {"UNDO", "INTERNAL"}

    target_name: bpy.props.StringProperty()
    matrix: bpy.props.FloatVectorProperty(size=16)
    scale_signs: bpy.props.FloatVectorProperty(size=3, default=(1, 1, 1))

    def execute(self, context):
        obj = context.view_layer.objects.get(self.target_name)
        if obj is None or context.mode != 'OBJECT':
            return {'CANCELLED'}
        from mathutils import Matrix
        from .transforms import apply_matrix
        apply_matrix(obj, Matrix(tuple(self.matrix[i:i+4] for i in range(0, 16, 4))), self.scale_signs)
        return {'FINISHED'}
