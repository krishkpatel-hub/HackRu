"""One localhost Blender client; one writer; bounded, thread-safe input callback."""

from collections import deque
import copy
import socket
import threading
import time

from shared.protocol import ADDRESS, INPUT_TYPES, Channel, ProtocolError, Session, validate_event

MAX_EVENTS = 256


class BridgeServer:
    def __init__(self, log=print):
        self.log = log
        self.last_error = None
        self.last_status = None
        self._lock = threading.Lock()
        self._events = deque()
        self._session_id = None
        self._overflow = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._listener = self._client = None
        self._session = self._channel = None

    @property
    def session_id(self):
        with self._lock:
            return self._session_id

    def emit(self, event) -> bool:
        """Accept only {type, payload}. Never wait for network I/O or queue space.

        Return False for invalid/offline/full input; callers must not retry stale
        actions on reconnect. A full queue faults the connection rather than
        silently losing gesture/command boundaries. Input is snapshotted.
        """
        with self._lock:
            session_id = self._session_id
        if session_id is None:
            self.last_error = "No ready Blender session; input discarded"
            return False
        try:
            validate_event(event)
            if event["type"] not in INPUT_TYPES:
                raise ProtocolError("Callback accepts only commands and hand events")
            event = copy.deepcopy(event)
        except (ProtocolError, RecursionError) as exc:
            self.last_error = str(exc)
            return False
        with self._lock:  # Short memory-only critical section; no socket/log calls.
            if self._session_id != session_id or self._overflow.is_set():
                self.last_error = "Session changed or faulted; input discarded"
                return False
            if event["type"] == "hand_frame" and self._events and self._events[-1]["type"] == "hand_frame":
                self._events[-1] = event
            elif len(self._events) >= MAX_EVENTS:
                self.last_error = "Input queue full; disconnecting to preserve event boundaries"
                self._overflow.set()
                return False
            else:
                self._events.append(event)
        return True

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Server already started")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(ADDRESS)
            listener.listen(1)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self._listener = listener
        self._thread = threading.Thread(target=self._run, name="air-modeler-transport", daemon=True)
        self._thread.start()
        self.log(f"Listening on {ADDRESS[0]}:{ADDRESS[1]}; waiting for Blender")

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError("Transport thread failed to stop")

    def _disconnect(self, reason):
        with self._lock:
            self._session_id = None
            self._events.clear()
            self._overflow.clear()
        if self._client is not None:
            self._client.close()
        self._client = self._session = self._channel = None
        self.last_status = None
        self.log(reason)

    def _tick(self):
        try:
            connection, _ = self._listener.accept()
        except BlockingIOError:
            pass
        else:
            # A reconnect can reach accept before this tick observes the old
            # client's EOF. Reap a closed peer without consuming live bytes.
            if self._client is not None:
                try:
                    closed = self._client.recv(1, socket.MSG_PEEK) == b""
                except (BlockingIOError, InterruptedError):
                    closed = False
                except OSError:
                    closed = True
                if closed:
                    self._disconnect("Disconnected: old peer closed before reconnect")
            if self._client is not None:
                connection.close()  # One client, including the handshake phase.
            else:
                connection.setblocking(False)
                self._client = connection
                self._session = Session("server")
                self._channel = Channel()
                self._deadline = time.monotonic() + 5
                self.log("Blender TCP connection accepted; awaiting hello")
        if self._client is None:
            return
        if self._overflow.is_set():
            raise BufferError(self.last_error)
        if self._session.session_id is None and time.monotonic() > self._deadline:
            raise ConnectionError("Hello timeout")
        # Read before enqueueing outbound input, so an observed EOF clears pending input.
        for message in self._channel.read(self._client, limit=16):
            try:
                if isinstance(message, ProtocolError):
                    raise message
                event, reply = self._session.accept(message)
                if reply is not None:
                    self._channel.queue(reply)
                    with self._lock:
                        self._events.clear()
                        self._session_id = self._session.session_id
                    self.log(f"READY session={self._session.session_id}")
                if event is not None:
                    status = event["payload"]
                    if status != self.last_status:
                        self.log(f"STATUS {status}")
                    self.last_status = status
            except ProtocolError as exc:
                self.last_error = str(exc)
                self.log(f"Rejected Blender message: {exc}")
        with self._lock:
            batch = [self._events.popleft() for _ in range(min(4, len(self._events)))]
        for event in batch:
            self._channel.queue(self._session.wrap(event))
        self._channel.flush(self._client)

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    self._tick()
                except (OSError, BufferError) as exc:
                    self.last_error = str(exc)
                    self._disconnect(f"Disconnected: {exc}")
                self._stop.wait(1 / 120)
        finally:
            self._disconnect("Server stopped; pending input discarded")
            self._listener.close()
