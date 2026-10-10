# Air Modeler v1 local bridge

The root README contains current setup instructions and the preserved architecture agreement. This document records the current clutch interaction and its legacy compatibility. The single standard-library implementation is `shared/protocol.py`; `tools/package_addon.py` copies its bytes to `air_modeler/_protocol.py` **inside the ZIP only**. Never edit or maintain a second validator source.

## Endpoint and handshake

The companion listens only on `127.0.0.1:8765`, accepts one Blender client (including a client awaiting hello), and closes additional connections. Blender uses a nonblocking socket and a roughly 30 Hz modal timer. No socket thread touches `bpy`.

Every wire message is one UTF-8 JSON object followed by `\n`, with exactly `v`, `type`, `session_id`, `seq`, and `payload`. Blender initiates:

```json
{"v":1,"type":"hello","session_id":null,"seq":1,"payload":{}}
```

The companion assigns a fresh canonical lowercase UUID for every connection and replies:

```json
{"v":1,"type":"hello","session_id":"9a6d7dd7-1ee2-46a4-95cb-cf34d2fb92a6","seq":1,"payload":{}}
```

After hello, each direction uses its own increasing positive integer sequence (first post-hello message is 2), with the assigned session. The receiver accepts strictly increasing values; it does not require contiguous numbers. Unknown fields, repeated JSON keys, non-UTF-8 text, invalid schemas, wrong versions/sessions, and stale sequences are rejected. A bad complete line does not prevent processing the following line. Hello has an empty payload and is accepted only at connection startup. Connection/hello timeout is five seconds.

Companion → Blender: `command`, `hands_frame`; legacy `hand_frame`, `gesture_start`, `gesture_end`, `gesture_cancel`, and deprecated `selector_frame` remain schema-compatible.
Blender → companion: `status`. Both directions send the initial `hello` as described above.

## Payloads

| Type | Required payload fields |
| --- | --- |
| `command` / `spawn` | `id` UUID, `action: "spawn"`, `shape`: `cube`, `sphere`, `cylinder`, `prism` |
| `command` / `set_mode` | `id` UUID, `action: "set_mode"`, `mode`: `MOVE`, `ROTATE`, `SCALE`, `EXTRUDE`; ROTATE optionally accepts `axis` X/Y/Z (default Z); EXTRUDE optionally accepts `plane` AUTO/XY/XZ/YZ (default AUTO) and `axis` NONE/X/Y/Z (default NONE). Explicit axes must belong to explicit planes. |
| `command` / `precision` | `id` UUID, `action: "precision"`, `mode`, finite numeric `value`; `axis` required for MOVE/ROTATE and forbidden for SCALE/EXTRUDE. Bounds and semantics below. |
| `command` / `cancel` or `undo` | `id` UUID, `action`: `cancel` or `undo` |
| `hands_frame` | `profile: "left_clutch_v2"`, `frame_id` positive integer, `t` nonnegative finite capture elapsed seconds, `hands` with exactly anatomical `Left` and `Right` observations; exact fields below |
| `hand_frame` | `u`, `v`, `present` boolean, `pinching` boolean |
| `gesture_start`, `gesture_end` | `gesture_id` UUID, `u`, `v` |
| `gesture_cancel` | `gesture_id` UUID, `reason` text |
| `status` | `mode`, `phase`, `selected_object`, `hovered_object`, `tracking`, `last_error` |

Coordinates must be finite numbers in `[0, 1]`; boolean values are not coordinates. Only absent `hand_frame` observations (`present: false`) may use null coordinates, with both `u` and `v` null. Visible/start/end coordinates cannot be null. Text fields allow at most 1024 Unicode characters and must encode as UTF-8. Extra payload fields are rejected.

**Spawn, MOVE, ROTATE, SCALE and single-face EXTRUDE** change the scene. Matching gesture start/end/cancel events control the armed transform; frames only report/update an existing preview. Commands `cancel`, `undo`, and `set_mode: MOVE/ROTATE/SCALE/EXTRUDE` are implemented. See [MOVE handoff](move_handoff.md) for lifecycle, camera setup, and validation.

Example status (at most 4 Hz while idle, also after received actions/errors):

```json
{"v":1,"type":"status","session_id":"9a6d7dd7-1ee2-46a4-95cb-cf34d2fb92a6","seq":2,"payload":{"mode":"MOVE","phase":"IDLE","selected_object":"Air Cube","hovered_object":null,"tracking":false,"last_error":null}}
```

`mode` is the armed MOVE, ROTATE, SCALE or EXTRUDE; `phase` is the actual IDLE, SELECTED_READY, DRAGGING, or NEEDS_RELEASE state. `selected_object` is the selected active object's name or null. `hovered_object` is the nearest eligible mesh under the cursor or null; passive hover never selects. `tracking` requires a present observation within 0.5 seconds. `last_error` is a readable rejection/recovery diagnostic, cleared by a successful command or gesture. Status is state reporting, not a per-command acknowledgement. SELECTED_READY locks a target and baseline but does not deform it.

In the **legacy single-cursor stream**, a start uses its own coordinates and locks a target, original transform, mode, axis, sensitivity and fixed view mapping. Frames preview from the original transform only; matching end honors final coordinates and creates one undoable transform, then returns to MOVE. Absent frames freeze immediately; 0.5 seconds without a present observation cancels, including stopped streams. Interruptions restore baseline and require a fresh present, non-pinching frame before another start. H independently enforces physical release; its `pinching` flag means gesture-active, never permission to start editing. Duplicate starts are remembered per session (4096 limit); mismatched ends/cancels are ignored. Spawn and mode changes during drag are rejected. The coherent two-hand stream instead follows the clutch lifecycle below.

## Teammate callback

```python
server = BridgeServer()  # from companion.transport.server
server.start()
emit = server.emit
# run_hand_tracker(emit, stop_event, config)
# run_voice(emit, stop_event, config)

accepted = emit({
    "type": "command",
    "payload": {
        "id": "875905d1-9dad-46bd-9ef6-439da23920ef",
        "action": "spawn",
        "shape": "cube",
    },
})
```

`BridgeServer.emit(event: dict) -> bool` is thread-safe and nonblocking with respect to network I/O and queue space. It validates and snapshots the event under short memory-only synchronization. H/V supply **only** `type` and `payload`, including their own command/gesture UUIDs. One transport thread assigns all outgoing envelope sequence numbers and writes bytes. H/V must not create sockets, add envelope fields, manage Blender modes, or retry discarded input after reconnect. Their existing service signatures and independent print-JSON harnesses remain unchanged.

`True` means queued in the current ready session, not confirmed scene execution. `False` means invalid input, no ready connection, a session change during the call, or queue overflow; `server.last_error` explains. The callback captures its initial session so an in-flight call cannot cross reconnect. Preserve ordered boundary events. Only a trailing legacy `hand_frame` may be replaced by another consecutive legacy `hand_frame`; never coalesce across a command or gesture boundary. **`hands_frame` events are never coalesced**, because each coherent capture can contain either hand's START/END/CANCEL boundary. The callback queue holds at most 256 events. Overflow faults the connection and discards pending input rather than silently losing boundaries.

## Limits, failure and reconnect behavior

- Maximum encoded line: 8192 bytes excluding newline. Overlong lines are discarded through the next newline, then normal decoding resumes. Each socket read takes at most 8192 bytes; complete buffered lines drain before another read. Partial-line storage is bounded to 8192 bytes.
- Blender decodes/dispatches at most four lines per timer tick and uses nonblocking writes with retained partial-write offsets. The server accepts at most one connection, processes at most 16 incoming lines and queues at most four callback events per iteration. Outgoing bytes are capped at 64 KiB; backpressure overflow disconnects instead of blocking.
- Command IDs are deduplicated in Blender for the entire session, including failed/unsupported commands. A duplicate with a newer sequence is consumed without a second action. At 4096 distinct command IDs, close the session rather than evict IDs and risk replay. Reconnect explicitly to continue.
- Clean EOF, server shutdown, connection failure, disable, file load, or invalid captured viewport context restores any active preview, closes the socket, and removes the modal timer and cursor draw handler. Reconnect is a user action; there is no automatic reconnect or spawn retry.
- Disconnect destroys session sequence/dedup state, partial receive data, pending writes, and queued callback input. The server rejects input while offline. Fresh sessions never replay prior pending events. TCP cannot retract an action already executed before a disconnect; inspect the scene/status if delivery was interrupted.
- Session state is runtime-only. Blender captures the initiating window/viewport/region and scene/view-layer names, re-resolves them after Undo, and uses an explicit context override for the existing undoable spawn operator. Changing/closing that viewport or switching its scene/view layer stops the connection. Edit Mode rejects spawn without switching modes or creating geometry.

## Development runner

From `/Users/krishpatel/HackRu`:

```sh
.venv/bin/python -m companion.main
```

Connect from Blender's Air Modeler panel and wait for `READY`. Then enter:

```text
spawn cube
spawn sphere
spawn cylinder
spawn prism
status
quit
```

Typed input now reuses V's parser and UUID emitter: `create cube`, `create sphere`, `create cylinder`, `create triangular prism`, `rotate`, `rotate x/y/z`, `scale`, `extrude`, `move`, `cancel`, and `undo`. Strict `spawn <shape>` aliases are translated to V's create phrase. `quit`, EOF, or Ctrl-C stops workers and transport; no stale replay occurs. `QUEUED` is not an acknowledgement. No camera/audio packages or keys are needed for typed/synthetic operation. Optional camera/audio flags and explicit `--two-hands` / `--legacy-hands` selection are documented in [the current handoff](clutch_handoff.md); discover camera indices through the hands module before selecting them.

In the legacy single-cursor fallback, ROTATE uses horizontal displacement around a world axis; SCALE uses upward vertical displacement to enlarge. The revised clutch stream uses Right whole-hand palm translation, twist and openness, plus distinct Right pinch extrusion; Left selects only. Axis/angle/factor appear locally in the sidebar/cursor text.

EXTRUDE uses an isolated geometry preview and separate geometry Undo operator. Face index, plane mapping and displacement remain Blender-owned transaction details; the tracker supplies observations, never geometry decisions. The legacy stream's outward vertical-distance mapping is distinct from the new signed plane mapping.

The integrated runner also supports `--mic --push-to-talk`: local `/talk` and `/end` controls share VoiceConfig’s gate and never enter the wire protocol. See [README](../README.md) and [demo handoff](demo_handoff.md) for audio gating, launch and rehearsal details.

## Coherent whole-hand observations (0.8.0, v1 envelope)

`--two-hands` uses one mirrored capture, up to two anatomical hands and exactly one `hands_frame` per processed capture. It emits no legacy cursors or selector menu events. Payload keys are exactly `profile`, `frame_id`, `t`, `hands`. `profile` must equal **`left_clutch_v2`**. Old 0.7 coherent frames and fields are rejected, never interpreted as new controls; install matching companion and ZIP. Explicit `--legacy-hands` retains the old single-cursor payloads. A camera run without either flag errors. There is no silent fallback.

`frame_id` is strictly increasing in `[1, 2^53−1]`; `t` is strictly increasing finite nonnegative elapsed seconds from the producer's monotonic origin. Both identities share the same capture timestamp. Blender checks ordering and delivery age (0.5 s from the first-capture clock offset), separately from transport sequence/session checks. `hands` has exactly `Left` and `Right`, with explicit invalid observations for missing/uncertain hands. Result-array order never assigns a role. Each hand has exactly:

| Field | Wire meaning / validation |
| --- | --- |
| `valid` | Boolean: confidently assigned visible anatomical identity; invalid never means released. |
| `confidence` | Finite `[0,1]`, exactly zero when invalid. Producer accepts identity at ≥0.8. |
| `u`, `v` | Corrected pinch cursor `[0,1]`: pre-close aim hold, palm-relative held movement, frozen opening/END coordinate. Null if invalid. Used for Left selection and Right extrusion, never Left-driven movement. |
| `palm_u`, `palm_v` | Once-filtered wrist/index/middle/pinky MCP center `[0,1]`; null if invalid. Right MOVE uses this center. |
| `pinching` | Boolean active thumb/index UUID lifecycle, not whole-hand shape and never permission by itself to select. False if invalid. |
| `open` | Boolean observed stable thumb/index release, false when pinching/invalid. This is separate from an open palm; a fist may have an ordinary pinch. |
| `gesture_id` | Canonical lowercase UUID on START/END/CANCEL or active pinch; null for inactive NONE. Left ID locks selection, Right ID locks extrusion. |
| `event` | NONE / START / END / CANCEL. START needs valid+pinching; END needs valid+open+not-pinching; CANCEL needs ID and not-pinching, and may be invalid. |
| `shape_valid` | Boolean: all required whole-hand measurements are finite/nondegenerate; independent of `valid`. A visible fist is shape-valid. False if invalid identity. |
| `shape_error` | Null when shape-valid; otherwise nonempty readable string ≤1024 characters. |
| `angle` | Finite measured palm image-plane radians `[-π,π]` when shape-valid, otherwise null. Available throughout fist closure; not 3D orientation. |
| `openness` | Finite `[0,1]` average of four fingers' flexion and palm-normalized reach when shape-valid, otherwise null. Not three-tip aperture. |
| `open_palm` | Boolean: all four fingers plus thumb extended, with hysteresis. False without valid measurements. Required for MOVE/ROTATE. |
| `extrude_pose` | Boolean: at least two of middle/ring/pinky substantially open, with hysteresis; thumb/index can approach/contact. False without valid measurements. |
| `pinch_pending` | Boolean: isolated extrusion-eligible thumb/index approach (ratio ≤0.75); implies `extrude_pose`. Reserves pending intent before debounced START. False without valid measurements. |

All flags are JSON booleans, never 0/1. Invalid identity requires four null coordinates, false pose/measurement flags, null angle/openness and a shape error. Shape-invalid with valid identity retains corrected cursor and boundary lifecycle but cannot manipulate; this permits a Left selection while reporting Right measurement failure distinctly. Unknown keys, old `grip`/`aperture`, invalid numbers, contradictory release flags and unsupported profiles fail closed. Encoder/server/packaged consumer all call the same validator.

The producer uses confidence and spatial continuity and protects Right's identity path throughout a Left pinch. Overlap/uncertain crossing invalidates observations rather than transferring ownership. Actual anatomical labels in the mirrored pipeline remain a physical acceptance requirement; synthetic identity tests do not establish that result. Exact openness math, pose thresholds and limitations are in [the current handoff](clutch_handoff.md).

Blender alone owns arbitration: IDLE → SELECTED_READY → DRAGGING → release gating → IDLE. Only a fresh **Left START** selects, using that event's corrected coordinates. It captures object, Left UUID, original baseline and eligible face separately; a valid object without an eligible face remains transformable. Left movement has no classifier input or preview displacement. Right START cannot select. Every START is remembered per session even when blocked; held misses, duplicate boundaries and completed IDs cannot queue another transaction.

Right open-palm translation competes for MOVE, whole-hand twist for ROTATE, and openness change for SCALE through normalized thresholds, persistence, dominance and hysteresis. A developing isolated pinch reserves EXTRUDE intent; whole-fist closure does not. A fresh eligible Right START after an observed Right-open state **after/at Left selection** can activate extrusion. Right already pinched (including START in the same selection capture) must reopen and repinch. Opening after reserved/held pinch rearms and resets references without accidentally scaling. Tool, references, required identities, face/plane and baseline lock on activation. Crossing the intent threshold itself has zero displacement. No mid-preview tool change or Left deformation is permitted.

MOVE/ROTATE/SCALE finish only on the matching observed Left END with valid Right input. Fist contact/Right END during SCALE is only a shape observation, not completion. EXTRUDE finishes on matching valid Right END with frozen final Right coordinates while Left is valid, or matching Left END while Right remains valid. First completion clears the transaction and makes the other END inert. Right-first completion retains the Left gate; Left-first retains the Right gate; both observed releases are needed before another Left selection. Required releases may arrive in one capture or separately. A START in a gate-clearing capture is consumed, never queued. Unchanged/ready/zero-distance completion restores temporary state with no geometry edit or Undo entry.

Both Left clutch and Right controller are required. Missing identity/invalid required pose/measurement immediately freezes; sustained loss or stale input for 0.5 seconds restores baseline once and gates both observed releases. Short recovery rebases Right references without jumping. Release in the same capture as required-hand recovery cancels rather than committing stale geometry. A fist is valid SCALE input. Tracking loss never fabricates END. Escape/cancel/disconnect/context change/file load/disable/shutdown restore through the same transaction cleanup. Undo cancels preview before undoing the prior completed edit. Idle cancel/disconnect doesn't invent a hand gate, preserving typed-only precision.

## Precision and one-operation overrides

Command action `precision` requires `id`, `action`, `mode`, `value`, plus `axis` only for MOVE/ROTATE. Values must be finite JSON numbers (not bool): rotation ±360 degrees, movement ±100 world units, scale 0.1–10 inclusive, extrusion >0.00001 and ≤4 world units. Axes are X/Y/Z. Exact object commands apply once to the currently selected eligible object while IDLE. EXTRUDE arms outward-normal distance for the next explicit Left face-selection plus fresh Right-pinch operation: no hover edit and no additional hand displacement. Invalid/conflicting commands during SELECTED_READY or DRAGGING are rejected, never queued. Session/UUID dedup and typed/committed-only speech remain unchanged.

Whole phrases include `rotate x 45 degrees`, `move z -2 units`, `scale by 1.5`, `extrude 0.5 units`, and `extend .5 units`. Bare `rotate [x|y|z]`, `scale`, `move`, `extrude` and `extend` arm one operation subject to the same target/identity locks and required gestures. Mode/plane commands do not immediately alter geometry. Completion/cancellation clears the override.

Plane phrases exactly match the controls: `extrude plane xy`, `extrude plane xz axis z`, `extrude plane yz axis y`, `extrude plane auto`, or `extrude axis x`. `extend` is accepted in place of `extrude`. Optional axes are X/Y/Z/NONE; omitted plane is AUTO and omitted axis is NONE. AUTO with an explicit axis chooses a compatible mapping plane. Explicit plane/axis incompatibility (such as XY with Z) is rejected. Numeric extrusion accepts distance only and keeps its separate outward-normal semantics. Conversational prefixes/suffixes and combined multi-action phrases are rejected.

## Deprecated 0.6.0 selector compatibility

Legacy events retain their exact payloads. Deprecated `selector_frame` has exactly `pose` (FIST, TWO, THREE, OPEN, UNKNOWN or ABSENT), `manipulator` (Right/Left) and `selector` (the opposite role). Its validator remains for compatibility; it is not emitted or used as the selector-pose menu in the new clutch interaction. The following describes the historical 0.6.0 producer/consumer, not the current two-hand controls. Older add-ons reject `hands_frame`; install the matching current ZIP and companion together.

Blender confirms FIST→MOVE, TWO→ROTATE world Z, THREE→SCALE, OPEN→EXTRUDE after 300 ms continuously observed while idle. UNKNOWN/ABSENT retains the last confirmed pose for 600 ms, then MOVE. A stale selector stream also falls back after 600 ms. Changes never alter a drag's captured mode/axis/target/start/baseline. Bare mode commands override automatic selection for one operation; fixed-distance extrusion also overrides. Completion/cancellation clears the override. Single-hand completes to MOVE; two-hand can rearm the still-confirmed selector while idle after release gating.

Two-hand identity uses MediaPipe handedness on the already mirrored input (selfie convention; anatomical labels must be physically verified), confidence ≥0.8, unique labels and spatial continuity of palm centers. Centers within 0.12 normalized image distance are ambiguous; displacement >0.18 per frame is rejected. Uncertain manipulating-hand identity during a pinch is quarantined until the existing loss cancellation; no hand substitution is permitted. After 600 ms without a recovered idle identity, old spatial anchors may expire. Reacquisition requires 300 ms stable identity and the existing open-hand gate. Selector never generates manipulation events.

Pose classification uses index/middle/ring/pinky MCP/PIP/DIP/tip points in aspect-corrected image coordinates. Extended: PIP and DIP joint angles ≥160° and tip-wrist distance ≥1.15×PIP-wrist distance. Folded: PIP angle ≤110° and tip-wrist distance ≤1.1×PIP-wrist distance. Other shapes are UNKNOWN. Fist requires all four folded; TWO requires only index/middle extended; THREE adds ring; OPEN requires all four extended. Thumb is ignored for selection (it remains part of manipulation pinch detection). This is conservative 2D classification; edge-on/occluded hands may be UNKNOWN.
