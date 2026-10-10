import json
import os
import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
    def test_typed_cli_outputs_only_json_and_fresh_ids(self):
        result = subprocess.run([sys.executable, "-m", "companion.voice", "--typed"],
                                input="ADD SPHERE!\nconversation about a cube\nadd sphere\n",
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["payload"]["shape"], "sphere")
        self.assertNotEqual(events[0]["payload"]["id"], events[1]["payload"]["id"])

    def test_microphone_failure_keeps_typed_path_alive(self):
        environment = dict(os.environ)
        environment.pop("ELEVENLABS_API_KEY", None)
        result = subprocess.run([sys.executable, "-m", "companion.voice", "--mic"],
                                input="undo\n", text=True, capture_output=True,
                                env=environment, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ELEVENLABS_API_KEY", result.stderr)
        self.assertEqual(json.loads(result.stdout)["payload"]["action"], "undo")

    def test_partial_line_does_not_block_external_stop(self):
        import threading

        from companion.voice.service import run_voice

        reader, writer = os.pipe()
        stop = threading.Event()
        events = []
        with os.fdopen(reader, "r") as stream:
            worker = threading.Thread(target=run_voice, args=(events.append, stop,
                                      {"source": "typed", "input_stream": stream}))
            try:
                worker.start()
                os.write(writer, b"create")
                stop.set()
                worker.join(2)
                self.assertFalse(worker.is_alive())
                self.assertEqual(events, [])
            finally:
                os.close(writer)
                stop.set()
                worker.join(2)
