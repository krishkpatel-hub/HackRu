import asyncio
import base64
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from companion.voice import microphone
from companion.voice.service import VoiceConfig, VoiceError, run_voice


class FakeAudio:
    def __init__(self, stop, gate=None, fail=False):
        self.stop, self.gate, self.fail = stop, gate, fail
        self.closed = False
        self.active = True
        self.options = None

    def check_input_settings(self, **options):
        if self.fail:
            raise RuntimeError("permission denied")

    def RawInputStream(self, **options):
        self.options = options
        return self

    def __enter__(self):
        async def produce():
            if self.gate:
                self.gate.set()
            self.options["callback"](b"\x01\x00" * 1600, 1600, None, False)
            await asyncio.sleep(0.02)
            if self.gate:
                self.gate.clear()
            self.options["callback"](b"\x01\x00" * 1600, 1600, None, False)
        self.task = asyncio.create_task(produce())
        return self

    def __exit__(self, *args):
        self.task.cancel()
        self.closed = True
        self.active = False


class FakeConnection:
    def __init__(self, stop, error=None):
        self.stop, self.error = stop, error
        self.handlers = {}
        self.audio = []
        self.closed = False
        self.commits = 0

    def on(self, event, handler):
        self.handlers[event] = handler

    async def send(self, data):
        self.audio.append(base64.b64decode(data["audio_base_64"]))
        if self.error:
            self.handlers["error"]({"message_type": self.error, "error": "secret-value"})
        if len(self.audio) == 2 and "manual" != self.strategy:
            self.stop.set()

    async def commit(self):
        self.commits += 1
        self.stop.set()

    async def close(self):
        self.closed = True


class FakeClient:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class MicrophoneTests(unittest.TestCase):
    def make_dependencies(self, stop, gate=None, error=None, audio_fail=False, connect=None):
        audio = FakeAudio(stop, gate, audio_fail)
        connection = FakeConnection(stop, error)
        client = FakeClient()

        async def default_connect(options):
            connection.strategy = options["commit_strategy"]
            connection.options = options
            # Match the SDK: its receiver starts immediately as connect returns.
            asyncio.get_running_loop().call_soon(
                lambda: connection.handlers.get("session_started", lambda data: None)(
                    {"session_id": "test"}))
            return connection

        events = SimpleNamespace(**{name.upper(): name for name in [
            "session_started", "partial_transcript", "committed_transcript",
            "committed_transcript_with_timestamps", "error", "close"]})
        sdk = SimpleNamespace(
            ElevenLabs=lambda **kw: SimpleNamespace(speech_to_text=SimpleNamespace(
                realtime=SimpleNamespace(connect=connect or default_connect))),
            RealtimeAudioOptions=dict,
            AudioFormat=lambda value: value,
            CommitStrategy=SimpleNamespace(MANUAL="manual", VAD="vad"),
            RealtimeEvents=events)
        httpx = SimpleNamespace(Client=lambda: client)
        return (audio, sdk, httpx), connection, client

    def test_missing_key_has_clear_error_without_loading_audio(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
                microphone, "_dependencies", side_effect=AssertionError("loaded audio")):
            with self.assertRaisesRegex(VoiceError, "ELEVENLABS_API_KEY"):
                run_voice(lambda event: None, threading.Event(), {})

    def test_pcm_stream_stops_and_closes_all_resources(self):
        stop = threading.Event()
        deps, conn, client = self.make_dependencies(stop)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            run_voice(lambda event: None, stop, {"feedback": lambda message: None})
        self.assertTrue(deps[0].closed and conn.closed and client.closed)
        self.assertEqual(conn.audio[0], b"\x01\x00" * 1600)
        self.assertTrue(conn.options["include_timestamps"])
        self.assertEqual(conn.options["audio_format"], "pcm_16000")
        self.assertEqual(deps[0].options["channels"], 1)
        self.assertEqual(deps[0].options["dtype"], "int16")

    def test_push_to_talk_sends_silence_when_released_and_commits_once(self):
        stop, gate = threading.Event(), threading.Event()
        deps, conn, client = self.make_dependencies(stop, gate)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            run_voice(lambda event: None, stop,
                      VoiceConfig(push_to_talk_event=gate, feedback=lambda message: None))
        self.assertEqual(conn.audio, [b"\x01\x00" * 1600, bytes(3200)])
        self.assertEqual(conn.commits, 1)
        self.assertTrue(conn.closed and deps[0].closed and client.closed)

    def test_quota_error_closes_resources_and_does_not_expose_key(self):
        stop = threading.Event()
        deps, conn, client = self.make_dependencies(stop, error="quota_exceeded")
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            with self.assertRaisesRegex(VoiceError, "quota") as caught:
                run_voice(lambda event: None, stop, {"feedback": lambda message: None})
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertTrue(conn.closed and deps[0].closed and client.closed)

    def test_microphone_failure_suggests_permission_fix(self):
        stop = threading.Event()
        deps, conn, client = self.make_dependencies(stop, audio_fail=True)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            with self.assertRaisesRegex(VoiceError, "permission"):
                run_voice(lambda event: None, stop, {"feedback": lambda message: None})
        self.assertFalse(conn.audio)

    def test_stop_interrupts_connection_attempt(self):
        stop = threading.Event()
        cancelled = []

        async def hanging_connect(options):
            try:
                stop.set()
                await asyncio.Future()
            finally:
                cancelled.append(True)

        deps, conn, client = self.make_dependencies(stop, connect=hanging_connect)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            run_voice(lambda event: None, stop, {"feedback": lambda message: None})
        self.assertTrue(cancelled and client.closed)

    def test_connection_timeout_cancels_attempt_and_closes_http(self):
        stop = threading.Event()
        cancelled = []

        async def hanging_connect(options):
            try:
                await asyncio.Future()
            finally:
                cancelled.append(True)

        deps, _conn, client = self.make_dependencies(stop, connect=hanging_connect)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            with self.assertRaisesRegex(VoiceError, "timed out"):
                run_voice(lambda event: None, stop,
                          {"connection_timeout": 0.01, "feedback": lambda message: None})
        self.assertTrue(cancelled and client.closed)

    def test_stop_interrupts_blocked_audio_send_and_closes_resources(self):
        stop = threading.Event()
        deps, conn, client = self.make_dependencies(stop)
        cancelled = []

        async def hanging_send(data):
            try:
                stop.set()
                await asyncio.Future()
            finally:
                cancelled.append(True)

        conn.send = hanging_send
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            run_voice(lambda event: None, stop, {"feedback": lambda message: None})
        self.assertTrue(cancelled and conn.closed and deps[0].closed and client.closed)

    def test_connection_exception_does_not_include_secret_in_traceback(self):
        import traceback

        stop = threading.Event()

        async def failed_connect(options):
            raise RuntimeError("SDK echoed secret-value")

        deps, _conn, client = self.make_dependencies(stop, connect=failed_connect)
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "secret-value"}), \
                patch.object(microphone, "_dependencies", return_value=deps):
            try:
                run_voice(lambda event: None, stop, {"feedback": lambda message: None})
            except VoiceError:
                self.assertNotIn("secret-value", traceback.format_exc())
            else:
                self.fail("Expected connection error")
        self.assertTrue(client.closed)
