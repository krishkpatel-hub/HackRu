"""One main-thread controller owns transport, gesture preview and passive drawing."""

import errno
import select
import socket
import time
from types import SimpleNamespace

from . import viewport, transforms, extrusion, intent, planes
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
        label = f"ROTATE world {self.axis}" if self.mode == "ROTATE" else self.mode
        if self.drag and self.drag.mode == "ROTATE":
            label += f" {math.degrees(self.drag.amount):+.1f}°"
        elif self.drag and self.drag.mode == "SCALE":
            label += f" {self.drag.amount:.3f}x"
        elif self.drag and self.drag.mode == "EXTRUDE":
            label += f" {self.drag.amount:.3f} units"
        if self.fixed_distance is not None and self.drag is None:
            label += f" fixed {self.fixed_distance:.3f} units"
        if self.clutch and self.drag and self.drag.mode == 'EXTRUDE':
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
        self.source = 'single-hand/manual'
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
                                        mode=self.mode, axis=self.axis, start=uv, fixed_distance=self.fixed_distance,
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
                       aperture_threshold=values.aperture_threshold,
                       persistence=values.intent_persistence)

    def select_hand(self, owner, observation, right, now):
        """Acquire once at the corrected START cursor, without preview mutation."""
        global _message, _last_error
        context = self.context()
        with bpy.context.temp_override(**context):
            if bpy.context.mode != 'OBJECT':
                raise RuntimeError('Selection requires Object Mode')
        uv = observation['u'], observation['v']
        view = viewport.mapping(context)
        hit, rejected = viewport.pick(context, view, uv)
        self.cursor, self.tracking = uv, True
        if hit is None:
            self.release_hands = {owner}
            self.cancel_drag(preserve_mode=True)
            raise RuntimeError('Unsupported target' if rejected else 'Pinch missed; open the selecting hand before retrying')
        obj, point = hit
        face_hit, face_error = viewport.pick_extrusion(context, view, uv)
        if face_hit and face_hit[0] != obj:
            face_hit = None
        normal = view[1].view_matrix.inverted().col[2].xyz.normalized()
        grab = viewport.plane_point(view, uv, point, normal)
        if grab is None:
            raise RuntimeError('Cannot map this viewport selection')
        for selected in context['view_layer'].objects:
            if selected.select_get():
                selected.select_set(False)
        obj.select_set(True)
        context['view_layer'].objects.active = obj
        cfg = self.selection_config()
        self.drag = SimpleNamespace(identifier=observation['gesture_id'], owner=owner,
            target_id=obj.session_uid, baseline=obj.matrix_world.copy(), scale_signs=tuple(obj.scale),
            source_mesh=obj.data, view=view, mode=None, axis=self.axis, start=uv, fixed_distance=self.fixed_distance,
            geometry=None, config=transforms.CONFIG, amount=0.0, point=point, normal=normal, grab=grab,
            max_delta=max(100, (point - viewport.ray(view, uv)[0]).length * 10),
            face_index=face_hit[2] if face_hit else None, face_error=face_error,
            intent=intent.Intent(uv, cfg), intent_config=cfg, required={owner}, lost_since=None,
            recovered=False, valid_preview=True, plane=None, last_right=None,
            plane_name=self.plane, plane_axis=self.plane_axis, override=self.mode if self.override else None)
        self.face_outline = face_hit[3] if face_hit else ()
        self.target_message = f'Locked face {face_hit[2]}' if face_hit else (face_error or 'No eligible extrusion face')
        self.hovered = obj.name
        self.phase = 'SELECTED_READY'
        self.drag.intent.update(now, uv, right, left_owner=owner == 'Left', override=self.drag.override)
        self.source = f'{owner} selection clutch'
        _last_error = None
        _message = 'Selected. Move owner, twist/spread right grip, or move right open palm.'

    def lock_operation(self, mode, owner, right):
        global _message, _last_error
        drag = self.drag
        obj = self.target()
        drag.mode = self.mode = mode
        drag.required = {drag.owner} if mode == 'MOVE' else {'Left', 'Right'}
        if mode == 'MOVE':
            drag.start = owner['u'], owner['v']
            drag.grab = viewport.plane_point(drag.view, drag.start, drag.point, drag.normal)
            if drag.grab is None:
                raise RuntimeError('Cannot map owner motion in this view')
        elif mode in ('ROTATE','SCALE'):
            drag.reference_angle = drag.last_angle = right['angle']
            drag.total_angle = 0.0
            drag.reference_aperture = right['aperture']
            drag.amount = 1.0 if mode == 'SCALE' else 0.0
        else:
            if drag.face_index is None:
                raise RuntimeError(drag.face_error or 'Selection did not capture an eligible extrusion face')
            drag.geometry = extrusion.Preview(obj, drag.face_index, extrusion.CONFIG)
            view_rotation = drag.view[1].view_matrix.inverted()
            drag.plane = planes.mapping(drag.geometry.world_normal,
                view_rotation.col[0].xyz, view_rotation.col[1].xyz,
                drag.plane_name, drag.plane_axis)
            def direction_label(vector):
                return next(('+' if x > 0 else '-') + 'XYZ'[i] for i,x in enumerate(vector) if x)
            self.target_message = f'Locked face {drag.face_index}; screen right {direction_label(drag.plane.horizontal)}, screen up {direction_label(drag.plane.vertical)}'
            drag.palm_reference = right['palm_u'], right['palm_v']
            drag.palm_delta = (0.0, 0.0)
            if drag.fixed_distance is not None:
                drag.geometry.update(drag.fixed_distance)
                drag.amount = drag.fixed_distance
            self.face_outline = drag.geometry.outline()
        drag.last_right = dict(right) if mode != 'MOVE' else None
        self.phase = 'DRAGGING'
        _last_error = None
        _message = f'{mode} locked; release {drag.owner} to commit, Escape to cancel'

    def preview_hands(self, owner, right, recovered=False):
        """Baseline-relative updates; right-operation clutch motion is ignored."""
        global _message, _last_error
        drag = self.drag
        if drag.mode == 'MOVE':
            if recovered:
                point = viewport.plane_point(drag.view, (owner['u'],owner['v']), drag.point, drag.normal)
                if point is None:
                    raise RuntimeError('Cannot reanchor recovered MOVE')
                drag.grab = point - (self.target().matrix_world.translation - drag.baseline.translation)
            self.preview((owner['u'], owner['v']))
            return
        if recovered:
            if drag.mode == 'ROTATE':
                drag.last_angle = right['angle']
            elif drag.mode == 'SCALE':
                drag.reference_aperture = right['aperture'] / drag.amount
            else:
                drag.palm_reference = (right['palm_u'] - drag.palm_delta[0],
                                       right['palm_v'] - drag.palm_delta[1])
        obj = self.target()
        if drag.mode == 'ROTATE':
            from mathutils import Matrix
            drag.total_angle += intent.angle_delta(right['angle'], drag.last_angle)
            drag.last_angle = right['angle']
            drag.amount = drag.total_angle * drag.intent_config.rotation_sensitivity
            final = Matrix.Rotation(drag.amount, 4, drag.axis) @ drag.baseline
            final.translation = drag.baseline.translation
            transforms.apply_matrix(obj, final, drag.scale_signs)
        elif drag.mode == 'SCALE':
            from mathutils import Matrix
            drag.amount = max(drag.config.scale_min, min(drag.config.scale_max,
                              right['aperture'] / drag.reference_aperture))
            final = Matrix.Scale(drag.amount, 4) @ drag.baseline
            final.translation = drag.baseline.translation
            transforms.apply_matrix(obj, final, drag.scale_signs)
        elif drag.fixed_distance is None:
            delta = right['palm_u'] - drag.palm_reference[0], right['palm_v'] - drag.palm_reference[1]
            vector = drag.plane.displacement(*delta)
            try:
                drag.geometry.update_vector(vector)
            except ValueError as exc:
                drag.valid_preview = False
                self.error(exc)
                return  # Last valid mesh remains visible; invalid release cancels.
            drag.palm_delta = delta
            drag.amount = drag.geometry.amount
        drag.valid_preview = True
        drag.last_right = dict(right)
        self.face_outline = drag.geometry.outline() if drag.geometry else self.face_outline
        _last_error = None
        _message = f'{drag.mode} locked; release {drag.owner} to commit'

    def finish_hand(self):
        """Restore once, then use the existing native Undo helpers once."""
        global _message, _last_error, _needs_release, _release_hands
        drag, obj = self.drag, self.target()
        operation = drag.mode
        if not drag.valid_preview:
            self.cancel_drag()
            raise RuntimeError('Invalid displacement on release; baseline restored')
        name = obj.name
        arguments = None
        changed = False
        if operation == 'EXTRUDE':
            geometry = drag.geometry
            changed = geometry.outward_distance > geometry.config.negligible_distance
            if changed:
                geometry.validate_result()
                arguments = dict(target_name=name, face_index=geometry.face_index,
                    vector=tuple(geometry.world_vector), use_vector=True,
                    maximum_distance=geometry.config.maximum_distance,
                    negligible_distance=geometry.config.negligible_distance)
            geometry.restore(obj)
        elif operation:
            final = obj.matrix_world.copy()
            changed = transforms.changed(drag.baseline, final, drag.config.matrix_tolerance)
            transforms.apply_matrix(obj, drag.baseline, drag.scale_signs)
            arguments = dict(target_name=name, matrix=transforms.flatten(final), scale_signs=drag.scale_signs)
        self.drag = None
        self.face_outline = ()
        # The matching END is already an observed stable release, so it
        # satisfies the success release gate in this same coherent frame.
        # Requiring a second sighting would prevent the other hand moving alone
        # when the completed owner immediately leaves the camera.
        self.phase = 'IDLE'
        self.release_hands.clear()
        _release_hands.clear()
        _needs_release = False
        self.completed_mode()
        if changed:
            with bpy.context.temp_override(**self.context()):
                op = bpy.ops.air_modeler.commit_extrusion if operation == 'EXTRUDE' else bpy.ops.air_modeler.commit_transform
                if op('EXEC_DEFAULT', True, **arguments) != {'FINISHED'}:
                    raise RuntimeError('Commit failed; baseline restored')
        _last_error = None
        _message = f'{operation} committed' if changed else 'Selected; unchanged release creates no edit'

    def hands_frame(self, payload):
        global _message, _needs_release, _release_hands
        now = time.monotonic()
        if payload['frame_id'] <= self.frame_id or payload['t'] <= self.frame_time:
            raise ValueError('Stale hand observation frame/time')
        if self.frame_origin is None:
            self.frame_origin = now - payload['t']
        if now - (self.frame_origin + payload['t']) > .5:
            if self.drag:
                self.cancel_drag()
            raise ValueError('Hand observation delivery is stale; release and reconnect')
        self.frame_id, self.frame_time = payload['frame_id'], payload['t']
        if not self.clutch and self.drag is not None:
            self.cancel_drag()  # A stream-format switch cannot transfer a legacy preview.
        self.clutch = True
        self.selector.enabled = False
        self.last_input = now
        hands = payload['hands']
        self.hand_status = ' | '.join(f"{hand}: " + ('uncertain/absent' if not obs['valid'] else 'grip' if obs['grip'] else 'open palm' if obs['open_palm'] else 'pinch' if obs['pinching'] else 'open' if obs['open'] else 'visible') for hand, obs in hands.items())
        # Consume every START even if another hand owns the selection; no queued takeover.
        starts = []
        for hand in ('Left', 'Right'):
            observation = hands[hand]
            if observation['event'] == 'START' and observation['gesture_id'] not in self.seen_gestures:
                if len(self.seen_gestures) >= 4096:
                    raise protocol.SessionFull('Gesture history full; reconnect')
                self.seen_gestures.add(observation['gesture_id'])
                starts.append(hand)
        if self.phase == 'NEEDS_RELEASE':
            had_required = bool(self.release_hands)
            self.release_hands.difference_update(hand for hand in tuple(self.release_hands)
                if hands[hand]['valid'] and hands[hand]['open'])
            _release_hands = set(self.release_hands)
            if not self.release_hands and (had_required or any(obs['valid'] and obs['open'] for obs in hands.values())):
                self.phase, _needs_release = 'IDLE', False
            # A START in the frame that rearms the controller is deliberately consumed.
            return
        if self.drag is None:
            available = next((hand for hand in ('Left','Right') if hands[hand]['valid']), None)
            self.tracking = available is not None
            if available:
                self.last_present = now
                obs = hands[available]
                self.observe((obs['u'], obs['v']))
            else:
                self.hovered = None
            if starts:
                owner = starts[0]  # Deterministic Left wins a coherent simultaneous frame.
                self.select_hand(owner, hands[owner], hands['Right'], payload['t'])
            return
        drag = self.drag
        owner, right = hands[drag.owner], hands['Right']
        # The owner ID cannot silently change, including on a final observation.
        owner_valid = owner['valid'] and owner['gesture_id'] == drag.identifier
        released = owner_valid and owner['event'] == 'END' and owner['open']
        if owner['event'] == 'CANCEL' and owner['gesture_id'] == drag.identifier:
            self.cancel_drag()
            _message = 'Selecting hand cancelled; open required hands to rearm'
            return
        required_valid = owner_valid and (owner['pinching'] or released)
        if drag.mode in ('ROTATE','SCALE'):
            required_valid = required_valid and right['valid'] and right['grip']
        elif drag.mode == 'EXTRUDE':
            required_valid = required_valid and right['valid'] and right['open_palm']
        self.tracking = bool(required_valid)
        if not required_valid:
            if drag.lost_since is None:
                drag.lost_since = now
            if released or now - drag.lost_since >= drag.intent_config.loss_timeout:
                self.cancel_drag()
                self.error('Required hand/pose lost; baseline restored, open hands to rearm')
            else:
                _message = 'Required hand/pose uncertain: preview frozen'
            return
        self.last_present = now
        self.cursor = owner['u'], owner['v']
        recovered = drag.lost_since is not None
        if recovered and now - drag.lost_since >= drag.intent_config.loss_timeout:
            self.cancel_drag()
            self.error('Required hand was absent too long; baseline restored')
            return
        drag.lost_since = None
        if self.phase == 'SELECTED_READY':
            if released:
                self.finish_hand()
                return
            if recovered:
                drag.intent = intent.Intent(self.cursor, drag.intent_config)
            mode = drag.intent.update(payload['t'], self.cursor, right,
                left_owner=drag.owner == 'Left', override=drag.override)
            if mode is not None:
                self.lock_operation(mode, owner, right)
            elif drag.owner == 'Left' and right['valid'] and right['grip']:
                _message = 'Twist to rotate or spread fingers to scale.'
            elif drag.owner == 'Right' and drag.override in ('ROTATE','SCALE','EXTRUDE'):
                _message = 'This override requires left selection and right manipulation; release and select with Left'
            return
        self.preview_hands(owner, right, recovered)
        if released:
            self.finish_hand()

    def handle(self, event):
        global _message, _last_error
        kind, payload = event["type"], event["payload"]
        self.next_status = 0
        try:
            if kind == 'hands_frame':
                self.hands_frame(payload)
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
            with bpy.context.temp_override(**self.context()):
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
                        self.set_mode('EXTRUDE', distance=payload['value'])
                        _message = 'Fixed extrusion armed: pinch an eligible face'
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
                    self.set_mode(payload["mode"], payload.get("axis", "Z"),
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
            elif ((getattr(self.drag, 'lost_since', None) is not None and
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
