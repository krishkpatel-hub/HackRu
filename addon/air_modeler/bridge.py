"""Main-thread, nonblocking modal TCP client. No scene data lives in this runtime."""

import errno
import select
import socket
import time

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
        try:
            result = self.sock.connect_ex(protocol.ADDRESS)
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, errno.EISCONN):
                raise OSError(result, "Could not connect to companion at 127.0.0.1:8765")
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

    def error(self, error):
        global _last_error, _message
        _last_error = str(error)[:1024]
        _message = "Input rejected"
        self.next_status = 0

    def handle(self, event):
        global _message, _last_error
        kind, payload = event["type"], event["payload"]
        if kind == "command":
            if payload["action"] != "spawn":
                self.error(f"{payload['action']} is not implemented in this milestone")
                return
            try:
                with bpy.context.temp_override(**self.context()):
                    result = bpy.ops.air_modeler.create_primitive("EXEC_DEFAULT", True, shape=payload["shape"])
                if result != {"FINISHED"}:
                    raise RuntimeError("Spawn operator did not finish")
                _message = f"Created {payload['shape']}"
                _last_error = None
                self.next_status = 0
            except (RuntimeError, ReferenceError, TypeError) as exc:
                self.error(exc)
        else:
            if kind == "hand_frame":
                self.tracking = payload["present"]
                self.last_input = time.monotonic()
            self.error("Hand interaction is not implemented in this milestone")

    def status(self):
        context = self.context()
        active = context["view_layer"].objects.active
        selected = active.name if active is not None and active.select_get(view_layer=context["view_layer"]) else None
        return {"type": "status", "payload": {
            "mode": "MOVE", "phase": "IDLE", "selected_object": selected,
            "hovered_object": None,
            "tracking": self.tracking and time.monotonic() - self.last_input < 0.5,
            "last_error": _last_error,
        }}

    def tick(self):
        global _state, _message
        self.context()  # Stop cleanly if the captured UI/scene context went away.
        now = time.monotonic()
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
                    _state, _message = "Connected", "Ready for spawn commands"
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
