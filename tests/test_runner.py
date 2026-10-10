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
        result = subprocess.run([sys.executable, '-m', 'companion.main', '--camera', '0', '--two-hands',
                                 '--model', '/tmp/air-modeler-nonexistent-model.task', '--mic'],
                                input='create cube\nquit\n', text=True, capture_output=True,
                                timeout=20, env=env, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DISCARDED', result.stdout)  # typed input parsed while offline
        self.assertIn('Other inputs remain available', result.stderr)
        self.assertIn('Server stopped', result.stdout)

class ConsoleIntegrationTests(unittest.TestCase):
    """Real main/config/service/parser; substitute devices and socket boundary."""

    def exercise(self, args, ptt=False, missing_key=False):
        import io
        import threading
        from unittest.mock import patch, MagicMock
        from companion.main import main
        from companion.voice.service import VoiceConfig, run_voice
        from companion.voice.transcripts import TranscriptHandler

        entered, finished = threading.Event(), threading.Event()
        captured = {}
        server = MagicMock(session_id='test', last_status=None, last_error=None)
        server.emit.return_value = True
        output = io.StringIO()

        def microphone(emit, stop, config):
            captured.update(config=config, stop=stop, thread=threading.current_thread())
            entered.set()
            try:
                stop.wait(3)
            finally:
                finished.set()

        def lines(stream, stop):
            if missing_key:
                self.assertTrue(entered.wait(2))
            if '--mic' in args and not missing_key:
                self.assertTrue(entered.wait(2))
                self.assertIsInstance(captured['config'], VoiceConfig)
                gate = captured['config'].push_to_talk_event
                self.assertEqual(gate is not None, ptt)
                if ptt:
                    self.assertFalse(gate.is_set())
            else:
                gate = None
            yield '/talk'
            if ptt:
                self.assertTrue(gate.is_set())
            yield '/talk'
            yield '/end'
            if ptt:
                self.assertFalse(gate.is_set())
                self.assertIs(gate, captured['config'].push_to_talk_event)
                # A timestamped commit arriving after /end executes once, not
                # blocked by the now-muted gate; duplicate/partial/plain do not.
                handler = TranscriptHandler(server.emit, stop, lambda _: None)
                event = dict(message_type='committed_transcript_with_timestamps',
                             text='create sphere', words=[dict(start=1., end=2.)])
                handler.handle(dict(event, message_type='partial_transcript'))
                handler.handle(dict(event, message_type='committed_transcript'))
                handler.handle(event)
                handler.handle(event)
            yield '/end'
            yield 'create cube'
            yield 'status'
            yield 'help'
            yield '/talk'  # Shutdown must clear an armed gate.
            yield 'quit'

        with patch('companion.main.BridgeServer', return_value=server), \
                patch('companion.main.typed_lines', side_effect=lines), \
                patch('sys.stdout', output), patch('sys.stderr', output):
            if missing_key:
                def checked_voice(*voice_args):
                    try:
                        return run_voice(*voice_args)
                    finally:
                        entered.set()
                with patch.dict(os.environ, {}, clear=True), patch(
                        'companion.voice.service.run_voice', side_effect=checked_voice):
                    result = main(args)
            else:
                # run_voice itself remains real: it must receive VoiceConfig
                # and pass it through to the microphone entrypoint unchanged.
                with patch('companion.voice.microphone.run_microphone', side_effect=microphone):
                    result = main(args)
        self.assertEqual(result, 0)
        server.close.assert_called_once()
        commands = [call.args[0] for call in server.emit.call_args_list]
        self.assertEqual([e['payload']['shape'] for e in commands],
                         ['sphere', 'cube'] if ptt else ['cube'])
        for event in commands:
            validate_event(event)
        if captured:
            self.assertTrue(finished.is_set())
            self.assertFalse(captured['thread'].is_alive())
            self.assertTrue(captured['stop'].is_set())
            if ptt:
                self.assertFalse(captured['config'].push_to_talk_event.is_set())
                self.assertEqual(output.getvalue().count('PTT ARMED'), 2)
        return output.getvalue()

    def test_ptt_console_real_config_and_release_commit(self):
        self.exercise(['--mic', '--push-to-talk', '--device', '1'], ptt=True)

    def test_hands_free_and_disabled_controls(self):
        self.assertIn('PTT unavailable', self.exercise(['--mic']))
        self.assertIn('PTT unavailable', self.exercise([]))

    def test_missing_key_keeps_typed_input(self):
        output = self.exercise(['--mic', '--push-to-talk'], missing_key=True)
        self.assertIn('ELEVENLABS_API_KEY is missing', output)
        self.assertIn('Other inputs remain available', output)

    def test_ptt_requires_microphone(self):
        from companion.main import main
        from unittest.mock import patch
        with patch('sys.stderr'), self.assertRaises(SystemExit) as result:
            main(['--push-to-talk'])
        self.assertEqual(result.exception.code, 2)


class ExplicitHandModeTests(unittest.TestCase):
    def test_camera_cannot_silently_choose_legacy(self):
        from companion.main import main
        from unittest.mock import patch
        for args in (['--camera','0'],['--legacy-hands'],['--camera','0','--two-hands','--legacy-hands']):
            with patch('sys.stderr'), self.assertRaises(SystemExit) as result:
                main(args)
            self.assertEqual(result.exception.code,2)

    def test_explicit_legacy_and_revised_modes_reach_worker_unchanged(self):
        from companion.main import main
        from unittest.mock import patch, MagicMock
        import threading
        for flag, expected in (('--legacy-hands',False),('--two-hands',True)):
            captured={}; entered=threading.Event()
            def tracker(emit,stop,config):
                captured.update(config);entered.set();stop.wait(2)
            def lines(*args):
                self.assertTrue(entered.wait(2));yield 'quit'
            with patch('companion.main.BridgeServer',return_value=MagicMock()), patch('companion.main.typed_lines',side_effect=lines), patch('companion.hands.tracker.run_hand_tracker',side_effect=tracker), patch('sys.stdout'):
                self.assertEqual(main(['--camera','0',flag]),0)
            self.assertEqual(captured['two_hands'],expected)
            self.assertFalse(captured['preview'])
