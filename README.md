# Air Modeler — HackRU

## Implemented MVP and verification

Air Modeler 0.5.0 implements sidebar/voice/typed creation of cubes, UV spheres, cylinders and triangular prisms; pinch MOVE in the viewport plane; world-axis ROTATE; uniform SCALE; outward single-face EXTRUDE; cancel and Undo. Completed gestures return to MOVE. A separate Python companion owns camera/audio and a local TCP bridge; Blender owns all scene edits.

Use Object Mode and visible, editable, unparented meshes without constraints, animation or enabled modifiers. EXTRUDE additionally requires a local single-user mesh, no shape keys/custom normals, a positive nonsingular transform, closed consistently oriented manifold geometry, and a flat convex triangular or quad supporting face. Cube faces, prism caps/sides and eligible newly extruded caps are supported. Reflected transforms, recessed/nonplanar faces, inward/multiple-face extrusion and arbitrary geometry reconstruction are outside this demo. See [geometry restrictions](docs/extrusion_handoff.md).

Automated Python checks and synthetic Blender geometry/Undo checks pass. H's live tracker and V's standalone live speech reports do **not** establish a combined live 0.5.0 demo pass. See [demo evidence and rehearsal](docs/demo_handoff.md) for exact revisions, remaining device checks and presentation checklist. Sponsor attribution remains unconfirmed; V verified realtime API access.

## Reproducible companion setup

Run in `/Users/krishpatel/HackRu`. Verified here: macOS arm64, CPython **3.12.15**, Blender **5.2.2 LTS** (its own Python 3.13.13). The runner console supports macOS/Linux; Windows console input is not implemented. Other Blender/platform versions remain unverified. Reuse the existing `.venv` after checking its interpreter; only run the creation command on a fresh setup, with Python 3.12 installed:

```sh
cd /Users/krishpatel/HackRu
python3.12 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install -r requirements.txt -r requirements-voice.txt
.venv/bin/python -m pip install pytest==9.1.1
.venv/bin/python -m pip check
.venv/bin/python -m companion.hands.model
```

The existing locally provisioned uv environment lacks pip; reuse it without recreating it. Its dependency check is `UV_CACHE_DIR=/tmp/hackru-uv-cache /tmp/hackru-uv/bin/uv pip check --python .venv/bin/python`. The portable pip commands above apply to a fresh standard-library venv.

Verified installed pins: MediaPipe 1.1.0, opencv-contrib-python 4.11.0.86, NumPy 1.26.4, ElevenLabs 2.71.0, sounddevice 0.5.6, httpx 0.28.1, websockets 17.2; pytest 9.1.1 for checks. Do not install a second OpenCV distribution alongside opencv-contrib-python. Install these outside Blender. Typed-only operation needs no third-party dependencies.

Model path: `/Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task`. Tested SHA-256: `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`. The downloader warns on mismatch because its upstream URL uses `latest`; investigate a changed checksum before the demo. The launch commands below pass the path explicitly, overriding `HAND_LANDMARKER_MODEL`.

Discover devices on the actual demo laptop:

```sh
.venv/bin/python -m companion.hands --list-cameras
.venv/bin/python -m companion.voice --list-devices
read 'CAMERA_INDEX?Camera index from the working local camera probe: '
read 'MIC_INDEX?Input microphone index from the local device list: '
```

These prompts use macOS zsh. Camera discovery probes indices 0–4. Grant Camera/Microphone access to the launching Terminal/IDE under System Settings → Privacy & Security, then restart that application if needed. Close competing capture applications. Select a working camera and an **input** microphone; indices change with attached phones/headsets. H's camera index 2 is not a portable default. The integrated hands worker always sets `preview=False`, avoiding macOS OpenCV GUI calls on a worker thread.

For live voice only, privately enter the **ElevenLabs API key** in the companion terminal. Do not paste it into a command, chat, file, Blender console or diagnostic output:

```sh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

The value is hidden and absent from shell history. Launch Blender separately from the key-bearing shell; after the companion exits, `unset ELEVENLABS_API_KEY`. Keep terminal recording/debug tracing off. Realtime account access and microphone permission still need validation on the demo laptop.

## Package, install and launch

```sh
.venv/bin/python tools/package_addon.py
```

ZIP: `/Users/krishpatel/HackRu/dist/air_modeler.zip`, actual add-on version **0.5.0**. Companion/PTT changes do not change that version. Record the companion revision with `git rev-parse HEAD`. In Blender, disconnect and disable/remove an older Air Modeler install, quit and restart Blender, then Preferences → Add-ons → Install from Disk, select this ZIP and enable Air Modeler. Confirm 0.5.0. Restart after updating to discard cached modules. Enable Global Undo. Open a separate rehearsal scene manually; do not overwrite `demo.blend` or clear an existing working scene.

Choose **one** command after selecting the local device variables above:

```sh
# Hands plus typed commands (no API key needed)
.venv/bin/python -m companion.main --camera "$CAMERA_INDEX" --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task

# Hands plus hands-free live voice, with typed fallback
.venv/bin/python -m companion.main --camera "$CAMERA_INDEX" --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device "$MIC_INDEX"

# Hands plus push-to-talk live voice, with typed fallback
.venv/bin/python -m companion.main --camera "$CAMERA_INDEX" --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device "$MIC_INDEX" --push-to-talk
```

In a 3D viewport, open the N sidebar → Air Modeler → Connect. Wait for companion `READY` before commands. `Hands config:` confirms camera/model and preview False. For voice, wait for `Scribe session ready. Opening microphone; typed commands remain active.` as well. `status` shows Blender state/errors; `help` lists commands. `QUEUED` means queued, not successful scene execution: inspect Blender/status. `quit`, `/quit`, EOF or Ctrl+C stops workers and bridge.

PTT starts **PTT MUTED**. Enter `/talk` → **PTT ARMED**, speak one complete command, then `/end` → **PTT MUTED**. Wait for `Committed with timestamps:` and the visible result before the next turn. Repeated controls are harmless; state changes print once, and `status` prints the current gate. Without `--mic --push-to-talk`, controls explain that PTT is unavailable. Hands-free mode uses speech silence detection instead.

PTT gates audio at capture callbacks (100 ms blocks), replacing muted audio with zero PCM; the microphone stays open and silence is transmitted. The first queued inactive block after active audio triggers one manual commit. Buffered active audio can finish after `/end`, and the intended delayed timestamped transcript can execute while muted. Partial/plain transcripts never execute; timestamped duplicates are suppressed by the voice service. `/end` is not cancellation of already spoken commands. Do not toggle faster than one audio block or start another turn until committed feedback; shutdown stops recognition rather than draining unfinished speech. `PTT ARMED` describes the gate, not microphone health. Restart the companion after a voice startup failure; typed input and hands remain usable.

Common remedies:

- `Cannot listen ... 8765`: close the prior companion; only one server/client is supported.
- `DISCARDED`/not READY: connect Blender and deliberately reissue the command once ready; offline input is discarded, never replayed.
- Missing model: run the downloader and verify the explicit path/checksum.
- Camera unavailable/unauthorized: grant permission and repeat discovery; don't guess another laptop's index.
- `ELEVENLABS_API_KEY is missing`, auth/quota/terms errors: enter the key privately or fix account access, then restart. Typed commands still work.
- Microphone unavailable: check permission and input device; integrated voice uses 16 kHz. The standalone voice diagnostic accepts `--sample-rate 48000`, but that flag is not exposed by this runner. If only 48 kHz works, use typed fallback and report the device incompatibility to V/P.
- `NEEDS_RELEASE`: open the hand visibly before pinching again. Face rejection: use an eligible cube/prism face and inspect the outline/error.

## Architecture agreement (preserved)

The following ownership boundaries and contracts remain the team agreement. Future-tense language in this historical agreement records the original design; the implemented status and launch instructions above supersede its milestone planning.

## Ownership and collaboration

| Owner | Planned owned paths |
| --- | --- |
| P (Pro / integration) | `addon/air_modeler/`, `companion/main.py`, `companion/transport/`, `shared/*`, `docs/protocol.md`, `tools/package_addon.py`; root configuration, dependency files, README, integration checks |
| H (hands) | `companion/hands/*`, `tests/test_hands_*`, `docs/hands_handoff.md` |
| V (voice) | `companion/voice/*`, `tests/test_voice_*`, `docs/voice_handoff.md` |

These are ownership boundaries, not scaffolding to create now. Once this agreement is committed to `main`, H and V may branch and create their implementation files without waiting for empty modules or a complete skeleton. Each service must run independently with a callback that prints JSON. Only P integrates into `main`; coordinate before changing another owner's files or any shared interface.

## Planned stack

| Area | Technology |
| --- | --- |
| Blender | `bpy`, `bmesh`, `mathutils` |
| Hands | OpenCV, MediaPipe Tasks Hand Landmarker |
| Voice | `sounddevice`, ElevenLabs Scribe v2 Realtime; deterministic parsing, no LLM parser required |
| Transport | Local TCP at `127.0.0.1:8765`; companion server, Blender client; UTF-8 newline-delimited JSON |

Camera/audio dependencies will run only in the companion environment. SDK compatibility and sponsored realtime speech-to-text access must be verified during implementation. API keys will stay in environment variables and outside Blender.

## Shared module interfaces

Exact planned signatures:

```python
# companion/hands/tracker.py
run_hand_tracker(emit, stop_event, config) -> None

# companion/voice/service.py
run_voice(emit, stop_event, config) -> None

# companion/voice/parser.py
parse_command(text) -> dict | None
```

Hands and voice will call `emit(event)` with a dictionary containing only `type` and `payload`. P will supply the thread-safe, nonblocking callback, orchestration, transport, and wire envelope. Both services must exit when `stop_event` is set. H and V must not create sockets or manage Blender interaction modes. P will handle platform-specific device and preview event-loop requirements during integration.

## Hand events

| Type | Payload fields |
| --- | --- |
| `hand_frame` | `u`, `v`, `present`, `pinching` |
| `gesture_start` | `gesture_id`, `u`, `v` |
| `gesture_end` | Same `gesture_id`, final `u`, `v` |
| `gesture_cancel` | `gesture_id`, `reason` |

Example callback event:

```json
{"type":"gesture_start","payload":{"gesture_id":"<uuid>","u":0.4,"v":0.6}}
```

H will track one hand and mirror the camera image once before inference and preview. Coordinates are normalized: `u` increases left to right and `v` top to bottom. Visible coordinates must be finite and within `[0, 1]`; only absent `hand_frame` observations may use `null` coordinates. Gesture start/end coordinates must be valid.

H will generate gesture UUIDs, apply cursor smoothing once, and use pinch hysteresis. One pinch must produce one start and one end or cancellation. Tracking loss will freeze the preview immediately; sustained loss of approximately 0.5 seconds will cancel it. After cancellation, a visible released hand is required before accepting another gesture.

## Voice commands

| Action | Payload parameters |
| --- | --- |
| `spawn` | `shape`: `cube`, `sphere` (UV sphere), `cylinder`, or `prism` (triangular prism) |
| `set_mode` | `mode`: `MOVE`, `ROTATE`, `SCALE`, or `EXTRUDE`; `ROTATE` accepts `axis`: `X`, `Y`, or `Z`, default `Z` |
| `cancel` | None |
| `undo` | None |

`parse_command` will return an action payload without an ID, or `None` for unrelated speech. For example:

```json
{"action":"set_mode","mode":"ROTATE","axis":"Z"}
```

The voice service will add a UUID under `id` and emit type `command`:

```json
{"type":"command","payload":{"id":"<uuid>","action":"spawn","shape":"cube"}}
```

Only committed transcripts will execute. Repeated provider events must be deduplicated while allowing later intentional repetition. Typed input will use the same parser and remain available when voice fails.

## Wire contract — planned version 1

Each message will be one UTF-8 JSON object followed by a newline:

```json
{"v":1,"type":"command","session_id":"<session>","seq":1,"payload":{"id":"<uuid>","action":"spawn","shape":"cube"}}
```

P's transport layer will add `v`, `session_id`, and `seq`; H and V will not. Blender will send `hello` first with `session_id: null`. The companion will assign a fresh session ID in its reply; subsequent messages will use that session. Sequence numbers will increase independently in each direction.

Blender will send `status` containing `mode`, `phase`, `selected_object`, `hovered_object`, `tracking`, and `last_error`.

Command IDs must be deduplicated per session. Disconnect will discard stale input; reconnect must neither replay commands nor revive gestures. Only consecutive `hand_frame` observations may be coalesced, preserving command and gesture boundaries.

## Blender interaction rules

- Blender alone will own scene edits, modes, and interaction state. Scene edits must run on Blender's main thread.
- Modes: `MOVE`, `ROTATE`, `SCALE`, `EXTRUDE`. Phases: `IDLE`, `DRAGGING`, `NEEDS_RELEASE`. `MOVE` is the default; successful manipulations will return to `MOVE`.
- Only `gesture_start` over a valid target may start hand manipulation. Hovering and `hand_frame` alone must never start an edit. A missed pinch must not begin editing later while still held; require release before another attempt.
- Voice spawning and undo will be explicit actions independent of pinching. Spawn and mode changes must be rejected during an active drag.
- Lock one target per gesture and calculate every preview from its initial state. Initially support unparented mesh primitives without topology-changing modifiers.
- Create extrusion topology once per gesture; subsequent updates will move the new cap vertices.
- Release will commit one completed edit as one undo action; preview frames must create none.
- Cancel, disconnect, or sustained tracking loss will restore the pre-gesture state. Cancellation will require release before another gesture. Undo during dragging will cancel the preview before undoing the previous completed action.

## First milestones

After the agreement is committed, work in parallel:

| Owner | First deliverable |
| --- | --- |
| P | Sidebar buttons that create all four shapes; shared validator and bridge |
| H | Webcam preview, cursor, pinch/release events, replay fixtures |
| V | Typed parser, microphone recognition, command fixtures |

Prove synthetic spawning through the real bridge early. Then integrate the live cursor and voice spawning, followed by movement, rotation/scaling, extrusion, and recovery checks.

## Git workflow and handoffs

Use `feature/blender`, `feature/hands`, and `feature/voice`. Each teammate will work in a separate local clone or worktree, commit and push owned changes, and open pull requests into `main`. P will merge one at a time with relevant checks between merges.

Every handoff must include the commit SHA, changed files, exact run command, checks actually performed, and known failures. Until verified, run commands and runtime/dependency versions must be labeled **to be verified**.
