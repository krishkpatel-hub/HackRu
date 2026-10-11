"""Microphone audio through the official ElevenLabs SDK, without a custom socket.

SDK pattern: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming
Audio buffers: https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html
"""

import asyncio
import base64
import os
import queue
import sys
from array import array
from threading import Event

from .service import VoiceError
from .transcripts import TranscriptHandler

ERROR_HINTS = {
    "auth_error": "Authentication failed. Check the key and its Speech to Text permission.",
    "quota_exceeded": "Scribe quota exceeded. Check sponsored credits and key spending limits.",
    "unaccepted_terms": "Accept the Scribe terms in the ElevenLabs dashboard.",
    "rate_limited": "Scribe rate limit reached. Close other sessions and try again later.",
    "input_error": "Scribe rejected audio. Check mono int16 PCM and sample rate.",
    "invalid_request": "Scribe rejected connection options. Check the pinned SDK version.",
    "commit_throttled": "Scribe commits were too frequent. Leave a pause between PTT turns.",
    "queue_overflow": "Scribe audio queue overflowed. Restart voice on a stable connection.",
    "resource_exhausted": "Scribe is at capacity. Try again later.",
    "session_time_limit_exceeded": "Scribe session time limit reached. Restart voice.",
    "chunk_size_exceeded": "Scribe rejected the audio chunk size.",
    "insufficient_audio_activity": "Scribe closed an inactive audio session. Restart voice.",
}


def _dependencies():
    try:
        import elevenlabs
        import httpx
        import sounddevice
    except (ImportError, OSError) as error:
        raise VoiceError(
            "Audio dependencies unavailable. Install companion/voice/requirements.txt; "
            "Linux also needs PortAudio. Typed commands remain available."
        ) from error
    return sounddevice, elevenlabs, httpx


class _Stopped(Exception):
    pass


async def _interruptible(awaitable, stop, failures, timeout):
    """Bound connect/send waits, and cancel them promptly on an external stop."""
    task = asyncio.ensure_future(awaitable)
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while not task.done():
            if stop.is_set():
                raise _Stopped()
            if failures:
                raise failures[0]
            if asyncio.get_running_loop().time() >= deadline:
                raise VoiceError("Scribe connection or send timed out. Check network access.")
            await asyncio.wait([task], timeout=0.05)
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def _stream(emit, stop, config, api_key, dependencies):
    sd, sdk, httpx = dependencies
    if config.sample_rate not in {8000, 16000, 22050, 24000, 44100, 48000}:
        raise VoiceError("Unsupported PCM sample rate; use 16000 or 48000.")
    if config.connection_timeout <= 0 or config.operation_timeout <= 0:
        raise VoiceError("Connection and operation timeouts must be positive.")
    config.feedback("Checking microphone access. Allow the OS microphone prompt if shown.")
    try:
        sd.check_input_settings(device=config.device, channels=1, dtype="int16",
                                samplerate=config.sample_rate)
    except Exception as error:
        raise VoiceError(
            "Microphone unavailable. Check OS microphone permission, input device, "
            "and sample rate (try --sample-rate 48000). On macOS use System Settings > "
            "Privacy & Security > Microphone for the launching app."
        ) from error

    chunks = queue.Queue(maxsize=10)  # At most one second of queued audio.
    audio_failed = Event()
    closing = Event()
    failures = []
    ready = asyncio.Event()
    connection = None
    gate = config.push_to_talk_event
    handler = TranscriptHandler(emit, stop, config.feedback)

    def capture(indata, frames, time_info, status):
        if stop.is_set():
            return
        if status:
            audio_failed.set()
            return
        active = gate is None or gate.is_set()
        data = bytes(indata) if active else bytes(len(indata))
        if sys.byteorder != "little":
            samples = array("h", data)
            samples.byteswap()
            data = samples.tobytes()
        try:
            chunks.put_nowait((data, active))
        except queue.Full:
            audio_failed.set()

    def transcript(data):
        if failures or audio_failed.is_set() or closing.is_set():
            return
        try:
            handler.handle(data)
        except Exception as error:
            # The SDK prints callback exceptions to stdout; catch them here so
            # JSON stdout stays clean and exception messages cannot expose secrets.
            failures.append(VoiceError(f"Voice callback failed ({type(error).__name__})."))

    def on_error(data):
        kind = data.get("message_type", "error") if isinstance(data, dict) else "error"
        failures.append(VoiceError(ERROR_HINTS.get(
            kind, "Scribe connection failed. Check network, SDK version, and account access."
        )))

    def on_close():
        if not stop.is_set() and not failures:
            failures.append(VoiceError("Scribe connection closed. Restart microphone mode."))

    # Give the SDK an owned HTTP client so its underlying resource is also closed.
    with httpx.Client() as http_client:
        try:
            client = sdk.ElevenLabs(api_key=api_key, httpx_client=http_client)
            options = sdk.RealtimeAudioOptions(
                model_id="scribe_v2_realtime",
                audio_format=sdk.AudioFormat(f"pcm_{config.sample_rate}"),
                sample_rate=config.sample_rate,
                commit_strategy=sdk.CommitStrategy.MANUAL if gate is not None
                else sdk.CommitStrategy.VAD,
                include_timestamps=True,
                language_code="en",
                vad_silence_threshold_secs=0.6,
            )
            async def connect_registered():
                # Register in the same task as connect(), before the SDK's newly
                # scheduled receiver can consume session_started or an auth error.
                conn = await client.speech_to_text.realtime.connect(options)
                events = sdk.RealtimeEvents
                conn.on(events.SESSION_STARTED, lambda data: ready.set())
                conn.on(events.PARTIAL_TRANSCRIPT, transcript)
                conn.on(events.COMMITTED_TRANSCRIPT, transcript)
                conn.on(events.COMMITTED_TRANSCRIPT_WITH_TIMESTAMPS, transcript)
                conn.on(events.ERROR, on_error)
                conn.on(events.CLOSE, on_close)
                return conn

            connection = await _interruptible(connect_registered(), stop, failures,
                                              config.connection_timeout)
            await _interruptible(ready.wait(), stop, failures, config.connection_timeout)
            if failures:
                raise failures[0]
            if stop.is_set():
                return
            config.feedback("Scribe session ready. Opening microphone; typed commands remain active.")
            try:
                stream = sd.RawInputStream(
                    samplerate=config.sample_rate, blocksize=config.sample_rate // 10,
                    device=config.device, channels=1, dtype="int16", callback=capture)
                with stream:
                    was_active = False
                    shown_state = None
                    while not stop.is_set():
                        if failures:
                            raise failures[0]
                        if audio_failed.is_set():
                            raise VoiceError("Microphone audio overflowed. Restart voice; reduce load.")
                        if not stream.active:
                            raise VoiceError("Microphone stopped unexpectedly. Check the input device.")
                        state = "MUTED" if gate is not None and not gate.is_set() else "LISTENING — CREATE/REMOVE ONLY"
                        if state != shown_state:
                            config.state(state)
                            shown_state = state
                        try:
                            data, active = chunks.get_nowait()
                        except queue.Empty:
                            await asyncio.sleep(0.02)
                            continue
                        await _interruptible(connection.send({
                            "audio_base_64": base64.b64encode(data).decode("ascii"),
                            "sample_rate": config.sample_rate,
                        }), stop, failures, config.operation_timeout)
                        if gate is not None and was_active and not active:
                            await _interruptible(connection.commit(), stop, failures,
                                                 config.operation_timeout)
                        was_active = active
            except VoiceError:
                raise
            except _Stopped:
                raise
            except Exception:
                raise VoiceError(
                    "Microphone streaming failed. Check microphone permission and input device; "
                    "typed commands remain available."
                ) from None
        except _Stopped:
            pass
        except VoiceError:
            raise
        except Exception as error:
            # Do not echo raw SDK/provider exceptions (they may contain credentials).
            detail = str(error).lower()
            if "certificate" in detail or "ssl" in detail:
                hint = "TLS verification failed. Fix Python's CA certificates; keep verification enabled."
            elif "401" in detail or "403" in detail:
                hint = ERROR_HINTS["auth_error"]
            elif "429" in detail:
                hint = ERROR_HINTS["rate_limited"]
            else:
                hint = "Scribe connection failed. Check internet access and sponsored Scribe access."
            raise VoiceError(hint) from None
        finally:
            closing.set()
            if connection is not None:
                try:
                    await asyncio.wait_for(connection.close(), config.operation_timeout)
                except Exception:
                    config.feedback("Scribe close timed out or failed; the voice event loop is stopping.")


def run_microphone(emit, stop_event, config) -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise VoiceError("ELEVENLABS_API_KEY is missing. Set it in the environment; use --no-mic for the companion or --typed for the voice diagnostic meanwhile.")
    dependencies = _dependencies()
    async def sessions():
        while not stop_event.is_set():
            config.state("CONNECTING")
            if config.session_id:
                while config.session_id() is None and not stop_event.is_set():
                    await asyncio.sleep(.05)
            if stop_event.is_set():
                break
            session = config.session_id() if config.session_id else None
            if config.session_id and session is None:
                continue  # Disconnected between the readiness check and capture.
            class StreamStop:
                def is_set(self, expected=session):
                    return stop_event.is_set() or bool(config.session_id and config.session_id() != expected)
            # The final transport check is atomic with enqueue, closing the
            # callback/reconnect race as well as dropping old SDK callbacks.
            bound_emit = (lambda event, expected=session: config.emit_for_session(event, expected)) if config.emit_for_session else emit
            await _stream(bound_emit, StreamStop(), config, api_key, dependencies)
            if not config.session_id:
                break
            # _stream has closed its mic/SDK/HTTP resources before the next opens.
    asyncio.run(sessions())
