import bpy
from bpy.props import EnumProperty

from .primitives import SHAPES, create_primitive, validate_context, remove_primitive


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


class AIRMODELER_OT_remove_primitive(bpy.types.Operator):
    bl_idname = "air_modeler.remove_primitive"
    bl_label = "Remove Selected Air Modeler Primitive"
    bl_description = "Remove only one selected object matching its recorded creation shape"
    bl_options = {"REGISTER", "UNDO"}

    shape: EnumProperty(name="Shape", items=SHAPES, default="cube")

    def execute(self, context):
        try:
            from .bridge import dragging
            if dragging():
                raise RuntimeError("Release or cancel the active gesture first")
            remove_primitive(context, self.shape)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


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
    vector: bpy.props.FloatVectorProperty(size=3)
    use_vector: bpy.props.BoolProperty(default=False)
    use_signed: bpy.props.BoolProperty(default=False)
    maximum_distance: bpy.props.FloatProperty()
    negligible_distance: bpy.props.FloatProperty()

    def execute(self, context):
        from dataclasses import replace
        from . import extrusion, signed_extrusion
        obj = context.view_layer.objects.get(self.target_name)
        if obj is None or context.mode != 'OBJECT':
            return {'CANCELLED'}
        try:
            config = replace(extrusion.CONFIG, maximum_distance=self.maximum_distance,
                             negligible_distance=self.negligible_distance)
            commit = signed_extrusion.commit if self.use_signed else extrusion.commit_vector if self.use_vector else extrusion.commit
            value = tuple(self.vector) if self.use_vector and not self.use_signed else self.distance
            if not commit(obj, self.face_index, value, config):
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
    plane: EnumProperty(name='Mapping plane', items=[(p,p,'') for p in ('AUTO','XY','XZ','YZ')], default='AUTO')
    rotation_constraint: EnumProperty(name='Gesture rotation', items=[(a,a,'') for a in ('FREE','X','Y','Z')], default='FREE')
    diagnostics: bpy.props.BoolProperty(name='Diagnostics (2 Hz console)', default=False)
    scale_sensitivity: bpy.props.FloatProperty(name='Scale log gain', default=1.38629436112, min=.2, max=4.)
    rotation_sensitivity: bpy.props.FloatProperty(name='Rotation gain', default=1., min=.2, max=3.)
    extrusion_sensitivity: bpy.props.FloatProperty(name='Extrude units / image height', default=12., min=1., max=40.)
    plane_axis: EnumProperty(name='Plane axis', items=[(a,a,'') for a in ('NONE','X','Y','Z')], default='NONE')
    move_threshold: bpy.props.FloatProperty(name='Right palm move threshold', default=.035, min=.005, max=.2)
    twist_threshold: bpy.props.FloatProperty(name='Twist threshold (degrees)', default=8, min=2, max=45)
    openness_threshold: bpy.props.FloatProperty(name='Whole-hand openness threshold', default=.15, min=.03, max=.5)
    intent_persistence: bpy.props.FloatProperty(name='Intent persistence (seconds)', default=.15, min=.05, max=.5)
    intent_dominance: bpy.props.FloatProperty(name='Intent dominance', default=1.35, min=1.1, max=3)
    intent_hysteresis: bpy.props.FloatProperty(name='Intent retain score', default=.75, min=.25, max=.95)
    extrusion: bpy.props.FloatProperty(name='Outward world units', default=.5, min=.00002, max=4)


class AIRMODELER_OT_precision_apply(bpy.types.Operator):
    bl_idname = 'air_modeler.precision_apply'
    bl_label = 'Apply to Selected Object'
    bl_description = 'Apply one relative edit; in two-hand mode fixed extrusion needs Left face selection and a fresh Right pinch'
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
                    raise RuntimeError('Connect Blender before arming fixed extrusion')
                bridge._runtime.set_mode('EXTRUDE', distance=amount, source='sidebar override',plane=values.plane,plane_axis=values.plane_axis)
                bridge.redraw()
                return {'CANCELLED'}  # Arming stages state; it must not push a geometry Undo entry.
            else:
                if not transforms.commit_precision(context, payload):
                    return {'CANCELLED'}  # Unchanged values must not add an outer Undo entry.
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
        for key in ('mode','axis','angle','factor','distance','extrusion','plane','plane_axis'):
            values.property_unset(key)
        return {'FINISHED'}


class AIRMODELER_OT_arm_gesture(bpy.types.Operator):
    bl_idname = 'air_modeler.arm_gesture'
    bl_label = 'Arm Next Gesture'
    bl_description = 'Override motion classification once; keeps required clutch and manipulation poses'

    @classmethod
    def poll(cls, context):
        from . import bridge
        return bridge._runtime is not None and bridge._runtime.phase == 'IDLE' and not bridge.dragging()

    def execute(self, context):
        from . import bridge
        values = context.window_manager.air_modeler_precision
        try:
            bridge._runtime.set_mode(values.mode, values.rotation_constraint if values.mode=='ROTATE' else values.axis, source='sidebar override',
                plane=values.plane if values.mode == 'EXTRUDE' else 'AUTO',
                plane_axis=values.plane_axis if values.mode == 'EXTRUDE' else 'NONE')
            bridge.redraw()
        except (RuntimeError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class AIRMODELER_OT_cancel(bpy.types.Operator):
    bl_idname = 'air_modeler.cancel'
    bl_label = 'Cancel Selection / Preview'

    @classmethod
    def poll(cls, context):
        from . import bridge
        return bridge._runtime is not None

    def execute(self, context):
        from . import bridge
        bridge._runtime.handle({'type':'command','payload':{'action':'cancel'}})
        return {'FINISHED'}


class AIRMODELER_OT_undo(bpy.types.Operator):
    bl_idname = 'air_modeler.undo'
    bl_label = 'Undo Completed Edit'

    @classmethod
    def poll(cls, context):
        from . import bridge
        return bridge._runtime is not None

    def execute(self, context):
        from . import bridge
        # This wrapper is not UNDO: the existing native history is consumed once.
        bridge._runtime.handle({'type':'command','payload':{'action':'undo'}})
        return {'FINISHED'}
