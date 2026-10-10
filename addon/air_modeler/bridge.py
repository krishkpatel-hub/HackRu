"""One main-thread controller owns transport, gesture preview and passive drawing."""

import errno
import select
import socket
import time
from types import SimpleNamespace

from . import viewport, transforms, extrusion, intent, planes, visibility, signed_extrusion
from .selection import Selector
import math

import bpy
from bpy.app.handlers import persistent

try:
    from . import _protocol as protocol  # Generated only inside the distribution ZIP.
except ImportError:
    from shared import protocol  # Source checkout development.

_runtime = None
_state = "Disconnected"
_message = "Start the companion, then Connect"
_last_error = None
_needs_release = False
_release_hands = set()


def dragging():
    return _runtime is not None and _runtime.drag is not None


def ui_state():
    return _state, _message, _last_error, _runtime is not None


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def disconnect(message="Disconnected", error=None):
    global _runtime, _state, _message, _last_error
    runtime, _runtime = _runtime, None
    if runtime is not None:
        runtime.close()
    _state = "Disconnected"
    _message, _last_error = message, error
    redraw()


@persistent
def on_load_pre(_):
    disconnect("File load: reconnect from the intended viewport")


class Client:
    def __init__(self, context):
        if context.window is None or context.area is None or context.area.type != "VIEW_3D":
            raise RuntimeError("Connect from a 3D Viewport")
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if region is None or context.scene is None or context.view_layer is None:
            raise RuntimeError("A viewport window, scene and view layer are required")
        # Resolve RNA again for each tick/action: Undo can invalidate scene references.
        self.window_id = context.window.as_pointer()
        self.area_id = context.area.as_pointer()
        self.region_id = region.as_pointer()
        self.scene_name = context.scene.name
        self.layer_name = context.view_layer.name
        self.timer = None
        self.wm = context.window_manager
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(False)
        self.channel = protocol.Channel()
        self.session = protocol.Session("client")
        self.connecting = True
        self.deadline = time.monotonic() + 5
        self.next_status = 0
        self.next_poll = 0
        self.tracking = False
        self.last_input = 0
        self.last_present = 0
        self.face_outline = ()
        self.target_message = ""
        self.cursor = None
        self.hovered = None
        self.drag = None
        self.mode, self.axis = "MOVE", "Z"
        self.selector = Selector()
        self.hand_status = ''
        self.clutch = False
        self.frame_id, self.frame_time, self.frame_origin = 0, -1.0, None
        self.release_hands = set(_release_hands)
        self.plane, self.plane_axis = 'AUTO', 'NONE'
        self.override = False
        self.fixed_distance = None
        self.source = "single-hand/manual"
        self.phase = "NEEDS_RELEASE" if _needs_release else "IDLE"
        self.seen_gestures = set()
        self.draw_handler = None
        try:
            result = self.sock.connect_ex(protocol.ADDRESS)
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, errno.EISCONN):
                raise OSError(result, "Could not connect to companion at 127.0.0.1:8765")
            self.draw_handler = bpy.types.SpaceView3D.draw_handler_add(viewport.draw, (self,), 'WINDOW', 'POST_PIXEL')
        except Exception:
            self.sock.close()
            raise

    def context(self):
        window = next((w for w in bpy.context.window_manager.windows if w.as_pointer() == self.window_id), None)
        if window is None:
            raise RuntimeError("Initiating Blender window was closed")
        area = next((a for a in window.screen.areas if a.as_pointer() == self.area_id), None)
        if area is None or area.type != "VIEW_3D":
            raise RuntimeError("Initiating viewport changed or was closed; reconnect")
        region = next((r for r in area.regions if r.as_pointer() == self.region_id and r.type == "WINDOW"), None)
        if region is None or window.scene.name != self.scene_name or window.view_layer.name != self.layer_name:
            raise RuntimeError("Initiating scene, view layer or viewport region changed; reconnect")
        return dict(window=window, area=area, region=region, scene=window.scene, view_layer=window.view_layer)

    def close(self):
        self.cancel_drag(require_release=self.drag is not None or self.phase == 'NEEDS_RELEASE')
        if self.draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None
        if self.timer is not None:
            try:
                self.wm.event_timer_remove(self.timer)
            except (ReferenceError, RuntimeError):
                pass
        self.timer = None
        self.sock.close()
        self.wm = None
        self.channel = protocol.Channel()
        self.session = protocol.Session("client")
        self.tracking = False
        self.cursor = self.hovered = None
        self.face_outline = ()
        self.seen_gestures.clear()

    def error(self, error):
        global _last_error, _message
        _last_error = str(error)[:1024]
        _message = "Input rejected"
        self.next_status = 0

    def target(self):
        if self.drag is None:
            return None
        return next((obj for obj in bpy.data.objects if obj.session_uid == self.drag.target_id), None)

    def mode_label(self):
        axis=self.drag.axis if self.drag and self.drag.mode=="ROTATE" else self.axis
        if not self.clutch and axis=="FREE":axis="Z"
        label = ("ROTATE free" if axis=="FREE" else f"ROTATE world {axis}") if self.mode == "ROTATE" else self.mode
        if self.drag and self.drag.mode == "ROTATE":
            label += f" {math.degrees(self.drag.amount):+.1f}°"
        elif self.drag and self.drag.mode == "SCALE":
            label += f" {self.drag.amount:.3f}x"
        elif self.drag and self.drag.mode == "EXTRUDE":
            label += f" {self.drag.amount:.3f} units"
        if self.fixed_distance is not None and self.drag is None:
            label += f" fixed {self.fixed_distance:.3f} units"
        if self.clutch and self.drag and self.drag.mode == 'EXTRUDE' and self.drag.geometry:
            vector = self.drag.geometry.world_vector
            mapping = self.drag.plane
            label += f" {mapping.plane}/{mapping.axis} ({vector.x:+.2f},{vector.y:+.2f},{vector.z:+.2f})"
        elif self.mode == 'EXTRUDE':
            label += f" {self.plane}/{self.plane_axis}"
        return label + f" [{self.source}]"

    def set_mode(self, mode, axis="Z", *, source="voice override", distance=None, plane="AUTO", plane_axis="NONE"):
        if self.drag:
            raise RuntimeError("Release or cancel the active drag first")
        if mode not in {"MOVE", "ROTATE", "SCALE", "EXTRUDE"}:
            raise RuntimeError(f"{mode} is not implemented in this milestone")
        if distance is not None:
            protocol.validate_precision(dict(id='internal', action='precision', mode=mode, value=distance))
        protocol.validate_mode(dict(id='internal', action='set_mode', mode=mode,
            **({'axis': axis} if mode == 'ROTATE' else {'plane':plane, 'axis':plane_axis} if mode == 'EXTRUDE' else {})))
        self.mode, self.axis = mode, axis
        self.plane, self.plane_axis = plane, plane_axis
        self.override = source != "automatic selector"
        self.fixed_distance = distance
        self.source = source
        self.face_outline = ()
        self.target_message = "Point at a flat convex outer triangle/quad" if mode == "EXTRUDE" else ""
        self.next_status = 0

    def automatic_mode(self):
        if self.selector.enabled and not self.override and self.drag is None and self.phase == 'IDLE':
            mode = self.selector.mode(time.monotonic())
            if mode != self.mode or self.source != 'automatic selector':
                self.set_mode(mode, source='automatic selector')

    def completed_mode(self):
        self.override = False
        self.fixed_distance = None
        self.mode, self.axis = 'MOVE', 'Z'
        self.plane, self.plane_axis = 'AUTO', 'NONE'
        self.source = 'Left clutch / Right whole hand' if self.clutch else 'single-hand/manual'
        self.automatic_mode()

    def cancel_drag(self, *, preserve_mode=False, require_release=True):
        global _needs_release, _release_hands
        # Idle command cancellation/disconnect need no new hand observation.
        # Actual previews, failed selection callers and existing gates retain
        # the conservative release requirement, including across reconnects.
        require_release = require_release or self.drag is not None or self.phase == 'NEEDS_RELEASE'
        if self.drag and hasattr(self.drag, 'owner'):
            self.release_hands = set(self.drag.required)
        if not require_release:
            self.release_hands.clear()
            _release_hands.clear()
        if self.clutch:
            _release_hands = set(self.release_hands)
        obj = self.target()
        if self.drag and self.drag.geometry is not None:
            self.drag.geometry.restore(obj)
        if obj is not None:
            transforms.apply_matrix(obj, self.drag.baseline, self.drag.scale_signs)
        self.face_outline = ()
        self.drag = None
        self.phase = "NEEDS_RELEASE" if require_release else "IDLE"
        if not preserve_mode:
            self.completed_mode()
        _needs_release = bool(require_release)
        self.next_status = 0

    def observe(self, uv):
        global _last_error
        self.cursor = uv
        self.tracking = True
        self.last_present = self.last_input = time.monotonic()
        if self.mode == "EXTRUDE":
            if self.drag:
                self.face_outline = self.drag.geometry.outline() if self.drag.geometry else self.face_outline
                return
            hit, error = viewport.pick_extrusion(self.context(), viewport.mapping(self.context()), uv)
            self.hovered = hit[0].name if hit else None
            self.face_outline = hit[3] if hit else ()
            self.target_message = f"Face {hit[2]}: ready" if hit else error
            _last_error = error
            return
        hit, _ = viewport.pick(self.context(), viewport.mapping(self.context()), uv)
        self.hovered = hit[0].name if hit else None

    def preview(self, uv):
        obj = self.target()
        if obj is None:
            self.cancel_drag()
            return
        drag = self.drag
        if drag.mode == "EXTRUDE":
            drag.amount = drag.fixed_distance if drag.fixed_distance is not None else extrusion.distance(drag.start[1], uv[1], drag.geometry.config)
            drag.geometry.update(drag.amount)
            self.face_outline = drag.geometry.outline()
            return
        if drag.mode != "MOVE":
            matrix, drag.amount = transforms.preview_matrix(
                drag.baseline, drag.mode, drag.axis, drag.start, uv, drag.config)
            transforms.apply_matrix(obj, matrix, drag.scale_signs)
            return
        current = viewport.plane_point(drag.view, uv, drag.point, drag.normal)
        if current is None:
            return
        delta = current - drag.grab
        if delta.length > drag.max_delta:
            return
        matrix = drag.baseline.copy()
        matrix.translation += delta
        transforms.apply_matrix(obj, matrix, drag.scale_signs)

    def gesture(self, kind, payload):
        global _needs_release, _last_error, _message
        now = time.monotonic()
        if kind == "hand_frame":
            self.last_input = now
            if not payload["present"]:
                self.tracking, self.hovered = False, None
                return
            self.observe((payload["u"], payload["v"]))
            if self.phase == "NEEDS_RELEASE" and not payload["pinching"]:
                self.phase, _needs_release = "IDLE", False
                self.automatic_mode()
            if self.drag and payload["pinching"]:
                self.preview(self.cursor)
            return
        identifier = payload["gesture_id"]
        if kind == "gesture_start":
            if identifier in self.seen_gestures:
                return
            if len(self.seen_gestures) >= 4096:
                raise protocol.SessionFull("Gesture history full; reconnect")
            self.seen_gestures.add(identifier)
            if self.phase != "IDLE":
                return
            context = self.context()
            with bpy.context.temp_override(**context):
                if bpy.context.mode != "OBJECT":
                    self.error("Transforms require Object Mode")
                    self.cancel_drag()
                    return
            uv = payload["u"], payload["v"]
            view = viewport.mapping(context)
            face_index = None
            rejection = None
            if self.mode == "EXTRUDE":
                face_hit, rejection = viewport.pick_extrusion(context, view, uv)
                hit = face_hit[:2] if face_hit else None
                face_index = face_hit[2] if face_hit else None
                rejected = rejection is not None
            else:
                hit, rejected = viewport.pick(context, view, uv)
            self.observe(uv)
            if hit is None:
                self.error(rejection or ("Unsupported target: use an editable unparented mesh without modifiers, constraints or animation" if rejected else "Pinch missed; release before trying again"))
                self.cancel_drag(preserve_mode=True)
                return
            obj, point = hit
            normal = view[1].view_matrix.inverted().col[2].xyz.normalized()
            grab = viewport.plane_point(view, uv, point, normal)
            if grab is None:
                self.cancel_drag()
                return
            for selected in context["view_layer"].objects:
                if selected.select_get():
                    selected.select_set(False)
            obj.select_set(True)
            context["view_layer"].objects.active = obj
            self.drag = SimpleNamespace(identifier=identifier, target_id=obj.session_uid,
                                        baseline=obj.matrix_world.copy(), scale_signs=tuple(obj.scale), view=view,
                                        mode=self.mode, axis="Z" if self.axis=="FREE" else self.axis, start=uv, fixed_distance=self.fixed_distance,
                                        geometry=None, config=transforms.CONFIG, amount=1.0 if self.mode == "SCALE" else 0.0,
                                        point=point, normal=normal, grab=grab,
                                        max_delta=max(100, (point - viewport.ray(view, uv)[0]).length * 10))
            if self.mode == "EXTRUDE":
                self.drag.geometry = extrusion.Preview(obj, face_index, extrusion.CONFIG)
                self.preview(uv)
                self.face_outline = self.drag.geometry.outline()
            self.phase = "DRAGGING"
            _last_error, _message = None, f"{self.mode_label()}: release to commit; Escape to cancel"
            return
        if not self.drag or identifier != self.drag.identifier:
            return
        if kind == "gesture_cancel":
            self.cancel_drag()
            _message = "Cancelled: " + payload["reason"]
        elif kind == "gesture_end":
            # End carries the release-onset position, even when it differs from
            # the last frame. It is itself a fresh valid observation.
            self.observe((payload["u"], payload["v"]))
            self.preview(self.cursor)
            obj = self.target()
            if obj is None:
                return
            if self.drag.mode == "EXTRUDE":
                geometry = self.drag.geometry
                amount, index, config = self.drag.amount, geometry.face_index, geometry.config
                name = obj.name
                geometry.restore(obj)
                self.drag = None
                self.face_outline = ()
                self.mode, self.phase, _needs_release = "MOVE", "IDLE", False
                self.completed_mode()
                if amount > config.negligible_distance:
                    with bpy.context.temp_override(**self.context()):
                        result = bpy.ops.air_modeler.commit_extrusion(
                            "EXEC_DEFAULT", True, target_name=name, face_index=index,
                            distance=amount, maximum_distance=config.maximum_distance,
                            negligible_distance=config.negligible_distance)
                    if result != {"FINISHED"}:
                        self.cancel_drag()
                        raise RuntimeError("Extrusion commit failed; baseline restored")
                _last_error, _message = None, "EXTRUDE committed" if amount > config.negligible_distance else "Zero extrusion restored; MOVE ready"
                return
            baseline = self.drag.baseline.copy()
            final = obj.matrix_world.copy()
            operation = self.drag.mode
            tolerance = self.drag.config.matrix_tolerance
            scale_signs = self.drag.scale_signs
            transforms.apply_matrix(obj, baseline, scale_signs)
            name = obj.name
            changed = transforms.changed(baseline, final, tolerance)
            self.drag = None
            self.phase, _needs_release = "IDLE", False
            self.completed_mode()
            if changed:
                with bpy.context.temp_override(**self.context()):
                    result = bpy.ops.air_modeler.commit_transform("EXEC_DEFAULT", True, target_name=name, matrix=transforms.flatten(final), scale_signs=scale_signs)
                if result != {"FINISHED"}:
                    self.cancel_drag()
                    self.error("Transform commit failed; baseline restored")
                    return
            _last_error, _message = None, f"{operation} committed" if changed else f"{operation} unchanged"

    def selection_config(self):
        from dataclasses import replace
        values = self.wm.air_modeler_precision
        return replace(intent.CONFIG, move_threshold=values.move_threshold,
                       twist_threshold=math.radians(values.twist_threshold),
                       openness_threshold=values.openness_threshold,
                       persistence=values.intent_persistence,
                       dominance=values.intent_dominance, hysteresis=values.intent_hysteresis, scale_sensitivity=values.scale_sensitivity,
                       rotation_sensitivity=values.rotation_sensitivity, extrusion_sensitivity=values.extrusion_sensitivity)

    def select_hand(self, owner, observation, right, now):
        """Only Left's corrected START selects. Its later coordinates are inert."""
        global _message, _last_error
        if owner != 'Left':
            raise RuntimeError('Only the Left selection clutch can acquire a target')
        context = self.context()
        with bpy.context.temp_override(**context):
            if bpy.context.mode != 'OBJECT':
                raise RuntimeError('Selection requires Object Mode')
        uv = observation['u'], observation['v']
        view = viewport.mapping(context)
        hit, rejected = viewport.pick(context, view, uv)
        self.cursor, self.tracking = uv, True
        if hit is None:
            self.release_hands = {'Left'}
            self.cancel_drag(preserve_mode=True)
            raise RuntimeError('Unsupported target' if rejected else 'Pinch missed; release Left before retrying')
        obj, point = hit
        # Selection is object-only; visible supported faces are discovered on EXTRUDE.
        normal = view[1].view_matrix.inverted().col[2].xyz.normalized()
        for selected in context['view_layer'].objects:
            if selected.select_get():
                selected.select_set(False)
        obj.select_set(True)
        context['view_layer'].objects.active = obj
        cfg = self.selection_config()
        self.drag = SimpleNamespace(identifier=observation['gesture_id'], owner='Left',
            target_id=obj.session_uid, baseline=obj.matrix_world.copy(), scale_signs=tuple(obj.scale),
            source_mesh=obj.data, source_stamp=visibility.mesh_stamp(obj.data), view=view, mode=None, axis=self.axis if self.override else "FREE", start=uv, fixed_distance=self.fixed_distance,
            geometry=None, config=transforms.CONFIG, amount=0., point=point, normal=normal, grab=None,
            max_delta=max(100, (point-viewport.ray(view,uv)[0]).length*10),
            face_index=None, face_error=None,
            intent=intent.Intent(cfg), intent_config=cfg, required={'Left','Right'}, lost_since=None,
            valid_preview=True, aspect=self.capture_aspect, plane=None, right_id=None, last_right=None,
            plane_name=self.plane, plane_axis=self.plane_axis, override=self.mode if self.override else None)
        self.face_outline = ()
        self.target_message = f'{obj.name}; selected object; Right chooses operation'
        self.hovered = obj.name
        self.phase = 'SELECTED_READY'
        self.drag.intent.update(now,right,override=self.drag.override)
        self.source = 'Left clutch / Right whole hand'
        _last_error = None
        _message = intent.PROMPT

    def lock_operation(self, mode, right):
        global _message, _last_error
        drag, obj = self.drag, self.target()
        drag.mode = self.mode = mode
        if mode == 'MOVE':
            drag.start = right['palm_u'],right['palm_v']
            drag.grab = viewport.plane_point(drag.view,drag.start,drag.point,drag.normal)
            if drag.grab is None:
                raise RuntimeError('Cannot map Right palm in this view')
        elif mode in ('ROTATE','SCALE'):
            transforms.validate_rigid_scale(obj)
            from mathutils import Quaternion
            drag.orientation_reference = right['orientation']
            drag.rotation_offset = Quaternion()
            drag.rotation_delta = Quaternion()
            drag.view_rotation = drag.view[1].view_matrix.inverted().to_quaternion()
            drag.reference_openness = right['openness']
            drag.amount = 1. if mode == 'SCALE' else 0.
        else:
            drag.right_id = drag.intent.pinch_id
            drag.pinch_start = drag.intent.pinch_start
            if drag.right_id is None:
                raise RuntimeError('Extrusion requires a fresh isolated Right pinch')
            self.validate_extrusion_baseline()
            drag.face_candidates,drag.visibility_records = visibility.visible_faces(obj,self.context(),drag.view)
            if not drag.face_candidates:
                raise ValueError('No supported visible face; expose a face and reselect')
            drag.occluders = visibility.scene_stamp(self.context(),obj)
            drag.visibility_checked = time.monotonic()
            drag.expected_stamp = drag.source_stamp
            space=self.context()['area'].spaces.active
            drag.shading=(space.shading.type,space.shading.show_xray)
            view_rotation = drag.view[1].view_matrix.inverted()
            drag.plane = planes.automatic(view_rotation.col[0].xyz,view_rotation.col[1].xyz,
                drag.plane_name,drag.plane_axis,drag.intent_config.extrusion_sensitivity)
            drag.pinch_reference = drag.pinch_start
            drag.pinch_delta = (0.,0.)
            drag.direction_candidate = None
            drag.direction_since = None
            self.target_message = f'{obj.name}; direction pending; {drag.plane.plane}/{drag.plane.axis} virtual mapping; right {drag.plane.horizontal}; up {drag.plane.vertical}'
        drag.last_right = dict(right)
        self.phase = 'DRAGGING'
        _last_error = None
        _message = f'{mode} locked; release Left'+(' or Right pinch' if mode == 'EXTRUDE' else '')+' to commit'

    def preview_hands(self, right, recovered=False):
        """All geometry input comes from Right; every result uses original baseline."""
        global _message, _last_error
        drag = self.drag
        if drag.mode == 'MOVE':
            uv = right['palm_u'],right['palm_v']
            if recovered:
                point = viewport.plane_point(drag.view,uv,drag.point,drag.normal)
                if point is None:
                    raise RuntimeError('Cannot reanchor recovered Right palm')
                drag.grab = point-(self.target().matrix_world.translation-drag.baseline.translation)
            self.preview(uv)
            drag.last_right = dict(right)
            return
        if recovered:
            if drag.mode == 'ROTATE':
                drag.orientation_reference = right['orientation']
                drag.rotation_offset = drag.rotation_delta.copy()
            elif drag.mode == 'SCALE':
                drag.reference_openness = right['openness']-math.log(drag.amount)/drag.intent_config.scale_sensitivity
            else:
                drag.pinch_reference = right['u']-drag.pinch_delta[0],right['v']-drag.pinch_delta[1]
                if drag.face_index is None:
                    drag.direction_candidate=None
        obj = self.target()
        if drag.mode == 'ROTATE':
            drag.rotation_delta = transforms.hand_rotation(right['orientation'],drag.orientation_reference,
                drag.view_rotation,drag.axis,drag.intent_config.rotation_sensitivity,
                drag.intent_config.rotation_deadband) @ drag.rotation_offset
            drag.amount = drag.rotation_delta.angle
            final = drag.rotation_delta.to_matrix().to_4x4()@drag.baseline
            final.translation = drag.baseline.translation
            transforms.apply_matrix(obj,final,drag.scale_signs)
        elif drag.mode == 'SCALE':
            from mathutils import Matrix
            factor = math.exp(drag.intent_config.scale_sensitivity*(right['openness']-drag.reference_openness))
            drag.amount = max(drag.config.scale_min,min(drag.config.scale_max,factor))
            final = Matrix.Scale(drag.amount,4)@drag.baseline
            final.translation = drag.baseline.translation
            transforms.apply_matrix(obj,final,drag.scale_signs)
        elif drag.mode == 'EXTRUDE':
            self.validate_extrusion_baseline()
            from mathutils import Vector
            delta = right['u']-drag.pinch_reference[0],right['v']-drag.pinch_reference[1]
            vector = drag.plane.displacement(delta[0]*drag.aspect,delta[1])
            if drag.face_index is None:
                # Small direction threshold is independent of extrusion gain.
                if math.hypot(delta[0]*drag.aspect,delta[1]) < .018:
                    drag.direction_candidate=None;self.face_outline=()
                    self.target_message = 'Pinch held: drag a little to choose extrusion direction'
                    return
                choice,scores,reason=visibility.choose(drag.face_candidates,vector,drag.plane,drag.direction_candidate)
                drag.face_scores=scores
                if choice is None:
                    drag.direction_candidate=None
                    if self.frame_time-getattr(drag,'highlight_at',-1)>.15:self.face_outline=()
                    self.target_message=reason+'; candidate only, no deformation'
                    return
                index,normal,center,outline=choice
                self.target_message=f'Candidate face {index}; hold direction to lock; no deformation'
                if drag.direction_candidate!=index:
                    if self.frame_time-getattr(drag,'highlight_at',-1)>.15:self.face_outline=()
                    drag.direction_candidate=index;drag.direction_since=self.frame_time
                    return
                if self.frame_time-drag.direction_since>=.06:
                    self.face_outline=outline;drag.highlight_at=self.frame_time
                if self.frame_time-drag.direction_since<.10:return
                drag.face_index=index;drag.locked_normal=normal
                drag.face_locked_at=self.frame_time
                drag.pinch_reference=right['u'],right['v']
                drag.pinch_delta=(0.,0.)
                self.face_outline=outline
                self.target_message=(f'Face {index}; normal ({normal.x:+.2f},{normal.y:+.2f},{normal.z:+.2f}); '
                    f'{drag.plane.plane}/{drag.plane.axis}; right {drag.plane.horizontal}; up {drag.plane.vertical}; arrow points OUT')
                return
            if self.frame_time-drag.face_locked_at<.12:return
            # Direction-selection travel was consumed at lock. Signed motion now
            # stays on this face and rebuilds only when crossing representations.
            amount=drag.fixed_distance if drag.fixed_distance is not None else Vector(vector).dot(drag.locked_normal)
            if drag.geometry is None and abs(amount)>extrusion.CONFIG.negligible_distance:
                drag.geometry=signed_extrusion.SignedPreview(obj,drag.face_index,extrusion.CONFIG)
            if drag.geometry:
                drag.geometry.update(amount)
                amount=drag.geometry.amount
            drag.expected_stamp=visibility.mesh_stamp(obj.data)
            drag.pinch_delta=delta
            drag.amount=amount
            limit=drag.geometry.limit_reason if drag.geometry else ''
            if not limit and Vector(vector).length>=drag.plane.maximum-1e-6:
                limit=f'Mapping travel limit {drag.plane.maximum:g} reached'
            self.target_message=(f'Face {drag.face_index}; OUT arrow; {drag.plane.plane}/{drag.plane.axis}; '
                f'distance {amount:+.3f}; gain {drag.plane.sensitivity:g}; '
                f'OUT {tuple(round(x,2) for x in drag.locked_normal)}; '
                f'right {drag.plane.horizontal}; up {drag.plane.vertical}; '+limit)
        drag.valid_preview = True
        drag.last_right = dict(right)
        self.face_outline = drag.geometry.outline() if drag.geometry else self.face_outline
        _last_error = None
        _message = f'{drag.mode} locked; Left is selection only'

    def finish_hand(self, hands):
        """First coherent valid completion restores then commits once via native Undo."""
        global _message, _last_error, _needs_release, _release_hands
        drag, obj = self.drag,self.target()
        operation = drag.mode
        if not drag.valid_preview:
            self.cancel_drag()
            raise RuntimeError('Invalid displacement on release; baseline restored')
        name, arguments, changed = obj.name,None,False
        if operation == 'EXTRUDE':
            self.validate_extrusion_baseline(force=True)
        if operation == 'EXTRUDE' and drag.geometry is not None:
            geometry = drag.geometry
            changed = abs(geometry.outward_distance) > geometry.config.negligible_distance
            if changed:
                geometry.validate_result()
                arguments = dict(target_name=name,face_index=geometry.face_index,
                    distance=geometry.amount,use_signed=True,
                    maximum_distance=geometry.config.maximum_distance,
                    negligible_distance=geometry.config.negligible_distance)
            geometry.restore(obj)
        elif operation and operation != 'EXTRUDE':
            final = obj.matrix_world.copy()
            changed = transforms.changed(drag.baseline,final,drag.config.matrix_tolerance)
            transforms.apply_matrix(obj,drag.baseline,drag.scale_signs)
            arguments = dict(target_name=name,matrix=transforms.flatten(final),scale_signs=drag.scale_signs)
        required = {'Left','Right'} if operation == 'EXTRUDE' else {'Left'}
        self.release_hands = {hand for hand in required if not (hands[hand]['valid'] and hands[hand]['open'])}
        _release_hands = set(self.release_hands)
        _needs_release = bool(self.release_hands)
        self.drag = None
        self.face_outline = ()
        self.phase = 'NEEDS_RELEASE' if _needs_release else 'IDLE'
        self.completed_mode()
        if changed:
            with bpy.context.temp_override(**self.context()):
                op = bpy.ops.air_modeler.commit_extrusion if operation == 'EXTRUDE' else bpy.ops.air_modeler.commit_transform
                if op('EXEC_DEFAULT',True,**arguments) != {'FINISHED'}:
                    raise RuntimeError('Commit failed; baseline restored')
        _last_error = None
        _message = (f'{operation} committed once' if changed else 'Unchanged release creates no edit') + ('; release '+', '.join(sorted(self.release_hands)) if self.release_hands else '')

    def hands_frame(self, payload):
        global _message, _needs_release, _release_hands
        now = time.monotonic()
        if payload['frame_id'] <= self.frame_id or payload['t'] <= self.frame_time:
            raise ValueError('Stale hand observation frame/time')
        if self.frame_origin is None:
            self.frame_origin = now-payload['t']
        if now-(self.frame_origin+payload['t']) > .5:
            if self.drag:
                self.cancel_drag()
            raise ValueError('Hand observation delivery is stale; release and reconnect')
        self.frame_id,self.frame_time = payload['frame_id'],payload['t']
        if not self.clutch and self.drag is not None:
            self.cancel_drag()
        self.clutch = True
        self.selector.enabled = False
        if not self.override:
            self.source = 'Left clutch / Right whole hand'
        self.last_input = now
        hands = payload['hands']
        self.capture_aspect = payload['aspect']
        left,right = hands['Left'],hands['Right']
        def recognition(obs):
            if not obs['valid']: return 'absent/uncertain'
            if not obs['shape_valid']: return obs['shape_error']
            pose = 'extrusion pinch' if obs['pinch_pending'] else 'open palm' if obs['open_palm'] else 'fist' if obs['openness'] < .25 else 'partly closed'
            return f"{pose}; openness {obs['openness']:.2f}"
        self.hand_status = 'Left clutch: '+('held' if left['valid'] and left['pinching'] else 'released' if left['valid'] and left['open'] else 'uncertain')+' | Right: '+recognition(right)
        starts = set()
        for hand in ('Left','Right'):
            obs = hands[hand]
            if obs['event'] == 'START' and obs['gesture_id'] not in self.seen_gestures:
                if len(self.seen_gestures) >= 4096:
                    raise protocol.SessionFull('Gesture history full; reconnect')
                self.seen_gestures.add(obs['gesture_id'])
                starts.add(hand)
        if right['event'] == 'START' and 'Right' not in starts:
            right = dict(right,event='NONE')
        if self.phase == 'NEEDS_RELEASE':
            had_required = bool(self.release_hands)
            self.release_hands.difference_update(hand for hand in tuple(self.release_hands)
                if hands[hand]['valid'] and hands[hand]['open'])
            _release_hands = set(self.release_hands)
            if not self.release_hands and (had_required or left['valid'] and left['open']):
                self.phase,_needs_release = 'IDLE',False
            _message = 'Release '+', '.join(sorted(self.release_hands)) if self.release_hands else 'Ready for a fresh Left pinch'
            return  # Consume starts in a rearming frame, never queue them.
        if self.drag is None:
            self.tracking = left['valid']
            if left['valid']:
                self.last_present = now
                self.observe((left['u'],left['v']))
            else:
                self.hovered = None
            if 'Left' in starts:
                self.select_hand('Left',left,right,payload['t'])
            elif not left['valid']:
                _message = 'Left clutch required; Right alone cannot select'
            return
        drag = self.drag
        owner_valid = left['valid'] and left['gesture_id'] == drag.identifier
        left_end = owner_valid and left['event'] == 'END' and left['open']
        right_match = right['valid'] and right['gesture_id'] == drag.right_id
        right_end = drag.mode == 'EXTRUDE' and right_match and right['event'] == 'END' and right['open']
        if left['event'] == 'CANCEL' and left['gesture_id'] == drag.identifier:
            self.cancel_drag()
            _message = 'Left clutch cancelled; release both hands to rearm'
            return
        valid = owner_valid and (left['pinching'] or left_end) and right['valid'] and right['shape_valid']
        if drag.mode == 'MOVE':
            valid = valid and right['open_palm'] and not right['pinch_pending']
        elif drag.mode == 'EXTRUDE':
            valid = valid and right_match and (right['pinching'] or right_end) and right['extrude_pose']
        # SCALE deliberately has no pinch/open-palm requirement: a fist is valid.
        completing = left_end or right_end
        self.tracking = bool(valid)
        if not valid:
            if drag.lost_since is None:
                drag.lost_since = now
            if completing or now-drag.lost_since >= drag.intent_config.loss_timeout:
                self.cancel_drag()
                self.error('Required hand/pose invalid at release or lost; baseline restored')
            else:
                _message = right.get('shape_error') or 'Required hand/pose uncertain: preview frozen'
            return
        if completing and drag.lost_since is not None:
            self.cancel_drag()
            self.error('Release raced required-hand loss; baseline restored')
            return
        self.last_present = now
        recovered = drag.lost_since is not None
        if recovered and now-drag.lost_since >= drag.intent_config.loss_timeout:
            self.cancel_drag()
            self.error('Required hand absent too long; baseline restored')
            return
        drag.lost_since = None
        if self.phase == 'SELECTED_READY':
            if left_end:
                self.finish_hand(hands)
                return
            if recovered:
                drag.intent = intent.Intent(drag.intent_config)
            mode = drag.intent.update(payload['t'],right,override=drag.override)
            if mode is not None:
                self.lock_operation(mode,right)
            else:
                _message = drag.intent.feedback
            return
        self.preview_hands(right,recovered)
        if completing:
            self.finish_hand(hands)

    def diagnostics(self, payload):
        if not bpy.context.window_manager.air_modeler_precision.diagnostics:return
        now=time.monotonic()
        if now-getattr(self,'diagnostic_at',0)<.5:return
        self.diagnostic_at=now
        d=self.drag;r=payload['hands']['Right'];l=payload['hands']['Left']
        import json
        print('AIR_DIAG '+json.dumps(dict(version='0.10.0',phase=self.phase,
            age=round(now-(self.frame_origin+payload['t']),3),
            identities={h:(v['valid'],v['confidence']) for h,v in payload['hands'].items()},
            clutch=l['pinching'],fingers=r['fingers'],openness=r['openness'],
            isolated_pinch=r['pinch_pending'],orientation_valid=r['shape_valid'],
            orientation=r['orientation'],angle=d.intent.twist if d else None,
            scores=d.intent.scores if d else {},candidate=d.intent.candidate if d else None,
            candidate_age=payload['t']-d.intent.since if d and d.intent.since is not None else None,
            reason=_last_error or _message,target_feedback=self.target_message,amount=d.amount if d else None,
            mapping=d.plane.plane if d and d.plane else None,
            faces=getattr(d,'face_scores',None),visibility=getattr(d,'visibility_records',None),
            limit=d.geometry.limit_reason if d and d.geometry and hasattr(d.geometry,'limit_reason') else None,
            face=d.face_index if d else None),allow_nan=False),flush=True)

    def handle(self, event):
        global _message, _last_error
        kind, payload = event["type"], event["payload"]
        self.next_status = 0
        try:
            if kind == 'hands_frame':
                self.hands_frame(payload)
                self.diagnostics(payload)
                return
            if self.clutch and kind != 'command':
                return  # Never mix legacy and coherent cursors in one connection.
            if kind == 'selector_frame':
                self.selector.observe(payload['pose'], time.monotonic(), self.drag is None and self.phase == 'IDLE')
                self.automatic_mode()
                return
            if kind != "command":
                self.gesture(kind, payload)
                return
            action = payload["action"]
            if self.drag and action in {"spawn", "set_mode", "precision"}:
                raise RuntimeError("Release or cancel the active drag first")
            context = self.context()
            # Native Undo replaces Scene/ViewLayer RNA. Keeping explicit data
            # overrides across it can leave Blender evaluating the freed scene
            # during the operator's post-update. Resolve data through its stable
            # Window instead; still validate the captured scene/view beforehand.
            with bpy.context.temp_override(**{key: context[key] for key in ('window','area','region')}):
                if action == "spawn":
                    result = bpy.ops.air_modeler.create_primitive("EXEC_DEFAULT", True, shape=payload["shape"])
                    if result != {"FINISHED"}:
                        raise RuntimeError("Spawn operator did not finish")
                    _message = f"Created {payload['shape']}"
                elif action == 'precision':
                    if bpy.context.mode != 'OBJECT':
                        raise RuntimeError('Precision edits require Object Mode')
                    if self.phase != 'IDLE':
                        raise RuntimeError('Open/release the hand before a precision edit')
                    protocol.validate_precision(payload)
                    if payload['mode'] == 'EXTRUDE':
                        self.set_mode('EXTRUDE', distance=payload['value'],plane=self.plane,plane_axis=self.plane_axis)
                        _message = ('Fixed extrusion armed: select object, pinch and drag to choose face'
                                    if self.clutch else 'Fixed extrusion armed: select an eligible face')
                    else:
                        transforms.commit_precision(bpy.context, payload)
                        self.completed_mode()
                        _message = 'Precision edit completed'
                elif action == "cancel":
                    self.cancel_drag(require_release=self.drag is not None or self.phase == 'NEEDS_RELEASE')
                    _message = "Cancelled; release hand to rearm" if self.phase == 'NEEDS_RELEASE' else "Cancelled; ready"
                elif action == "undo":
                    if self.drag:
                        self.cancel_drag()
                    if not bpy.ops.ed.undo.poll():
                        raise RuntimeError("Nothing available to undo")
                    bpy.ops.ed.undo()
                    self.hovered = None
                    _message = "Undo completed"
                else:
                    self.set_mode(payload["mode"], payload.get("axis", "FREE" if payload["mode"]=="ROTATE" else "Z"),
                                  plane=payload.get('plane','AUTO'),
                                  plane_axis=payload.get('axis','NONE') if payload['mode']=='EXTRUDE' else 'NONE')
                    _message = f"{self.mode_label()} armed"
            _last_error = None
        except protocol.SessionFull:
            raise
        except (RuntimeError, ReferenceError, TypeError, ValueError) as exc:
            if self.drag and kind != "command":
                self.cancel_drag()
            self.error(exc)

    def validate_extrusion_baseline(self, force=False):
        """Cancel on stale captured view/geometry; never reuse a changed face index."""
        drag,obj=self.drag,self.target()
        extrusion.validate_object(obj)
        if obj.data!=drag.source_mesh and (drag.source_mesh.users or drag.source_mesh.use_fake_user):
            raise RuntimeError('Extrusion baseline gained another owner; release and reselect')
        if not visibility.view_unchanged(self.context(),drag.view):
            raise RuntimeError('Viewport changed; release and reselect to capture the new view')
        if any(abs(a-b)>1e-6 for x,y in zip(obj.matrix_world,drag.baseline) for a,b in zip(x,y)):
            raise RuntimeError('Object transform changed externally; extrusion cancelled')
        space=self.context()['area'].spaces.active
        if hasattr(drag,'shading') and (space.shading.type,space.shading.show_xray)!=drag.shading:
            raise RuntimeError('Viewport shading changed; release and reselect')
        expected=getattr(drag,'expected_stamp',drag.source_stamp)
        if visibility.mesh_stamp(obj.data)!=expected or visibility.mesh_stamp(drag.source_mesh)!=drag.source_stamp:
            raise RuntimeError('Mesh changed externally; extrusion cancelled')
        now=time.monotonic()
        if hasattr(drag,'occluders') and (force or now-drag.visibility_checked>=.25):
            if visibility.scene_stamp(self.context(),obj)!=drag.occluders:
                raise RuntimeError('Visible scene changed; release and reselect')
            drag.visibility_checked=now

    def check_tracking(self, now):
        if now - self.last_input >= .5:
            self.tracking, self.hovered = False, None
        if self.drag:
            context = self.context()
            with bpy.context.temp_override(**context):
                if bpy.context.mode != "OBJECT":
                    raise RuntimeError("Left Object Mode; drag cancelled")
            obj = self.target()
            if obj is None or not viewport.eligible(obj, context) or (self.drag.geometry is not None and obj.data != self.drag.geometry.mesh) or (self.drag.geometry is None and hasattr(self.drag, 'source_mesh') and obj.data != self.drag.source_mesh):
                self.cancel_drag()
                self.error("Drag target disappeared or became unsupported")
            elif self.clutch and getattr(self.drag,'mode',None)=='EXTRUDE':
                try:self.validate_extrusion_baseline()
                except (ValueError,RuntimeError) as exc:
                    self.cancel_drag();self.error(str(exc))
            if self.drag and ((getattr(self.drag, 'lost_since', None) is not None and
                   now - self.drag.lost_since >= self.drag.intent_config.loss_timeout)
                  or now - self.last_present >= .5):
                self.cancel_drag()
                self.error("Tracking lost or stale for 0.5 seconds; release to rearm")

    def status(self):
        context = self.context()
        active = context["view_layer"].objects.active
        selected = active.name if active is not None and active.select_get(view_layer=context["view_layer"]) else None
        return {"type": "status", "payload": {
            "mode": self.mode, "phase": self.phase, "selected_object": selected,
            "hovered_object": self.hovered,
            "tracking": self.tracking and time.monotonic() - self.last_input < 0.5,
            "last_error": _last_error,
        }}

    def tick(self):
        global _state, _message
        self.context()  # Stop cleanly if the captured UI/scene context went away.
        now = time.monotonic()
        self.check_tracking(now)
        self.automatic_mode()
        if self.session.session_id is None and now > self.deadline:
            raise ConnectionError("Connection/hello timed out; start the companion and reconnect")
        if self.connecting:
            _, writable, exceptional = select.select([], [self.sock], [self.sock], 0)
            if not writable and not exceptional:
                return
            result = self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if result:
                raise OSError(result, "Companion unavailable at 127.0.0.1:8765")
            self.connecting = False
            _state = "Handshaking"
            self.channel.queue(self.session.wrap({"type": "hello", "payload": {}}))
        self.channel.flush(self.sock)
        for message in self.channel.read(self.sock, limit=4):
            try:
                if isinstance(message, protocol.ProtocolError):
                    raise message
                previous = self.session.session_id
                event, _ = self.session.accept(message)
                if previous is None and self.session.session_id is not None:
                    _state, _message = "Connected", "MOVE ready; open hand before pinching"
                if event is not None:
                    self.handle(event)
            except protocol.SessionFull:
                raise
            except protocol.ProtocolError as exc:
                self.error(exc)
        if self.session.session_id is not None and now >= self.next_status:
            self.channel.queue(self.session.wrap(self.status()))
            self.next_status = now + 0.25
        self.channel.flush(self.sock)
        redraw()


class AIRMODELER_OT_connect(bpy.types.Operator):
    bl_idname = "air_modeler.connect"
    bl_label = "Connect"
    bl_description = "Connect to the local companion from this viewport"
    # Intentionally no UNDO flag: each received spawn is its own undoable operator.

    @classmethod
    def poll(cls, context):
        return _runtime is None and context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        global _runtime, _state, _message, _last_error
        self.runtime = None
        try:
            self.runtime = Client(context)
            self.runtime.timer = context.window_manager.event_timer_add(1 / 30, window=context.window)
            if not context.window_manager.modal_handler_add(self):
                raise RuntimeError("Could not start modal bridge controller")
            _runtime = self.runtime
            _state, _message, _last_error = "Connecting", "Connecting to 127.0.0.1:8765", None
            redraw()
            return {"RUNNING_MODAL"}
        except (OSError, RuntimeError) as exc:
            if self.runtime is not None:
                self.runtime.close()
            disconnect("Connection failed", str(exc))
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if _runtime is not self.runtime:
            self.runtime = None
            return {"CANCELLED"}
        # Event exposes no timer identity in Blender 5.2. Other timers may also
        # deliver TIMER events, so throttle work independently to at most 30 Hz.
        if event.type == "TIMER" and time.monotonic() >= self.runtime.next_poll:
            self.runtime.next_poll = time.monotonic() + 1 / 30
            try:
                self.runtime.tick()
            except (OSError, RuntimeError, ReferenceError, BufferError, protocol.SessionFull) as exc:
                disconnect("Connection stopped; reconnect explicitly", str(exc))
                return {"CANCELLED"}
        if self.runtime.drag and event.type != "TIMER":
            if event.type == "ESC" and event.value == "PRESS":
                self.runtime.cancel_drag()
                return {"RUNNING_MODAL"}
            if event.type == "Z" and event.value == "PRESS" and (event.ctrl or event.oskey):
                self.runtime.handle({"type": "command", "payload": {"action": "undo"}})
                return {"RUNNING_MODAL"}
            # A generic sidebar can also contain Blender's native transform
            # fields. Restore before allowing any click/scroll there, so no
            # competing edit or Undo snapshot can capture a live preview.
            # Cancel/Undo/Disconnect buttons remain usable after restoration.
            in_sidebar = any(region.type == 'UI' and region.x <= event.mouse_x < region.x + region.width
                             and region.y <= event.mouse_y < region.y + region.height
                             for region in (context.area.regions if context.area is not None else ()))
            if in_sidebar and event.type in {'LEFTMOUSE','RIGHTMOUSE','MIDDLEMOUSE',
                                             'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','TRACKPADZOOM'}:
                self.runtime.cancel_drag()
                return {'PASS_THROUGH'}
            if in_sidebar and event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE'}:
                return {'PASS_THROUGH'}
            # Block viewport navigation and competing editing shortcuts while
            # the fixed mapping owns a preview. Network cancel/undo still work.
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        if _runtime is not None and _runtime is self.runtime:
            disconnect("Controller cancelled")


class AIRMODELER_OT_disconnect(bpy.types.Operator):
    bl_idname = "air_modeler.disconnect"
    bl_label = "Disconnect"

    @classmethod
    def poll(cls, context):
        return _runtime is not None

    def execute(self, context):
        disconnect()
        return {"FINISHED"}
