import threading
import unittest

from companion.voice.transcripts import TranscriptHandler


def committed(text="Create cube.", start=1.0):
    return {"message_type": "committed_transcript_with_timestamps", "text": text,
            "words": [{"text": "Create", "start": start, "end": start + 0.2,
                       "type": "word"},
                      {"text": "cube.", "start": start + 0.3, "end": start + 0.7,
                       "type": "word"}]}


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.feedback = []
        self.stop = threading.Event()
        self.handler = TranscriptHandler(self.events.append, self.stop, self.feedback.append)

    def test_partials_are_feedback_only(self):
        self.handler.handle({"message_type": "partial_transcript", "text": "Create cube"})
        self.assertEqual(self.events, [])
        self.assertIn("Partial: Create cube", self.feedback)

    def test_overlapping_plain_and_timestamped_commits_execute_once(self):
        plain = {"message_type": "committed_transcript", "text": "Create cube."}
        for event in [plain, plain, committed(), committed(), plain, committed()]:
            self.handler.handle(event)
        self.assertEqual(len(self.events), 1)

    def test_reversed_pair_and_late_duplicate_execute_once(self):
        self.handler.handle(committed())
        self.handler.handle({"message_type": "committed_transcript", "text": "Create cube."})
        self.handler.handle(committed(start=5.0))
        self.handler.handle(committed())
        self.assertEqual(len(self.events), 2)

    def test_intentional_repetition_executes_even_without_intermediate_partial(self):
        self.handler.handle(committed())
        self.handler.handle(committed(start=2.0))
        self.assertEqual(len(self.events), 2)
        self.assertNotEqual(self.events[0]["payload"]["id"], self.events[1]["payload"]["id"])

    def test_repeated_keepalive_partial_does_not_rearm_duplicate(self):
        self.handler.handle(committed())
        self.handler.handle({"message_type": "partial_transcript", "text": "Create cube."})
        self.handler.handle(committed())
        self.assertEqual(len(self.events), 1)

    def test_unrelated_commits_do_not_execute(self):
        self.handler.handle(committed("I was talking about a cube"))
        self.assertEqual(self.events, [])

    def test_empty_or_malformed_timestamps_fail_closed(self):
        for words in [[], [{"text": "undo"}],
                      [{"start": float("nan"), "end": 1}],
                      [{"start": 5, "end": 1}], [{"start": -1, "end": 2}]]:
            self.handler.handle({"message_type": "committed_transcript_with_timestamps",
                                 "text": "undo", "words": words})
        self.assertEqual(self.events, [])
        self.assertTrue(self.feedback)

    def test_stopped_handler_does_not_execute(self):
        self.stop.set()
        self.handler.handle(committed())
        self.assertEqual(self.events, [])
