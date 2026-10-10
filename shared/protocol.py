"""Air Modeler v1: the single standard-library wire/schema implementation.

The packager copies this file, unchanged, to air_modeler/_protocol.py in the ZIP.
"""

from collections import deque
import json
import math
from uuid import UUID, uuid4

ADDRESS = ("127.0.0.1", 8765)
VERSION = 1
MAX_LINE = 8192
MAX_OUTBOX = 65536
MAX_COMMAND_IDS = 4096
SHAPES = ("cube", "sphere", "cylinder", "prism")
MODES = ("MOVE", "ROTATE", "SCALE", "EXTRUDE")
PLANES = ("AUTO", "XY", "XZ", "YZ")
INPUT_TYPES = ("command", "hand_frame", "gesture_start", "gesture_end", "gesture_cancel", "selector_frame", "hands_frame")


class ProtocolError(ValueError):
    pass


class SessionFull(ProtocolError):
    """Reconnect rather than evict IDs and risk replay within a session."""


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def keys(value, required, optional=()):
    require(isinstance(value, dict), "Expected a JSON object")
    require(set(required) <= value.keys() <= set(required) | set(optional), "Unexpected or missing fields")


def uuid(value):
    require(isinstance(value, str) and len(value) == 36, "Expected a UUID string")
    try:
        require(str(UUID(value)) == value, "UUID must use canonical lowercase form")
    except (ValueError, AttributeError) as exc:
        raise ProtocolError("Invalid UUID") from exc


def text(value, nullable=False):
    require((nullable and value is None) or (isinstance(value, str) and len(value) <= 1024), "Expected text of at most 1024 characters")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ProtocolError("Text must be valid UTF-8") from exc


def coordinates(payload, absent=False):
    if absent and payload["u"] is None and payload["v"] is None:
        return
    for name in ("u", "v"):
        value = payload[name]
        require(type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value), "Coordinates must be finite and within 0–1")


def validate_precision(payload):
    mode = payload.get('mode')
    require(mode in MODES, "Invalid precision mode")
    keys(payload, ('id', 'action', 'mode', 'value'), ('axis',))
    require(('axis' in payload) == (mode in ('MOVE','ROTATE')), "MOVE/ROTATE require an axis; other modes forbid it")
    if 'axis' in payload:
        require(payload['axis'] in ('X','Y','Z'), "Invalid world axis")
    value = payload['value']
    require(finite_number(value), "Precision value must be finite")
    bounds = {'MOVE':(-100,100), 'ROTATE':(-360,360), 'SCALE':(.1,10), 'EXTRUDE':(.00001,4)}
    low, high = bounds[mode]
    require(low <= value <= high and (mode != 'EXTRUDE' or value > low), "Precision value outside supported bounds")


def validate_mode(payload):
    """Validate a staged one-operation override, without inventing defaults."""
    keys(payload, ("id", "action", "mode"), ("axis", "plane"))
    mode = payload["mode"]
    require(mode in MODES, "Invalid mode")
    if mode == "EXTRUDE":
        plane, axis = payload.get("plane", "AUTO"), payload.get("axis", "NONE")
        require(plane in PLANES, "Invalid extrusion plane")
        require(axis in ("NONE", "X", "Y", "Z"), "Invalid extrusion axis")
        require(plane == "AUTO" or axis == "NONE" or axis in plane,
                "Extrusion axis must belong to its mapping plane")
    else:
        require("plane" not in payload, "Only EXTRUDE accepts a plane")
        require("axis" not in payload or mode == "ROTATE", "Only ROTATE/EXTRUDE accept an axis")
        if "axis" in payload:
            require(payload["axis"] in ("FREE", "X", "Y", "Z"), "Invalid rotation axis")


def finite_number(value):
    """Reject booleans and excessively large JSON integers without overflowing."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_hand_observation(observation):
    keys(observation, ("valid", "confidence", "u", "v", "palm_u", "palm_v",
                       "pinching", "open", "gesture_id", "event", "shape_valid",
                       "shape_error", "angle", "openness", "open_palm",
                       "extrude_pose", "pinch_pending", "orientation", "fingers"))
    flags = ("valid", "pinching", "open", "shape_valid", "open_palm", "extrude_pose", "pinch_pending")
    for flag in flags:
        require(type(observation[flag]) is bool, "Hand observation flags must be booleans")
    confidence = observation["confidence"]
    require(finite_number(confidence) and 0 <= confidence <= 1, "Invalid handedness confidence")
    for field in ("u", "v", "palm_u", "palm_v"):
        value = observation[field]
        if observation["valid"]:
            require(finite_number(value) and 0 <= value <= 1, "Visible hand coordinates must be finite and within 0–1")
        else:
            require(value is None, "Invalid hand coordinates must be null")
    if not observation["valid"]:
        require(confidence == 0 and not any(observation[k] for k in flags[1:]),
                "Invalid observations cannot imply a pose or observed release")
    require(not (observation["pinching"] and observation["open"]), "A pinching hand cannot be observed open")
    text(observation['shape_error'], nullable=True)
    if observation['shape_valid']:
        require(observation['shape_error'] is None, "Valid measurements cannot carry a shape error")
        require(finite_number(observation['angle']) and -math.pi <= observation['angle'] <= math.pi,
                "Palm angle must be finite radians within ±pi")
        require(finite_number(observation['openness']) and 0 <= observation['openness'] <= 1,
                "Whole-hand openness must be finite within 0–1")
    else:
        require(observation['angle'] is None and observation['openness'] is None
                and not any(observation[k] for k in ('open_palm','extrude_pose','pinch_pending')),
                "Invalid shape measurements must be null and cannot authorize poses")
        require(bool(observation['shape_error']), "Invalid shape needs readable feedback")
    require(not observation['pinch_pending'] or observation['extrude_pose'],
            "Extrusion pinch approach requires remaining open fingers")
    for field, size in (('orientation',4),('fingers',4)):
        value=observation[field]
        if observation['shape_valid']:
            require(isinstance(value,list) and len(value)==size and all(finite_number(x) for x in value), 'Invalid 3D measurement')
            if field=='orientation':
                require(abs(sum(x*x for x in value)-1)<1e-4, 'Orientation must be unit quaternion')
            else:
                require(all(0<=x<=1 for x in value), 'Finger openness outside bounds')
                require(abs(sum(value)/4-observation['openness'])<1e-5, 'Incoherent aggregate openness')
        else:
            require(value is None, 'Invalid 3D measurements must be null')
    event, identifier = observation["event"], observation["gesture_id"]
    require(event in ("NONE", "START", "END", "CANCEL"), "Invalid hand boundary event")
    if event != "NONE" or observation["pinching"]:
        uuid(identifier)
    else:
        require(identifier is None, "Inactive observations cannot carry gesture IDs")
    if event == "START":
        require(observation["valid"] and observation["pinching"], "START requires an observed pinch")
    elif event == "END":
        require(observation["valid"] and observation["open"] and not observation["pinching"],
                "END requires an observed release")
    elif event == "CANCEL":
        require(not observation["pinching"], "CANCEL cannot retain an active pinch")


def validate_event(event):
    """Validate callback type/payload only; never add an envelope or mutate input."""
    keys(event, ("type", "payload"))
    kind, payload = event["type"], event["payload"]
    require(isinstance(kind, str), "Event type must be text")
    require(isinstance(payload, dict), "Payload must be an object")
    if kind == "hello":
        keys(payload, ())
    elif kind == "command":
        action = payload.get("action")
        require(isinstance(action, str), "Command action must be text")
        if action == "spawn":
            keys(payload, ("id", "action", "shape"))
            require(payload["shape"] in SHAPES, "Invalid spawn shape")
        elif action == "precision":
            validate_precision(payload)
        elif action == "set_mode":
            validate_mode(payload)
        else:
            require(action in ("cancel", "undo"), "Unknown command action")
            keys(payload, ("id", "action"))
        uuid(payload["id"])
    elif kind == "hands_frame":
        keys(payload, ("profile", "frame_id", "t", "aspect", "hands"))
        require(finite_number(payload["aspect"]) and .1 <= payload["aspect"] <= 10, "Invalid capture aspect")
        require(payload["profile"] == "left_clutch_v3", "Unsupported hand controls; install matching 0.9 companion/add-on")
        require(type(payload["frame_id"]) is int and 1 <= payload["frame_id"] <= 2**53 - 1,
                "Invalid capture frame ID")
        require(finite_number(payload["t"]) and payload["t"] >= 0, "Invalid capture elapsed time")
        keys(payload["hands"], ("Left", "Right"))
        for observation in payload["hands"].values():
            validate_hand_observation(observation)
    elif kind == "selector_frame":
        keys(payload, ('pose','manipulator','selector'))
        require(payload['pose'] in ('FIST','TWO','THREE','OPEN','UNKNOWN','ABSENT'), "Invalid selector pose")
        require(payload['manipulator'] in ('Left','Right') and payload['selector'] in ('Left','Right')
                and payload['manipulator'] != payload['selector'], "Invalid hand roles")
    elif kind == "hand_frame":
        keys(payload, ("u", "v", "present", "pinching"))
        require(type(payload["present"]) is bool and type(payload["pinching"]) is bool, "Hand flags must be booleans")
        coordinates(payload, absent=not payload["present"])
    elif kind in ("gesture_start", "gesture_end"):
        keys(payload, ("gesture_id", "u", "v"))
        uuid(payload["gesture_id"])
        coordinates(payload)
    elif kind == "gesture_cancel":
        keys(payload, ("gesture_id", "reason"))
        uuid(payload["gesture_id"])
        text(payload["reason"])
    elif kind == "status":
        keys(payload, ("mode", "phase", "selected_object", "hovered_object", "tracking", "last_error"))
        require(payload["mode"] in MODES, "Invalid status mode")
        require(payload["phase"] in ("IDLE", "SELECTED_READY", "DRAGGING", "NEEDS_RELEASE"), "Invalid phase")
        for field in ("selected_object", "hovered_object", "last_error"):
            text(payload[field], nullable=True)
        require(type(payload["tracking"]) is bool, "Tracking must be a boolean")
    else:
        raise ProtocolError("Unknown event type")
    return event


def validate_envelope(message):
    keys(message, ("v", "type", "session_id", "seq", "payload"))
    require(type(message["v"]) is int and message["v"] == VERSION, "Unsupported protocol version")
    require(type(message["seq"]) is int and 1 <= message["seq"] <= 2**53 - 1, "Invalid sequence number")
    if message["session_id"] is not None:
        uuid(message["session_id"])
    validate_event({"type": message["type"], "payload": message["payload"]})
    return message


def encode(message):
    validate_envelope(message)
    data = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    require(len(data) <= MAX_LINE, "Message exceeds line limit")
    return data + b"\n"


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def decode(line):
    try:
        return validate_envelope(json.loads(line.decode("utf-8"), object_pairs_hook=_object))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError("Malformed UTF-8 JSON line") from exc


class Session:
    """Direction, handshake, monotonic sequencing and per-session command dedup."""

    def __init__(self, role):
        require(role in ("client", "server"), "Invalid role")
        self.role = role
        self.session_id = None
        self.sent = self.received = 0
        self.command_ids = set()
        self.duplicates = 0

    def wrap(self, event):
        validate_event(event)
        if event["type"] == "hello":
            require(self.sent == 0, "Hello already sent")
        else:
            require(self.session_id is not None, "Handshake not complete")
            allowed = INPUT_TYPES if self.role == "server" else ("status",)
            require(event["type"] in allowed, "Wrong message direction")
        message = dict(event, v=VERSION, session_id=self.session_id, seq=self.sent + 1)
        encode(message)
        self.sent += 1
        return message

    def accept(self, message):
        """Return (event, handshake_reply); duplicates return (None, None)."""
        validate_envelope(message)
        if self.session_id is None:
            require(message["type"] == "hello" and message["seq"] == 1, "Expected hello with seq 1")
            if self.role == "server":
                require(message["session_id"] is None, "Initial hello session must be null")
                self.session_id = str(uuid4())
                self.received = 1
                return None, self.wrap({"type": "hello", "payload": {}})
            require(self.sent == 1 and message["session_id"] is not None, "Unexpected hello reply")
            self.session_id = message["session_id"]
            self.received = 1
            return None, None
        require(message["session_id"] == self.session_id, "Wrong session")
        require(message["seq"] > self.received, "Stale sequence number")
        allowed = ("status",) if self.role == "server" else INPUT_TYPES
        require(message["type"] in allowed, "Wrong message direction")
        self.received = message["seq"]
        if message["type"] == "command":
            identifier = message["payload"]["id"]
            if identifier in self.command_ids:
                self.duplicates += 1
                return None, None
            if len(self.command_ids) >= MAX_COMMAND_IDS:
                raise SessionFull("Session command limit reached; reconnect explicitly")
            self.command_ids.add(identifier)  # Consume even if the modeling action fails.
        return {"type": message["type"], "payload": message["payload"]}, None


class Channel:
    """Bounded nonblocking socket I/O. Never owns or closes the socket."""

    def __init__(self):
        self.partial = bytearray()
        self.discarding = False
        self.lines = deque()
        self.outgoing = deque()
        self.pending_bytes = 0

    def queue(self, message):
        data = encode(message)
        if self.pending_bytes + len(data) > MAX_OUTBOX:
            raise BufferError("Socket backpressure limit reached; reconnect required")
        self.outgoing.append(data)
        self.pending_bytes += len(data)

    def flush(self, sock):
        if not self.outgoing:
            return
        data = self.outgoing[0]
        try:
            count = sock.send(data[:16384])
        except (BlockingIOError, InterruptedError):
            return
        if count == 0:
            raise ConnectionError("Socket closed during write")
        self.pending_bytes -= count
        if count == len(data):
            self.outgoing.popleft()
        else:
            self.outgoing[0] = data[count:]

    def _feed(self, chunk):
        # One recv is at most MAX_LINE bytes; pending lines are drained before another.
        parts = chunk.split(b"\n")
        for index, part in enumerate(parts):
            complete = index < len(parts) - 1
            if not self.discarding:
                if len(self.partial) + len(part) > MAX_LINE:
                    self.partial.clear()
                    self.discarding = True
                    self.lines.append(ProtocolError("Line exceeds 8192 bytes"))
                else:
                    self.partial.extend(part)
            if complete:
                if not self.discarding:
                    self.lines.append(bytes(self.partial))
                self.partial.clear()
                self.discarding = False

    def read(self, sock, limit=4):
        """Return envelopes or ProtocolError values; bad lines never poison following ones."""
        if not self.lines:
            try:
                chunk = sock.recv(MAX_LINE)
            except (BlockingIOError, InterruptedError):
                chunk = None
            if chunk == b"":
                raise ConnectionError("Peer disconnected")
            if chunk:
                self._feed(chunk)
        result = []
        for _ in range(min(limit, len(self.lines))):
            line = self.lines.popleft()
            if isinstance(line, ProtocolError):
                result.append(line)
            else:
                try:
                    result.append(decode(line))
                except ProtocolError as exc:
                    result.append(exc)
        return result
