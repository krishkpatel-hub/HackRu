"""P-owned integration checks for typed parsing and optional-worker isolation."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from companion.main import typed_event
from shared.protocol import validate_event


class RunnerTests(unittest.TestCase):
    def test_typed_parser_and_uuid(self):
        events = [typed_event(text) for text in ('create cube', 'spawn cube', 'Create cube!', 'undo', 'cancel', 'move')]
        for event in events:
            validate_event(event)
        self.assertEqual(len({e['payload']['id'] for e in events}), len(events))
        self.assertEqual(events[0]['payload']['shape'], 'cube')
        self.assertIsNone(typed_event('create cube and undo'))

    def test_failed_devices_leave_typed_input_and_shutdown(self):
        env = dict(os.environ)
        env.pop('ELEVENLABS_API_KEY', None)
        result = subprocess.run([sys.executable, '-m', 'companion.main', '--camera', '0',
                                 '--model', '/tmp/air-modeler-nonexistent-model.task', '--mic'],
                                input='create cube\nquit\n', text=True, capture_output=True,
                                timeout=20, env=env, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DISCARDED', result.stdout)  # typed input parsed while offline
        self.assertIn('Other inputs remain available', result.stderr)
        self.assertIn('Server stopped', result.stdout)
