import io
import threading
import unittest
from uuid import UUID

from companion.voice.service import run_voice


class TypedServiceTests(unittest.TestCase):
    def test_typed_commands_use_contract_and_allow_repetition(self):
        events = []
        run_voice(events.append, threading.Event(),
                  {"source": "typed", "input_stream": io.StringIO(
                      "create cube\nwe talked about a sphere\ncreate cube\nRotate X!\n"),
                   "feedback": lambda message: None})
        self.assertEqual(len(events), 3)
        for event in events:
            self.assertEqual(set(event), {"type", "payload"})
            self.assertEqual(event["type"], "command")
            self.assertEqual(str(UUID(event["payload"]["id"])), event["payload"]["id"])
        self.assertNotEqual(events[0]["payload"]["id"], events[1]["payload"]["id"])
        self.assertEqual(events[2]["payload"]["axis"], "X")

    def test_stopped_service_emits_nothing(self):
        stop = threading.Event()
        stop.set()
        events = []
        run_voice(events.append, stop,
                  {"source": "typed", "input_stream": io.StringIO("undo\n")})
        self.assertEqual(events, [])
