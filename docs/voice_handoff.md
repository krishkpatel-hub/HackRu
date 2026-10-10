> Current 0.6.0 integration: [two-hand selection and precision handoff](enhancement_handoff.md). The dated results below are historical evidence, not a combined 0.6.0 live pass.

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
audio watermark. Missing/malformed timestamps fail closed. Keep timestamps enabled.
The live rehearsal confirmed later utterances have later session word spans.
No reconnect/replay occurs.

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
   In Developers → Analytics → Usage, select workspace data and filter by the
   test's time range, product, and API key. Compare allowance before/after and
   confirm the requests appear in that workspace's Request Log. A successful
   transcript alone does not establish sponsorship coverage.

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
- Follow-up physical capture on the MacBook Pro microphone (device 1): mono
  int16 at 16 kHz, a two-second capture in a child with an eight-second hard
  deadline. In the user's Terminal it delivered 19 callbacks / 30,400 frames,
  peak 2,734, zero status errors, an active stream during capture, and a closed
  stream afterward (`CAPTURE_AND_CLEAN_CLOSE_PASS`). A separate local run also
  passed with 20 callbacks / 32,000 frames. No audio was saved or transmitted.
- Follow-up voice tests: all 28 unittest tests passed. The actual microphone CLI
  with the key deliberately absent reported the missing key and continued to
  emit typed `undo`, `create cube`, and another `create cube`; the two cube
  commands had distinct UUIDs and the process exited successfully.

- Live ElevenLabs recognition passed in the user's Terminal. The full sequence
  `create cube`, `create sphere`, `create cylinder`, `create triangular prism`,
  `rotate x`, `scale`, `extrude`, `move`, `cancel`, `undo`, `create cube` emitted
  exactly 11 spoken commands with the documented payloads and 11 distinct UUIDs.
  The two cubes had different word spans (2.44–3.18 s and 31.98–33.14 s),
  confirming intentional repetition executes again on the session timeline.
- In that full live session, 13 partials and 12 plain commits emitted zero
  commands. The temporary diagnostic replayed each of the 12 real timestamped
  events once; all injected replays emitted zero additional commands. This is
  replay testing with real event data, not a claim that the provider naturally
  sent duplicate timestamped events. Plain/timestamped partner events executed
  once. Unrelated committed speech (`Mm, negative.`) was rejected.
- Live push-to-talk: two `/talk` → spoken `create cube` → `/end` turns emitted
  exactly two cubes with different UUIDs and word spans. Typed `undo` also
  emitted correctly in the same session. Five partials, two plain commits, and
  two injected timestamped replays emitted zero additional commands. The user
  confirmed speech attempted while muted produced no command and venue
  background noise was present. These environmental conditions are operator
  observations; the report verifies the resulting command/event counts.
- Manual Ctrl+C in the full-command and push-to-talk sessions returned exit code
  0; microphone streams, API WebSockets, and owned HTTP clients all closed,
  with no voice worker left alive. The initial short live recognition session
  also passed the same resource-close checks.
- Local diagnostic reports (temporary, not committed; no audio or key values):
  `/tmp/hackru_voice_live_vad.json`, `/tmp/hackru_voice_live_commands.json`, and
  `/tmp/hackru_voice_live_ptt.json`. Payload/UUID/event/resource assertions passed
  against the full-command and PTT reports. All 28 voice unittest tests passed
  again after these live checks. Production code required no changes.

**Remaining verification — sponsor attribution only:** the user reports dashboard
usage increased from 0 to 70 credits against a displayed 131,000-credit allowance.
The dashboard shows Creator plan without a sponsorship label. Realtime access and
a dashboard usage
increase are confirmed, but ownership of the key by the sponsored workspace and
attribution to the sponsored grant remain unconfirmed. The workspace/sponsor
admin must confirm the key's workspace and that the displayed allowance is the
sponsored realtime allowance. No API key was requested in chat or logged.

The earlier native probe stalled and was terminated; the bounded follow-up above
now verifies physical capture and clean microphone close.
An initial zero-frame follow-up result came from a buffer conversion bug in the
temporary diagnostic, which was corrected; production already converts the raw
buffer to bytes. No production fix was required. Use the audio virtualenv:
system `python3` on this machine does not have sounddevice installed. Native OS
permission/driver calls can block outside Python's interruptible waits, so keep
capture probes bounded. Permission-denial reporting remains tested with fakes.

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
- [Workspace usage analytics](https://elevenlabs.io/docs/overview/administration/usage-analytics)
- [sounddevice raw streams](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html)
- [Official Python SDK source](https://github.com/elevenlabs/elevenlabs-python)
