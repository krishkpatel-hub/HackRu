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


class AIRMODELER_OT_commit_extrusion(bpy.types.Operator):
    bl_idname = "air_modeler.commit_extrusion"
    bl_label = "Air Modeler Extrude Face"
    bl_options = {"UNDO", "INTERNAL"}

    target_name: bpy.props.StringProperty()
    face_index: bpy.props.IntProperty()
    distance: bpy.props.FloatProperty()
    maximum_distance: bpy.props.FloatProperty()
    negligible_distance: bpy.props.FloatProperty()

    def execute(self, context):
        from dataclasses import replace
        from . import extrusion
        obj = context.view_layer.objects.get(self.target_name)
        if obj is None or context.mode != 'OBJECT':
            return {'CANCELLED'}
        try:
            config = replace(extrusion.CONFIG, maximum_distance=self.maximum_distance,
                             negligible_distance=self.negligible_distance)
            if not extrusion.commit(obj, self.face_index, self.distance, config):
                return {'CANCELLED'}
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class AIRMODELER_PG_precision(bpy.types.PropertyGroup):
    mode: EnumProperty(name='Operation', items=[(m,m,'') for m in ('MOVE','ROTATE','SCALE','EXTRUDE')], default='ROTATE')
    axis: EnumProperty(name='World axis', items=[(a,a,'') for a in 'XYZ'], default='Z')
    angle: bpy.props.FloatProperty(name='Angle (degrees)', default=45, min=-360, max=360)
    factor: bpy.props.FloatProperty(name='Uniform factor', default=1.5, min=.1, max=10)
    distance: bpy.props.FloatProperty(name='World units', default=2, min=-100, max=100)
    extrusion: bpy.props.FloatProperty(name='Outward world units', default=.5, min=.00002, max=4)


class AIRMODELER_OT_precision_apply(bpy.types.Operator):
    bl_idname = 'air_modeler.precision_apply'
    bl_label = 'Apply to Selected Object'
    bl_description = 'Apply one relative edit; extrusion arms the next face pinch'
    # Blender suppresses nested operator Undo pushes; the outer GUI action
    # supplies one step while sharing the exact inner commit implementation.
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        from . import bridge
        return (context.mode == 'OBJECT' and context.area is not None and context.area.type == 'VIEW_3D'
                and not bridge.dragging() and (bridge._runtime is None or bridge._runtime.phase == 'IDLE'))

    def execute(self, context):
        from . import bridge, transforms
        values = context.window_manager.air_modeler_precision
        amount = {'MOVE':values.distance, 'ROTATE':values.angle, 'SCALE':values.factor, 'EXTRUDE':values.extrusion}[values.mode]
        payload = dict(mode=values.mode, value=amount)
        if values.mode in ('MOVE','ROTATE'):
            payload['axis'] = values.axis
        try:
            if values.mode == 'EXTRUDE':
                if bridge._runtime is None:
                    raise RuntimeError('Connect Blender before arming a face pinch')
                bridge._runtime.set_mode('EXTRUDE', distance=amount, source='sidebar override')
            else:
                transforms.commit_precision(context, payload)
                if bridge._runtime is not None:
                    bridge._runtime.completed_mode()
            bridge.redraw()
        except (RuntimeError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class AIRMODELER_OT_precision_reset(bpy.types.Operator):
    bl_idname = 'air_modeler.precision_reset'
    bl_label = 'Cancel Values'
    bl_description = 'Discard unapplied sidebar values without editing geometry'

    @classmethod
    def poll(cls, context):
        from .bridge import dragging
        return not dragging()

    def execute(self, context):
        values = context.window_manager.air_modeler_precision
        for key in ('mode','axis','angle','factor','distance','extrusion'):
            values.property_unset(key)
        return {'FINISHED'}
