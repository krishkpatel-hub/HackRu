# Voice handoff — HackRU

Branch: `feature/voice`. Base agreement: main commit
`46c25b9e63e67ddbfddffc14119de3a87e386eff`. No interface discrepancies found.
Get the final checkout SHA with `git rev-parse HEAD`; the delivery message also
records it. Only `companion/voice/`, `tests/test_voice_*`, and this document are owned
by this change.

## Launch from the repository root

Typed commands require Python 3.10+ and no third-party packages or API key:

```sh
python3 -m companion.voice --typed
```

Enter one complete phrase per line. `/quit`, Ctrl+C, or stdin EOF exits. Example:

```sh
printf 'Create cube!\nRotate X.\nUndo\n' | python3 -m companion.voice --typed
```

stdout contains only callback JSON, one object per line. Diagnostics, partial
transcripts, committed feedback, and rejected input go to stderr. The
`--list-devices` utility prints a device listing instead of command JSON.

Install audio packages in the external companion environment, outside Blender:

```sh
python3 -m venv /tmp/hackru-voice-venv
source /tmp/hackru-voice-venv/bin/activate
python -m pip install -r companion/voice/requirements.txt
python -m companion.voice --list-devices
```

macOS wheels include PortAudio. Linux installations may additionally need the
distribution's PortAudio library (for example `libportaudio2`). Do not change the
root dependency files independently; P can adopt these pins during integration.

Set the key in the launching shell. This **zsh** prompt hides it and avoids placing
the value in command history:

```sh
read -r -s 'ELEVENLABS_API_KEY?ElevenLabs API key: '
export ELEVENLABS_API_KEY
printf '\n'
```

Hands-free microphone mode, with typed commands always available:

```sh
python -m companion.voice --mic
```

Use the device listing to select an input. Example for the enumerated MacBook
microphone (indexes may change):

```sh
python -m companion.voice --mic --device 1 --sample-rate 16000
```

If the device rejects 16 kHz, try `--sample-rate 48000`. No resampling is performed;
the provider format is changed to match the requested supported rate.

Optional push-to-talk:

```sh
python -m companion.voice --mic --push-to-talk --device 1
```

Enter `/talk`, speak one supported phrase, then enter `/end`. Release sends a
manual commit. Wait for committed feedback before the next turn. This terminal
control uses two presses rather than a held global hotkey. The integration owner
can implement a held button by setting/clearing `push_to_talk_event` below.
Release is sampled at the 100 ms microphone callback boundary. Do not tap faster
than that. Muted input is replaced with zero PCM samples; the API session stays
open and silent audio is still streamed and may incur usage.

If Python reports a TLS certificate error, retain verification and point Python
at the installed CA bundle:

```sh
SSL_CERT_FILE="$(python -m certifi)" python -m companion.voice --mic
```

## Integration contract

```python
from threading import Event, Thread
from companion.voice.parser import parse_command
from companion.voice.service import VoiceConfig, VoiceError, run_voice

stop_event = Event()  # Owned by P; setting it requests shutdown.
talk_event = Event()  # Optional: set while a PTT button is held; clear on release.
config = VoiceConfig(push_to_talk_event=talk_event)

def voice_worker():
    try:
        run_voice(emit, stop_event, config)  # P supplies thread-safe/nonblocking emit.
    except VoiceError as error:
        show_voice_status(str(error))     # P's UI; typed commands can continue.

worker = Thread(target=voice_worker, name="voice")
worker.start()
# When shutting down: stop_event.set(); worker.join().
```

`emit` and `show_voice_status` above are P's callbacks, not exports of this module.
Run microphone service in a worker thread, not inside an existing asyncio loop.
`config` accepts `VoiceConfig`, a dictionary of its fields, or `None` for defaults:

| Field | Default | Meaning |
| --- | --- | --- |
| `source` | `"microphone"` | `"microphone"` or `"typed"` |
| `input_stream` | `None` | Typed input stream; defaults to stdin |
| `feedback` | stderr printer | Callable accepting a status/transcript string |
| `device` | `None` | PortAudio input index/name; default OS input |
| `sample_rate` | `16000` | PCM rate: 8000, 16000, 22050, 24000, 44100, or 48000 |
| `push_to_talk_event` | `None` | `threading.Event`; None enables hands-free VAD |
| `connection_timeout` | `10.0` | Seconds for connect and session acknowledgement |
| `operation_timeout` | `5.0` | Seconds for audio sends, commits, and closing |

`run_voice(emit, stop_event, config) -> None` raises `VoiceError` on voice failure.
The standalone CLI catches it and leaves typed input running. An injected feedback
callback should be nonblocking and safe for the voice worker thread.

`parse_command(text) -> dict | None` returns a fresh action payload **without id**.
The service adds a new UUID for each accepted utterance/typed line and calls:

```json
{"type":"command","payload":{"id":"<uuid>","action":"spawn","shape":"cube"}}
```

P adds the wire envelope and handles Blender state. This module creates no
application sockets and does not import Blender, hands, or transport.

Commands match entire normalized phrases. Case, punctuation, and whitespace are
normalized; extra conversational words and compound commands are rejected.
`create`/`add` accept cube, sphere, cylinder, prism, and triangular prism (both
prism aliases support `add`, consistent with the README's create/add action).
`rotate x/y/z` selects that axis; bare `rotate` defaults to Z. `scale`, `extrude`,
`move`, `cancel`, and `undo` follow the README exactly.

## Transcripts and resource behavior

Audio is mono signed 16-bit **little-endian** PCM in 100 ms chunks. Hands-free mode
uses Scribe VAD with a 0.6 second silence threshold. PTT uses manual commits.
Provider processing initially requires about two seconds of streamed audio;
startup recognition is therefore not instantaneous.

The SDK connection always requests `include_timestamps=True`. Partial and plain
committed events provide feedback; **only timestamped committed events execute**.
Plain/timestamped pairs consequently cannot execute twice. Deduplication uses
normalized text and word spans in the provider's session audio timeline, not a
text cooldown. Later identical commands with new timing get new UUIDs, even
without an intermediate partial. Spacing entries are excluded from fingerprints.
The cache retains 1024 recent spans and rejects replays at/before the evicted
audio watermark. Missing/malformed timestamps fail closed. Keep timestamps enabled;
verify their session timeline in the live API rehearsal. No reconnect/replay occurs.

Queues hold at most one second of audio. Capture status errors or overflow stop
voice rather than replaying stale audio. Stop interrupts Python input polling and
SDK connect/send waits, closes the microphone context, awaits API close, and
closes the owned HTTP client. Pending speech is discarded on stop. Raw provider
error/exception text is not printed or included in public exception tracebacks.
Auth, quota, terms, rate-limit, input, connection, and timeout failures have
actionable messages; the API key is read only from the environment.

## Verify sponsored realtime access

1. Select the **sponsored workspace** in the ElevenLabs dashboard. Confirm the key
   belongs to that workspace and has Speech to Text access; inspect key spending
   limits and remaining workspace credits. Accept Scribe terms if requested.
2. Ask the sponsor/workspace admin to confirm the allowance covers the
   **Scribe v2 Realtime developer API**, not just text-to-speech, batch Scribe, or
   the web transcription UI. Public documentation cannot establish your grant's
   coverage or billing terms.
3. Run `python -m companion.voice --mic`, wait for `Scribe session ready`, and say
   `Create cube`. A timestamped committed transcript and one command JSON verify
   this key can perform realtime recognition. Inspect dashboard usage afterward
   to confirm charges use the sponsored allowance. A missing key, auth error,
   `quota_exceeded`, or `unaccepted_terms` message identifies what to fix.

## Verification performed and limitations

Tested environment: macOS 26.4.1, x86_64; Python 3.12.6; ElevenLabs 2.71.0;
sounddevice 0.5.6; httpx 0.28.1; websockets 17.2; PortAudio V19.7.0-devel.
Ruff 0.17.0 and pytest 9.1.1 were installed for verification; the tests themselves
use only the standard library. Audio dependencies are pinned in the owned
`companion/voice/requirements.txt`.

Checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_voice_*'
python -m pip check
ruff check --no-cache --select E4,E7,E9,F,I companion/voice tests/test_voice_*.py
git diff --check
```

- 28 tests passed: supported commands and variants, unrelated/compound speech,
  UUID envelopes, overlapping/duplicate/reordered transcript events, keepalive
  partials, intentional repetitions, bounded dedup state, missing timestamps,
  typed CLI fallback, partial-line input shutdown, PCM/PTT behavior, permission
  error reporting, quota errors, stalled connect/send cancellation, timeouts,
  and secret-safe error tracebacks.
- Typed CLI pipe smoke passed with actual JSON output. Device-list CLI passed and
  enumerated the built-in MacBook microphone and other audio devices.
- Installed SDK smoke passed using **fake audio/API** with the real SDK message
  receiver: session startup, PCM serialization, partial/plain/timestamped event
  dispatch, paired duplicate suppression, repeated commands, and resource close.
  This smoke caught and fixed a startup event-handler registration race.
- Dependency consistency, focused lint, and whitespace checks passed.

**Pending live checks:** no API key was available in this session, so sponsored
entitlement, quota, live transcripts, venue accuracy/latency, and actual API close
are unverified. A local native microphone-format/capture probe stalled in
CoreAudio and was terminated; device enumeration alone does not verify capture.
Grant microphone permission to the launching app/Python entry as shown by macOS,
then repeat a short capture and Ctrl+C rehearsal. Native OS permission/driver
calls can block outside Python's interruptible waits; resolve prompts before the
demo. Permission-denial reporting and shutdown are tested with fakes, not claimed
as physical microphone passes.

Typed console polling supports macOS/Linux; Windows console input is not
implemented. A single committed segment must contain one whole command; multiple
commands, polite filler, misrecognized axis letters, and split phrases are
rejected. There is no LLM interpretation or automatic retry. Restart microphone
mode after fixing a voice error; typed commands remain available throughout.

Official sources consulted on 2026-10-10:

- [ElevenLabs server-side streaming](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming)
- [Transcript and commit strategies](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies)
- [Realtime event/error reference](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference)
- [Realtime API schema](https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime)
- [Workspace API keys and limits](https://elevenlabs.io/docs/overview/administration/workspaces/api-keys)
- [sounddevice raw streams](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html)
- [Official Python SDK source](https://github.com/elevenlabs/elevenlabs-python)
