# Air Modeler — HackRU Architecture Agreement

## Scope and status

We are a three-person team planning a Blender add-on controlled by hand gestures and voice. Blender will supply modeling, geometry, and the viewport; a separate local Python companion will handle webcam tracking and voice recognition. This README records the planned agreement, not working features.

The MVP will support voice spawning of cubes, UV spheres, cylinders, and triangular prisms; default pinch-and-drag movement in the current viewport plane; voice-selected rotation around world X/Y/Z, uniform scaling, and single-face extrusion. Release will commit, cancel will restore the pre-gesture state, and undo will reverse completed actions. Extrusion will start with cube and prism faces. Arbitrary air-drawn mesh reconstruction, physics, and a custom renderer are outside scope.

Runtime versions, dependency versions, and launch commands: **to be verified**. No implementation or runtime checks are claimed by this agreement.

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
