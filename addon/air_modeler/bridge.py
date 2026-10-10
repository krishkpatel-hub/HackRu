"""One main-thread controller owns transport, gesture preview and passive drawing."""

import errno
import select
import socket
import time
from types import SimpleNamespace

from . import viewport, transforms, extrusion
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
        self.cancel_drag()
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
        return label + f" [{self.source}]"

    def set_mode(self, mode, axis="Z", *, source="voice override", distance=None):
        if self.drag:
            raise RuntimeError("Release or cancel the active drag first")
        if mode not in {"MOVE", "ROTATE", "SCALE", "EXTRUDE"}:
            raise RuntimeError(f"{mode} is not implemented in this milestone")
        if distance is not None:
            protocol.validate_precision(dict(id='internal', action='precision', mode=mode, value=distance))
        self.mode, self.axis = mode, axis
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
        self.source = 'single-hand/manual'
        self.automatic_mode()

    def cancel_drag(self, *, preserve_mode=False):
        global _needs_release
        obj = self.target()
        if self.drag and self.drag.geometry is not None:
            self.drag.geometry.restore(obj)
        if obj is not None:
            transforms.apply_matrix(obj, self.drag.baseline, self.drag.scale_signs)
        self.face_outline = ()
        self.drag = None
        self.phase = "NEEDS_RELEASE"
        if not preserve_mode:
            self.completed_mode()
        _needs_release = True
        self.next_status = 0

    def observe(self, uv):
        global _last_error
        self.cursor = uv
        self.tracking = True
        self.last_present = self.last_input = time.monotonic()
        if self.mode == "EXTRUDE":
            if self.drag:
                self.face_outline = self.drag.geometry.outline()
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

    def handle(self, event):
        global _message, _last_error
        kind, payload = event["type"], event["payload"]
        self.next_status = 0
        try:
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
                    self.cancel_drag()
                    _message = "Cancelled; release hand to rearm"
                elif action == "undo":
                    if self.drag:
                        self.cancel_drag()
                    if not bpy.ops.ed.undo.poll():
                        raise RuntimeError("Nothing available to undo")
                    bpy.ops.ed.undo()
                    self.hovered = None
                    _message = "Undo completed"
                else:
                    self.set_mode(payload["mode"], payload.get("axis", "Z"))
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
            if obj is None or not viewport.eligible(obj, context) or (self.drag.geometry is not None and obj.data != self.drag.geometry.mesh):
                self.cancel_drag()
                self.error("Drag target disappeared or became unsupported")
            elif now - self.last_present >= .5:
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
