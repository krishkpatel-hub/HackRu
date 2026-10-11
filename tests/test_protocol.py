import json
import unittest
from uuid import uuid4

from shared.protocol import Channel, MAX_LINE, ProtocolError, Session, decode, encode, validate_event


def spawn(shape="cube", identifier=None):
    return {"type": "command", "payload": {"id": identifier or str(uuid4()), "action": "spawn", "shape": shape}}


def paired():
    client, server = Session("client"), Session("server")
    _, reply = server.accept(client.wrap({"type": "hello", "payload": {}}))
    client.accept(reply)
    return client, server


class SocketStub:
    def __init__(self, chunks=(), write_size=3):
        self.chunks = list(chunks)
        self.sent = b""
        self.write_size = write_size

    def recv(self, limit):
        if not self.chunks:
            raise BlockingIOError
        chunk = self.chunks.pop(0)
        assert len(chunk) <= limit
        return chunk

    def send(self, data):
        if self.write_size == 0:
            raise BlockingIOError
        part = data[:self.write_size]
        self.sent += part
        return len(part)


class ProtocolTests(unittest.TestCase):
    def test_split_and_combined_lines(self):
        client, server = paired()
        a, b = server.wrap(spawn()), server.wrap(spawn("prism"))
        data = encode(a) + encode(b)
        sock = SocketStub([data[:8], data[8:40], data[40:]])
        channel = Channel()
        self.assertEqual(channel.read(sock), [])
        self.assertEqual(channel.read(sock), [])
        self.assertEqual(channel.read(sock), [a, b])
        self.assertEqual(client.accept(a)[0]["payload"]["shape"], "cube")

    def test_malformed_followed_by_valid_and_oversized_recovery(self):
        _, server = paired()
        valid = server.wrap(spawn())
        channel = Channel()
        sock = SocketStub([b"{bad}\n\xff\n" + encode(valid)])
        result = channel.read(sock)
        self.assertTrue(all(isinstance(item, ProtocolError) for item in result[:2]))
        self.assertEqual(result[2], valid)
        channel = Channel()
        sock = SocketStub([b"x" * MAX_LINE, b"x\n" + encode(valid)])
        self.assertEqual(channel.read(sock), [])
        result = channel.read(sock)
        self.assertIsInstance(result[0], ProtocolError)
        self.assertEqual(result[1], valid)
        self.assertEqual(len(channel.partial), 0)

    def test_per_tick_limit_and_partial_writes(self):
        _, server = paired()
        messages = [server.wrap(spawn()) for _ in range(10)]
        sock = SocketStub([b"".join(map(encode, messages))])
        channel = Channel()
        self.assertEqual(len(channel.read(sock)), 4)
        self.assertEqual(len(channel.read(sock)), 4)
        self.assertEqual(len(channel.read(sock)), 2)
        channel.queue(messages[0])
        sock.write_size = 0
        channel.flush(sock)
        self.assertGreater(channel.pending_bytes, 0)
        sock.write_size = 3
        while channel.pending_bytes:
            channel.flush(sock)
        self.assertEqual(sock.sent, encode(messages[0]))
        with self.assertRaises(BufferError):
            for _ in range(1000):
                channel.queue(messages[0])

    def test_validation_and_sequence(self):
        client, server = paired()
        message = server.wrap(spawn())
        for field, value in (("v", 2), ("session_id", str(uuid4())), ("seq", True)):
            invalid = dict(message, **{field: value})
            with self.assertRaises(ProtocolError):
                client.accept(invalid)
        invalid = dict(message, payload=dict(message["payload"], shape="monkey"))
        with self.assertRaises(ProtocolError):
            client.accept(invalid)
        self.assertIsNotNone(client.accept(message)[0])
        with self.assertRaises(ProtocolError):
            client.accept(message)
        with self.assertRaises(ProtocolError):
            decode(b'{"v":1,"v":1}')
        with self.assertRaises(ProtocolError):
            validate_event({"type": "hand_frame", "payload": {"u": 10**1000, "v": 0, "present": True, "pinching": False}})

    def test_dedup_and_fresh_session(self):
        client, server = paired()
        event = spawn()
        self.assertIsNotNone(client.accept(server.wrap(event))[0])
        self.assertIsNone(client.accept(server.wrap(event))[0])
        old = server.wrap(spawn())
        fresh_client, fresh_server = paired()
        self.assertNotEqual(server.session_id, fresh_server.session_id)
        with self.assertRaises(ProtocolError):
            fresh_client.accept(old)
        self.assertIsNotNone(fresh_client.accept(fresh_server.wrap(event))[0])

    def test_callback_schemas(self):
        for mode in ("MOVE", "ROTATE", "SCALE", "EXTRUDE"):
            validate_event({"type": "command", "payload": {"id": str(uuid4()), "action": "set_mode", "mode": mode}})
        for kind in ("gesture_start", "gesture_end"):
            validate_event({"type": kind, "payload": {"gesture_id": str(uuid4()), "u": .4, "v": .6}})
        validate_event({"type": "hand_frame", "payload": {"u": None, "v": None, "present": False, "pinching": False}})
        with self.assertRaises(ProtocolError):
            validate_event(dict(spawn(), seq=1))
        with self.assertRaises(ProtocolError):
            validate_event({"type": "gesture_cancel", "payload": {"gesture_id": str(uuid4()), "reason": "\ud800"}})


if __name__ == "__main__":
    unittest.main()
