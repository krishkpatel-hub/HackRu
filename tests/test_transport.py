import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from companion.transport.server import BridgeServer, MAX_EVENTS
from shared.protocol import ADDRESS, Channel, Session, encode


def spawn():
    return {"type": "command", "payload": {"id": str(uuid4()), "action": "spawn", "shape": "cube"}}


def frame(u):
    return {"type": "hand_frame", "payload": {"u": u, "v": .5, "present": True, "pinching": False}}


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.server = BridgeServer(log=lambda _: None)
        self.server.start()
        self.sockets = []

    def tearDown(self):
        for sock in self.sockets:
            sock.close()
        self.server.close()

    def wait(self, predicate):
        end = time.monotonic() + 3
        while not predicate():
            self.assertLess(time.monotonic(), end, "Loopback timed out")
            time.sleep(.005)

    def connect(self, malformed=False):
        sock = socket.create_connection(ADDRESS, timeout=1)
        self.sockets.append(sock)
        session, channel = Session("client"), Channel()
        hello = encode(session.wrap({"type": "hello", "payload": {}}))
        # Exercise real split reads and complete malformed-line recovery.
        sock.sendall((b"not-json\n" if malformed else b"") + hello[:10])
        sock.sendall(hello[10:])
        sock.setblocking(False)
        def ready():
            for message in channel.read(sock):
                session.accept(message)
            return session.session_id is not None
        self.wait(ready)
        return sock, session, channel

    def test_loopback_status_and_reconnect_no_replay(self):
        self.assertFalse(self.server.emit(spawn()))
        sock, client, channel = self.connect(malformed=True)
        first_session = client.session_id
        status = {"type": "status", "payload": {"mode": "MOVE", "phase": "IDLE", "selected_object": None, "hovered_object": None, "tracking": False, "last_error": None}}
        channel.queue(client.wrap(status))
        self.wait(lambda: (channel.flush(sock) or self.server.last_status is not None))
        event = spawn()
        self.assertTrue(self.server.emit(event))
        self.assertTrue(self.server.emit(event))
        received = []
        def drained():
            for message in channel.read(sock):
                value, _ = client.accept(message)
                if value:
                    received.append(value)
            return client.duplicates == 1
        self.wait(drained)
        self.assertEqual(received, [event])
        # Leave an incomplete incoming status in the old server decoder.
        sock.send(encode(client.wrap(status))[:15])
        sock.close()
        self.wait(lambda: self.server.session_id is None)
        self.assertFalse(self.server.emit(spawn()))
        other, fresh, fresh_channel = self.connect()
        self.assertNotEqual(first_session, fresh.session_id)
        time.sleep(.05)
        self.assertEqual(fresh_channel.read(other), [])

    def test_one_client_and_shutdown(self):
        sock, _, _ = self.connect()
        other = socket.create_connection(ADDRESS, timeout=1)
        self.sockets.append(other)
        other.settimeout(1)
        self.assertEqual(other.recv(1), b"")
        self.server.close()
        sock.settimeout(1)
        self.assertEqual(sock.recv(1), b"")
        self.assertFalse(self.server.emit(spawn()))

    def test_ordering_coalescing_and_threaded_callback(self):
        # Isolate the callback queue to prove exact boundaries without a racing writer.
        queue_server = BridgeServer(log=lambda _: None)
        queue_server._session_id = str(uuid4())
        a, b = spawn(), spawn()
        for event in (frame(.1), frame(.2), a, frame(.3), frame(.4), b):
            self.assertTrue(queue_server.emit(event))
        self.assertEqual(list(queue_server._events), [frame(.2), a, frame(.4), b])
        queue_server._events.clear()
        commands = [spawn() for _ in range(80)]
        threads = [threading.Thread(target=lambda batch=batch: [queue_server.emit(e) for e in batch]) for batch in (commands[:40], commands[40:])]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        events = list(queue_server._events)
        self.assertEqual(len(events), 80)
        for batch in (commands[:40], commands[40:]):
            positions = [events.index(event) for event in batch]
            self.assertEqual(positions, sorted(positions))
        for _ in range(MAX_EVENTS):
            queue_server.emit(spawn())
        self.assertTrue(queue_server._overflow.is_set())
        self.assertEqual(len(queue_server._events), MAX_EVENTS)
        queue_server._disconnect("Test loss")
        self.assertEqual(list(queue_server._events), [])
        self.assertIsNone(queue_server.session_id)

    def test_device_free_module_entry_point(self):
        self.server.close()  # Let the real runner own the fixed production port.
        result = subprocess.run([sys.executable, "-m", "companion.main"],
                                input="spawn cube\nstatus\nquit\n", text=True,
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Listening on 127.0.0.1:8765", result.stdout)
        self.assertIn("DISCARDED", result.stdout)

    def test_callback_in_flight_cannot_cross_reconnect(self):
        queue_server = BridgeServer(log=lambda _: None)
        queue_server._session_id = str(uuid4())
        entered, resume = threading.Event(), threading.Event()
        accepted = []
        def paused_copy(value):
            entered.set()
            self.assertTrue(resume.wait(1))
            return value
        with patch("companion.transport.server.copy.deepcopy", side_effect=paused_copy):
            thread = threading.Thread(target=lambda: accepted.append(queue_server.emit(spawn())))
            thread.start()
            self.assertTrue(entered.wait(1))
            queue_server._disconnect("Test reconnect")
            queue_server._session_id = str(uuid4())
            resume.set()
            thread.join(timeout=1)
        self.assertEqual(accepted, [False])
        self.assertEqual(list(queue_server._events), [])


if __name__ == "__main__":
    unittest.main()
